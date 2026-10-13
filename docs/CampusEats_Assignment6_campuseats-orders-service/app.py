"""CampusEats Orders Service - Assignment 6: honest status codes, one error
shape (Problem Details), request validation and content negotiation.

Built on the Assignment 5 service (same endpoints, same store, same payment
client). What changed in A6 is how outcomes are reported:

  * every failure is a Problem Details body (application/problem+json) built
    by errors.problem() -- there is no other error shape in this file;
  * invalid request bodies get ONE 422 listing every bad field;
  * Accept is honoured: application/json (default), application/xml, else 406;
  * unexpected exceptions are logged server-side and mapped to a clean 500.
"""

import gzip
import hashlib
import json
import logging
import os
import time
import uuid
import xml.etree.ElementTree as ET

from flask import Flask, g, request
from werkzeug.exceptions import HTTPException

import errors
import store
from errors import ApiError
from models import Order, OrderItem
from payment_client import PaymentDeclined, PaymentServiceUnavailable, charge_payment

app = Flask(__name__)

VALID_PAYMENT_METHODS = {"CARD", "UPI", "WALLET", "COD"}
CANCELLABLE_STATUSES = {"PENDING", "PLACED"}
ALLOWED_OVERRIDE_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
DEMO_BEARER_TOKEN = os.environ.get("DEMO_BEARER_TOKEN", "campuseats-demo-token")
RATE_LIMIT = int(os.environ.get("RATE_LIMIT", "60"))
RATE_WINDOW_SECONDS = 60
_rate_state = {}


def _is_int(value):
    # bool is a subclass of int in Python; true/false is not a valid number here.
    return isinstance(value, int) and not isinstance(value, bool)


def validate_create_order(data):
    """C1/C2: check the whole POST /orders body and COLLECT every problem.

    Body schema (equivalent JSON Schema is in openapi.yaml -> OrderCreateRequest):
      studentId     string, non-empty                     required
      items         array, >= 1 entries                   required
        itemId      integer                               required
        quantity    integer >= 1                          required
      addressId     integer                               required
      paymentMethod one of CARD, UPI, WALLET, COD         required

    Nothing is looked up or charged until this returns without raising.
    """
    if not isinstance(data, dict):
        raise errors.malformed_body("Request body must be a JSON object.")

    problems = []

    def bad(field, message):
        problems.append({"field": field, "message": message})

    student_id = data.get("studentId")
    if student_id is None:
        bad("studentId", "is required")
    elif not isinstance(student_id, str) or not student_id.strip():
        bad("studentId", "must be a non-empty string")

    items = data.get("items")
    cart_is_empty = False
    if items is None:
        bad("items", "is required")
    elif not isinstance(items, list):
        bad("items", "must be an array of {itemId, quantity} objects")
    elif len(items) == 0:
        cart_is_empty = True
        bad("items", "must contain at least one item")
    else:
        for i, entry in enumerate(items):
            if not isinstance(entry, dict):
                bad(f"items[{i}]", "must be an object with itemId and quantity")
                continue
            if "itemId" not in entry:
                bad(f"items[{i}].itemId", "is required")
            elif not _is_int(entry["itemId"]):
                bad(f"items[{i}].itemId", "must be an integer")
            if "quantity" not in entry:
                bad(f"items[{i}].quantity", "is required")
            elif not _is_int(entry["quantity"]) or entry["quantity"] < 1:
                bad(f"items[{i}].quantity", "must be an integer >= 1")

    address_id = data.get("addressId")
    if address_id is None:
        bad("addressId", "is required")
    elif not _is_int(address_id):
        bad("addressId", "must be an integer")

    payment_method = data.get("paymentMethod")
    if payment_method is None:
        bad("paymentMethod", "is required")
    elif payment_method not in VALID_PAYMENT_METHODS:
        bad("paymentMethod", f"must be one of {sorted(VALID_PAYMENT_METHODS)}")

    if problems:
        # An empty cart gets its own stable type; errors[] still lists every bad field.
        raise (errors.empty_cart(problems) if cart_is_empty else errors.validation_error(problems))

    return student_id, items, address_id, payment_method


def _read_json_body():
    """Parse the request body. 415 for the wrong media type, 400 if it is not JSON."""
    raw = request.get_data()
    if raw and not request.is_json:
        raise errors.unsupported_media_type("Send the body with Content-Type: application/json.")
    if not raw.strip():
        raise errors.malformed_body("A JSON request body is required.")
    try:
        return json.loads(raw)
    except ValueError:  # includes UnicodeDecodeError; parser text is not echoed
        raise errors.malformed_body("The request body is not valid JSON.")


def _effective_method():
    return request.method


class MethodOverrideMiddleware:
    """Allow POST requests to tunnel a supported HTTP method for proxies."""
    def __init__(self, application):
        self.application = application

    def __call__(self, environ, start_response):
        if environ.get("REQUEST_METHOD", "").upper() == "POST":
            override = environ.get("HTTP_X_HTTP_METHOD_OVERRIDE", "").upper().strip()
            if override in ALLOWED_OVERRIDE_METHODS:
                environ["REQUEST_METHOD"] = override
        return self.application(environ, start_response)


def _etag_for_order(order, fmt="json"):
    """Strong validator for one representation of the order (JSON and XML bytes differ)."""
    if fmt == "xml":
        payload = to_xml(order.as_json(), "order")
    else:
        payload = json.dumps(order.as_json(), sort_keys=True, separators=(",", ":")).encode()
    return '"' + hashlib.sha256(payload).hexdigest() + '"'


def _etag_matches(header_value, order):
    """If-Match / If-None-Match: '*', or any listed tag equal to the order's ETag
    in any representation we can produce (weak prefix ignored)."""
    if not header_value:
        return False
    if header_value.strip() == "*":
        return True
    wanted = {_etag_for_order(order, fmt) for fmt in REPRESENTATIONS}
    tags = [t.strip() for t in header_value.split(",")]
    return any((t[2:] if t.startswith("W/") else t) in wanted for t in tags)


# ---------------------------------------------------------------------------
# C3/C4: content negotiation and representation
# ---------------------------------------------------------------------------
# format -> (media type for normal bodies, media type for Problem Details bodies)
REPRESENTATIONS = {
    "json": ("application/json", "application/problem+json"),
    "xml": ("application/xml", "application/problem+xml"),
}
PROBLEM_XML_NS = "urn:ietf:rfc:9457"
XML_ITEM_TAGS = {"items": "item", "errors": "error"}


def negotiate(accept_header):
    """Pick 'json' or 'xml' from an Accept header, or None if neither is acceptable.

    Honours q-values and wildcards. Absent header or */* -> JSON (the default).
    A more specific range beats a wildcard; ties go to JSON.
    """
    if accept_header is None or not accept_header.strip():
        return "json"
    ranges = []
    for part in accept_header.split(","):
        pieces = [p.strip() for p in part.split(";")]
        media = pieces[0].lower()
        if "/" not in media:
            continue
        q = 1.0
        for param in pieces[1:]:
            if param.lower().startswith("q="):
                try:
                    q = float(param[2:])
                except ValueError:
                    q = 0.0
        ranges.append((media, q))

    best_fmt, best_score = None, None
    for fmt in ("json", "xml"):  # order = tie-break preference
        media_type = REPRESENTATIONS[fmt][0]
        q_match, specificity = None, -1
        for media, q in ranges:
            if media == media_type:
                spec = 2
            elif media == "application/*":
                spec = 1
            elif media == "*/*":
                spec = 0
            else:
                continue
            if spec > specificity:
                q_match, specificity = q, spec
        if q_match is None or q_match <= 0:
            continue
        score = (q_match, specificity)
        if best_score is None or score > best_score:
            best_fmt, best_score = fmt, score
    return best_fmt


def _check_accept():
    g.fmt = "json"  # errors raised below are still rendered
    if request.method == "OPTIONS":
        return
    fmt = negotiate(request.headers.get("Accept"))
    if fmt is None:
        raise errors.not_acceptable(
            "This API can produce application/json (default) and application/xml."
        )
    g.fmt = fmt


def _xml_node(parent, tag, value):
    node = ET.SubElement(parent, tag)
    if isinstance(value, dict):
        for key, val in value.items():
            _xml_node(node, key, val)
    elif isinstance(value, list):
        child_tag = XML_ITEM_TAGS.get(tag, "item")
        for val in value:
            _xml_node(node, child_tag, val)
    elif isinstance(value, bool):
        node.text = "true" if value else "false"
    elif value is not None:
        node.text = str(value)
    return node


def to_xml(data, root_tag, item_tag=None, namespace=None):
    root = ET.Element(root_tag)
    if namespace:
        root.set("xmlns", namespace)
    if isinstance(data, list):
        for entry in data:
            _xml_node(root, item_tag or "item", entry)
    else:
        for key, val in data.items():
            _xml_node(root, key, val)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def render(data, status=200, *, is_problem=False, root="order", item_tag="order", headers=None):
    """Serialise `data` in the negotiated format and label it (C4): every body
    carries a Content-Type with charset=utf-8, errors included."""
    fmt = g.get("fmt", "json")
    media_type = REPRESENTATIONS[fmt][1 if is_problem else 0]
    if fmt == "xml":
        if is_problem:
            body = to_xml(data, "problem", namespace=PROBLEM_XML_NS)
        else:
            body = to_xml(data, root, item_tag=item_tag)
    else:
        body = (json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8")
    resp = app.response_class(body, status=status)
    resp.headers["Content-Type"] = f"{media_type}; charset=utf-8"
    for name, value in (headers or {}).items():
        resp.headers[name] = value
    return resp


def render_error(err):
    """The ONLY way an error leaves the service: ApiError -> Problem Details."""
    return render(err.body, err.status, is_problem=True, headers=err.headers)


def _require_auth():
    if _effective_method() == "OPTIONS":
        return
    authorization = request.headers.get("Authorization", "")
    expected = f"Bearer {DEMO_BEARER_TOKEN}"
    if authorization != expected:
        raise errors.unauthorized("A valid Authorization: Bearer <token> header is required.")


def _rate_limit():
    if _effective_method() == "OPTIONS":
        return
    client = request.headers.get("Authorization", request.remote_addr or "unknown")
    now = time.monotonic()
    state = _rate_state.get(client)
    if state is None or now - state["started"] >= RATE_WINDOW_SECONDS:
        state = {"started": now, "count": 0}
        _rate_state[client] = state
    if state["count"] >= RATE_LIMIT:
        retry_after = max(1, int(RATE_WINDOW_SECONDS - (now - state["started"])))
        raise errors.rate_limited(retry_after)  # carries Retry-After
    state["count"] += 1


@app.before_request
def before_request():
    # Method override is deliberately evaluated first so OPTIONS remains public.
    _check_accept()
    _require_auth()
    _rate_limit()


@app.after_request
def common_headers(response):
    # C4: no body -> no Content-Type; any body must say what it is, with a charset.
    if response.status_code in (204, 304):
        response.headers.pop("Content-Type", None)
    else:
        content_type = response.headers.get("Content-Type", "")
        if content_type and "charset" not in content_type.lower():
            response.headers["Content-Type"] = f"{content_type}; charset=utf-8"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Accept, Idempotency-Key, If-None-Match, If-Match, X-HTTP-Method-Override"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    response.headers["Access-Control-Expose-Headers"] = "Location, ETag, Retry-After, Idempotency-Replayed"
    response.headers["Vary"] = "Accept, Origin, Accept-Encoding"

    # Lightweight gzip support for larger responses when requested.
    if ("gzip" in request.headers.get("Accept-Encoding", "").lower()
            and response.status_code not in (204, 304)
            and response.direct_passthrough is False
            and response.content_length is not None
            and response.content_length >= 1024
            and response.headers.get("Content-Encoding") is None):
        response.set_data(gzip.compress(response.get_data()))
        response.headers["Content-Encoding"] = "gzip"
        response.headers.pop("Content-Length", None)

    client = request.headers.get("Authorization", request.remote_addr or "unknown")
    state = _rate_state.get(client)
    remaining = max(0, RATE_LIMIT - state["count"]) if state else RATE_LIMIT
    response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    return response


def _replay(original):
    """Re-send a stored result. Stored as data (status, body), re-rendered for THIS
    request's Accept, so a replay can be XML even if the first call was JSON."""
    status = original["status"]
    resp = render(original["body"], status, is_problem=status >= 400, headers=original["headers"])
    resp.headers["Idempotency-Replayed"] = "true"
    return resp


@app.route("/orders", methods=["POST"], provide_automatic_options=False)
def create_order():
    if _effective_method() != "POST":
        raise errors.method_not_allowed("Method override is only a compatibility tunnel; use the documented endpoint method.")

    idem_key = request.headers.get("Idempotency-Key")
    data = _read_json_body()

    if idem_key:
        existing = store.find_by_idempotency_key(idem_key)
        if existing:
            # Reusing a key with a different operation/body is unsafe.
            if store.idempotency_payload(idem_key) != store.canonical_payload(data):
                raise errors.idempotency_conflict("This Idempotency-Key was already used with a different request body.")
            original = store.idempotency_result(idem_key)
            if original:
                return _replay(original)
            return _replay({"status": 201, "body": existing.as_json(),
                            "headers": {"Location": f"/orders/{existing.order_id}"}})

    # C2: validate everything first (one 422 listing all bad fields), then act.
    student_id, items, address_id, payment_method = validate_create_order(data)

    if not store.validate_address(student_id, address_id):
        raise errors.invalid_address(
            f"Address {address_id} does not exist or does not belong to {student_id}.",
            [{"field": "addressId", "message": "does not exist or does not belong to this student"}],
        )

    order_items = []
    total = 0.0
    unavailable, unavailable_ids = [], []
    for index, entry in enumerate(items):
        available, unit_price = store.check_item(entry["itemId"], entry["quantity"])
        if not available:
            unavailable.append({"field": f"items[{index}].itemId",
                                "message": f"item {entry['itemId']} is unavailable or has insufficient stock"})
            unavailable_ids.append(str(entry["itemId"]))
            continue
        order_items.append(OrderItem(entry["itemId"], entry["quantity"], unit_price))
        total += unit_price * entry["quantity"]
    if unavailable:
        raise errors.item_unavailable(
            f"Item(s) {', '.join(unavailable_ids)} cannot be ordered right now.", unavailable)

    order_id = store.next_order_id()
    order = Order(
        order_id=order_id,
        student_id=student_id,
        address_id=address_id,
        payment_method=payment_method,
        items=order_items,
        total_amount=total,
        status="PENDING",
        idempotency_key=idem_key,
    )

    # B4: the Payments call is the risky part. Whatever goes wrong inside it is
    # logged here with full detail; the client only ever gets a mapped, clean error.
    try:
        result = charge_payment(
            order_id=order_id,
            student_id=student_id,
            amount=total,
            payment_method=payment_method,
            idempotency_key=idem_key or f"order-{order_id}",
        )
    except PaymentDeclined as exc:
        app.logger.warning("payment declined order=%s upstream_detail=%r", order_id, exc.detail)
        order.status = "CANCELLED"
        store.save_order(order, canonical_payload=data)
        err = errors.payment_declined()  # permanent: remembered, a replay gets the same 422
        if idem_key:
            store.save_idempotency_result(idem_key, err.status, err.body)
        raise err
    except PaymentServiceUnavailable as exc:
        # Upstream text (host, port, library errors) goes to the log, not the client.
        app.logger.error("payments unavailable order=%s cause=%s", order_id, exc)
        # Transient: deliberately NOT remembered under the Idempotency-Key, so the
        # client's retry with the same key is a fresh attempt instead of a cached 503.
        raise errors.payment_unavailable()

    order.status = "PLACED"
    order.transaction_id = result.get("transactionId")
    store.save_order(order, canonical_payload=data)

    location = {"Location": f"/orders/{order.order_id}"}
    if idem_key:
        store.save_idempotency_result(idem_key, 201, order.as_json(), location)
    return render(order.as_json(), 201, headers=location)


@app.route("/orders/<int:order_id>", methods=["GET"], provide_automatic_options=False)
def get_order(order_id):
    if _effective_method() not in ("GET", "HEAD"):
        raise errors.method_not_allowed("Use GET for retrieving an order.", "GET, HEAD, OPTIONS")
    order = store.get_order(order_id)
    if order is None:
        raise errors.order_not_found(order_id)

    fmt = g.fmt
    etag = _etag_for_order(order, fmt)
    if _etag_matches(request.headers.get("If-None-Match"), order):
        resp = app.response_class(status=304)
        resp.headers["ETag"] = etag
        resp.headers["Cache-Control"] = "private, max-age=30"
        return resp

    resp = render(order.as_json(), 200)
    resp.headers["ETag"] = etag
    resp.headers["Cache-Control"] = "private, max-age=30"
    return resp


@app.route("/orders", methods=["GET"], provide_automatic_options=False)
def list_orders():
    if _effective_method() not in ("GET", "HEAD"):
        raise errors.method_not_allowed("Use GET for listing orders.", "GET, HEAD, OPTIONS")

    # Same rule as the POST body: check every parameter, report all bad ones in one 422.
    problems = []
    status = request.args.get("status")
    if status is not None and status not in ("PENDING", "PLACED", "CANCELLED"):
        problems.append({"field": "status", "message": "must be one of PENDING, PLACED, CANCELLED"})
    student_id = request.args.get("studentId")
    sort_by = request.args.get("sortBy", "orderId")
    if sort_by not in {"orderId", "total", "createdAt", "status"}:
        problems.append({"field": "sortBy", "message": "must be one of orderId, total, createdAt, status"})
    sort_order = request.args.get("sortOrder", "asc").lower()
    if sort_order not in {"asc", "desc"}:
        problems.append({"field": "sortOrder", "message": "must be asc or desc"})
    page, page_size = 1, 10
    try:
        page = int(request.args.get("page", "1"))
        if page < 1:
            problems.append({"field": "page", "message": "must be an integer >= 1"})
    except ValueError:
        problems.append({"field": "page", "message": "must be an integer >= 1"})
    try:
        page_size = int(request.args.get("pageSize", "10"))
        if not 1 <= page_size <= 100:
            problems.append({"field": "pageSize", "message": "must be an integer between 1 and 100"})
    except ValueError:
        problems.append({"field": "pageSize", "message": "must be an integer between 1 and 100"})
    if problems:
        raise errors.validation_error(problems, source="query")

    results = store.list_orders(student_id=student_id, status=status)
    key_map = {
        "orderId": lambda o: o.order_id,
        "total": lambda o: o.total_amount,
        "createdAt": lambda o: o.created_at,
        "status": lambda o: o.status,
    }
    results = sorted(results, key=key_map[sort_by], reverse=(sort_order == "desc"))
    start = (page - 1) * page_size
    page_items = [o.as_json() for o in results[start:start + page_size]]
    return render(page_items, 200, root="orders", item_tag="order")


@app.route("/orders/<int:order_id>/cancellation", methods=["POST"], provide_automatic_options=False)
def cancel_order(order_id):
    if _effective_method() != "POST":
        raise errors.method_not_allowed("Use POST /orders/{orderId}/cancellation to cancel an order.")
    order = store.get_order(order_id)
    if order is None:
        raise errors.order_not_found(order_id)

    if_match = request.headers.get("If-Match")
    if if_match and not _etag_matches(if_match, order):
        raise errors.precondition_failed("The order changed after the supplied If-Match ETag; fetch it again before updating.")

    if order.status not in CANCELLABLE_STATUSES:
        raise errors.illegal_transition(
            f"Order {order_id} is '{order.status}' and cannot move to 'CANCELLED'."
        )

    order.status = "CANCELLED"
    store.save_order(order)
    resp = render(order.as_json(), 200)
    resp.headers["ETag"] = _etag_for_order(order, g.fmt)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/orders", methods=["OPTIONS"])
@app.route("/orders/<int:order_id>", methods=["OPTIONS"])
@app.route("/orders/<int:order_id>/cancellation", methods=["OPTIONS"])
def options_order(order_id=None):
    if request.path.endswith("/cancellation"):
        allow = "POST, OPTIONS"
    elif order_id is None:
        allow = "GET, POST, OPTIONS"
    else:
        allow = "GET, OPTIONS"
    resp = app.response_class(status=204)
    resp.headers["Allow"] = allow
    resp.headers["Access-Control-Allow-Methods"] = allow
    resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Accept, Idempotency-Key, If-None-Match, If-Match, X-HTTP-Method-Override"
    return resp


# ---------------------------------------------------------------------------
# B1/B4: every failure leaves through render_error()
# ---------------------------------------------------------------------------
@app.errorhandler(ApiError)
def handle_api_error(err):
    return render_error(err)


@app.errorhandler(HTTPException)
def handle_http_exception(exc):
    """Framework-level errors (unknown URL, wrong method, ...) get the same shape."""
    if exc.code == 404:
        err = ApiError("not-found", "The requested URL does not exist.")
    elif exc.code == 405:
        allow = ", ".join(sorted(exc.valid_methods or [])) or None
        err = errors.method_not_allowed("The HTTP method is not supported for this resource.", allow)
    elif exc.code == 400:
        err = errors.malformed_body("The request could not be parsed.")
    else:
        err = ApiError("http-error", exc.description or "The request could not be processed.",
                       status=exc.code, title=exc.name)
    return render_error(err)


@app.errorhandler(Exception)
def handle_unexpected(exc):
    """Last line of defence. Full detail (type, message, stack trace) goes to the
    server log under an errorId; the client sees only a generic 500 and that id."""
    error_id = uuid.uuid4().hex[:12]
    app.logger.exception("unhandled error errorId=%s %s %s", error_id, request.method, request.path)
    return render_error(errors.internal_error(error_id))


app.wsgi_app = MethodOverrideMiddleware(app.wsgi_app)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(port=int(os.environ.get("PORT", "5000")), debug=False)
