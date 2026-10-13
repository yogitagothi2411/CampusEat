"""CampusEats Orders Service - Assignment 4 HTTP Methods & Headers."""

import gzip
import hashlib
import json
import os
import time
from functools import wraps

from flask import Flask, jsonify, request

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


def validate_create_order(data):
    if not isinstance(data, dict):
        raise errors.malformed_body("Request body must be a JSON object.")

    student_id = data.get("studentId")
    if not isinstance(student_id, str) or not student_id:
        raise errors.malformed_body("'studentId' is required and must be a non-empty string.")

    items = data.get("items")
    if not isinstance(items, list) or len(items) == 0:
        raise errors.empty_cart()

    for entry in items:
        if not isinstance(entry, dict):
            raise errors.malformed_body("Each entry in 'items' must be an object.")
        if not isinstance(entry.get("itemId"), int):
            raise errors.malformed_body("Each item requires an integer 'itemId'.")
        qty = entry.get("quantity")
        if not isinstance(qty, int) or qty <= 0:
            raise errors.malformed_body("Each item requires a positive integer 'quantity'.")

    address_id = data.get("addressId")
    if not isinstance(address_id, int):
        raise errors.malformed_body("'addressId' is required and must be an integer.")

    payment_method = data.get("paymentMethod")
    if payment_method not in VALID_PAYMENT_METHODS:
        raise errors.malformed_body(
            f"'paymentMethod' must be one of {sorted(VALID_PAYMENT_METHODS)}."
        )

    return student_id, items, address_id, payment_method


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


def _etag_for_order(order):
    payload = json.dumps(order.as_json(), sort_keys=True, separators=(",", ":")).encode()
    return '"' + hashlib.sha256(payload).hexdigest() + '"'


def _check_accept():
    accept = request.headers.get("Accept")
    if not accept or "*/*" in accept:
        return
    accepted = [part.split(";", 1)[0].strip().lower() for part in accept.split(",")]
    if "application/json" not in accepted:
        raise errors.not_acceptable("This API supports application/json responses only.")


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
        err = errors.rate_limited(f"Rate limit exceeded. Retry after {retry_after} seconds.")
        err.retry_after = retry_after
        raise err
    state["count"] += 1


@app.before_request
def before_request():
    # Method override is deliberately evaluated first so OPTIONS remains public.
    _check_accept()
    _require_auth()
    _rate_limit()


@app.after_request
def common_headers(response):
    if response.status_code not in (204, 304):
        response.headers.setdefault("Content-Type", "application/json")
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Accept, Idempotency-Key, If-None-Match, If-Match, X-HTTP-Method-Override"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    response.headers["Vary"] = "Accept, Origin, Accept-Encoding"

    # Lightweight gzip support for larger JSON responses when requested.
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


@app.route("/orders", methods=["POST"])
def create_order():
    if _effective_method() != "POST":
        raise errors.method_not_allowed("Method override is only a compatibility tunnel; use the documented endpoint method.")

    idem_key = request.headers.get("Idempotency-Key")
    if request.data and not request.is_json:
        raise errors.malformed_body("Requests with a body must use Content-Type: application/json.")
    data = request.get_json(silent=True)

    if idem_key:
        existing = store.find_by_idempotency_key(idem_key)
        if existing:
            # Reusing a key with a different operation/body is unsafe.
            if store.idempotency_payload(idem_key) != store.canonical_payload(data):
                raise errors.idempotency_conflict("This Idempotency-Key was already used with a different request body.")
            original = store.idempotency_result(idem_key)
            if original:
                resp = jsonify(original["body"])
                resp.status_code = original["status"]
                for name, value in original["headers"].items():
                    resp.headers[name] = value
                resp.headers["Idempotency-Replayed"] = "true"
                return resp
            resp = jsonify(existing.as_json())
            resp.status_code = 201
            resp.headers["Location"] = f"/orders/{existing.order_id}"
            resp.headers["Idempotency-Replayed"] = "true"
            return resp

    student_id, items, address_id, payment_method = validate_create_order(data)

    if not store.validate_address(student_id, address_id):
        raise errors.invalid_address(
            f"Address {address_id} does not exist or does not belong to {student_id}."
        )

    order_items = []
    total = 0.0
    for entry in items:
        available, unit_price = store.check_item(entry["itemId"], entry["quantity"])
        if not available:
            raise errors.item_unavailable(f"Item {entry['itemId']} is unavailable.")
        order_items.append(OrderItem(entry["itemId"], entry["quantity"], unit_price))
        total += unit_price * entry["quantity"]

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

    try:
        result = charge_payment(
            order_id=order_id,
            student_id=student_id,
            amount=total,
            payment_method=payment_method,
            idempotency_key=idem_key or f"order-{order_id}",
        )
    except PaymentDeclined as exc:
        order.status = "CANCELLED"
        store.save_order(order, canonical_payload=data)
        if idem_key:
            store.save_idempotency_result(idem_key, 422, errors.payment_declined(str(exc)).body)
        raise errors.payment_declined(str(exc))
    except PaymentServiceUnavailable as exc:
        order.status = "CANCELLED"
        store.save_order(order, canonical_payload=data)
        if idem_key:
            store.save_idempotency_result(idem_key, 503, errors.payment_unavailable(str(exc)).body)
        raise errors.payment_unavailable(str(exc))

    order.status = "PLACED"
    order.transaction_id = result.get("transactionId")
    store.save_order(order, canonical_payload=data)

    resp = jsonify(order.as_json())
    resp.status_code = 201
    resp.headers["Location"] = f"/orders/{order.order_id}"
    if idem_key:
        store.save_idempotency_result(idem_key, 201, order.as_json(), {"Location": f"/orders/{order.order_id}"})
    return resp


@app.route("/orders/<int:order_id>", methods=["GET"])
def get_order(order_id):
    if _effective_method() != "GET":
        raise errors.method_not_allowed("Use GET for retrieving an order.")
    order = store.get_order(order_id)
    if order is None:
        raise errors.order_not_found(order_id)

    etag = _etag_for_order(order)
    if request.headers.get("If-None-Match") == etag or request.headers.get("If-None-Match") == "*":
        resp = app.response_class(status=304)
        resp.headers["ETag"] = etag
        resp.headers["Cache-Control"] = "private, max-age=30"
        return resp

    resp = jsonify(order.as_json())
    resp.status_code = 200
    resp.headers["ETag"] = etag
    resp.headers["Cache-Control"] = "private, max-age=30"
    return resp


@app.route("/orders", methods=["GET"])
def list_orders():
    if _effective_method() != "GET":
        raise errors.method_not_allowed("Use GET for listing orders.")
    status = request.args.get("status")
    if status is not None and status not in ("PENDING", "PLACED", "CANCELLED"):
        raise errors.malformed_body(
            "'status' query parameter must be one of PENDING, PLACED, CANCELLED."
        )
    student_id = request.args.get("studentId")
    sort_by = request.args.get("sortBy", "orderId")
    sort_order = request.args.get("sortOrder", "asc").lower()
    if sort_by not in {"orderId", "total", "createdAt", "status"}:
        raise errors.malformed_body("'sortBy' must be one of orderId, total, createdAt, status.")
    if sort_order not in {"asc", "desc"}:
        raise errors.malformed_body("'sortOrder' must be asc or desc.")
    try:
        page = int(request.args.get("page", "1"))
        page_size = int(request.args.get("pageSize", "10"))
    except ValueError:
        raise errors.malformed_body("'page' and 'pageSize' must be integers.")
    if page < 1 or page_size < 1 or page_size > 100:
        raise errors.malformed_body("'page' must be >= 1 and 'pageSize' must be between 1 and 100.")

    results = store.list_orders(student_id=student_id, status=status)
    key_map = {
        "orderId": lambda o: o.order_id,
        "total": lambda o: o.total_amount,
        "createdAt": lambda o: o.created_at,
        "status": lambda o: o.status,
    }
    results = sorted(results, key=key_map[sort_by], reverse=(sort_order == "desc"))
    start = (page - 1) * page_size
    end = start + page_size
    return jsonify([o.as_json() for o in results[start:end]]), 200


@app.route("/orders/<int:order_id>/cancellation", methods=["POST"])
def cancel_order(order_id):
    if _effective_method() != "POST":
        raise errors.method_not_allowed("Use POST /orders/{orderId}/cancellation to cancel an order.")
    order = store.get_order(order_id)
    if order is None:
        raise errors.order_not_found(order_id)

    current_etag = _etag_for_order(order)
    if_match = request.headers.get("If-Match")
    if if_match and if_match != current_etag and if_match != "*":
        raise errors.precondition_failed("The order changed after the supplied If-Match ETag; fetch it again before updating.")

    if order.status not in CANCELLABLE_STATUSES:
        raise errors.cannot_cancel(
            f"Order {order_id} is '{order.status}' and can no longer be cancelled."
        )

    order.status = "CANCELLED"
    store.save_order(order)
    resp = jsonify(order.as_json())
    resp.status_code = 200
    resp.headers["ETag"] = _etag_for_order(order)
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


@app.errorhandler(ApiError)
def handle_api_error(err):
    resp = jsonify(err.body)
    resp.status_code = err.status
    if getattr(err, "retry_after", None):
        resp.headers["Retry-After"] = str(err.retry_after)
    if err.status == 401:
        resp.headers["WWW-Authenticate"] = 'Bearer realm="CampusEats Orders"'
    return resp


@app.errorhandler(400)
def handle_400(_err):
    return jsonify(errors.problem("bad-request", "Bad request", 400, "The request could not be parsed.")), 400


@app.errorhandler(404)
def handle_404(_err):
    return jsonify(errors.problem("not-found", "Not found", 404, "The requested URL does not exist.")), 404


@app.errorhandler(405)
def handle_405(_err):
    return jsonify(errors.problem("method-not-allowed", "Method not allowed", 405, "The HTTP method is not supported for this resource.")), 405


app.wsgi_app = MethodOverrideMiddleware(app.wsgi_app)

if __name__ == "__main__":
    app.run(port=5000, debug=False)
