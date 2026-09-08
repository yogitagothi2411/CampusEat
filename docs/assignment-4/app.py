"""
app.py
CampusEats Orders Service (Assignment 4).

REST rebuild of the Assignment 2 ORDERS CONTRACT operations
(addToCart, placeOrder, getOrder, cancelOrder) as four HTTP endpoints:

    POST   /orders                       (placeOrder)
    GET    /orders/{orderId}             (getOrder)
    GET    /orders?studentId=&status=    (filtered list)
    POST   /orders/{orderId}/cancellation (cancelOrder)

Run:
    export PAYMENTS_URL=http://localhost:5001
    python3 app.py
"""

from flask import Flask, jsonify, request

import errors
import store
from errors import ApiError
from models import Order, OrderItem
from payment_client import PaymentDeclined, PaymentServiceUnavailable, charge_payment

app = Flask(__name__)

VALID_PAYMENT_METHODS = {"CARD", "UPI", "WALLET", "COD"}
CANCELLABLE_STATUSES = {"PENDING", "PLACED"}


# ---------------------------------------------------------------------
# C4: request validation, done by hand (this is what the Assignment 3
# XML Schema used to do for free -- see NOTES.md Q4)
# ---------------------------------------------------------------------
def validate_create_order(data):
    if not isinstance(data, dict):
        raise errors.malformed_body("Request body must be a JSON object.")

    student_id = data.get("studentId")
    if not isinstance(student_id, str) or not student_id:
        raise errors.malformed_body("'studentId' is required and must be a non-empty string.")

    items = data.get("items")
    if not isinstance(items, list) or len(items) == 0:
        # Assignment 2's EMPTY_CART: items[] missing or empty.
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


# ---------------------------------------------------------------------
# POST /orders  -- create (placeOrder), C7: idempotency-key supported
# ---------------------------------------------------------------------
@app.post("/orders")
def create_order():
    idem_key = request.headers.get("Idempotency-Key")

    # Repeat of an earlier request: return the original result, do not redo the work.
    if idem_key:
        existing = store.find_by_idempotency_key(idem_key)
        if existing:
            resp = jsonify(existing.as_json())
            resp.status_code = 201
            resp.headers["Location"] = f"/orders/{existing.order_id}"
            return resp

    data = request.get_json(silent=True)
    student_id, items, address_id, payment_method = validate_create_order(data)

    # Step 2 of placeOrder: validate the address (Account Service, simulated).
    if not store.validate_address(student_id, address_id):
        raise errors.invalid_address(
            f"Address {address_id} does not exist or does not belong to {student_id}."
        )

    # Step 3: check each item and fetch its live price (Catalogue Service, simulated).
    # Price is computed server-side and never taken from the client body.
    order_items = []
    total = 0.0
    for entry in items:
        available, unit_price = store.check_item(entry["itemId"], entry["quantity"])
        if not available:
            raise errors.item_unavailable(f"Item {entry['itemId']} is unavailable.")
        order_items.append(OrderItem(entry["itemId"], entry["quantity"], unit_price))
        total += unit_price * entry["quantity"]

    # Step 5: create the order row with status PENDING.
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

    # Step 6: charge the payment (Part D -- the one real, hardened outbound call).
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
        store.save_order(order)
        raise errors.payment_declined(str(exc))
    except PaymentServiceUnavailable as exc:
        # D3 fallback: fail safely rather than pretend the order was placed.
        order.status = "CANCELLED"
        store.save_order(order)
        raise errors.payment_unavailable(str(exc))

    # Step 7: charge succeeded -> PLACED.
    order.status = "PLACED"
    order.transaction_id = result.get("transactionId")
    store.save_order(order)

    resp = jsonify(order.as_json())
    resp.status_code = 201
    resp.headers["Location"] = f"/orders/{order.order_id}"
    return resp


# ---------------------------------------------------------------------
# GET /orders/{orderId} -- read one (getOrder)
# ---------------------------------------------------------------------
@app.get("/orders/<int:order_id>")
def get_order(order_id):
    order = store.get_order(order_id)
    if order is None:
        raise errors.order_not_found(order_id)
    return jsonify(order.as_json()), 200


# ---------------------------------------------------------------------
# GET /orders?studentId=&status= -- filtered list
# ---------------------------------------------------------------------
@app.get("/orders")
def list_orders():
    status = request.args.get("status")
    if status is not None and status not in ("PENDING", "PLACED", "CANCELLED"):
        raise errors.malformed_body(
            "'status' query parameter must be one of PENDING, PLACED, CANCELLED."
        )
    student_id = request.args.get("studentId")
    results = store.list_orders(student_id=student_id, status=status)
    return jsonify([o.as_json() for o in results]), 200


# ---------------------------------------------------------------------
# POST /orders/{orderId}/cancellation -- state-changing sub-resource (cancelOrder)
# ---------------------------------------------------------------------
@app.post("/orders/<int:order_id>/cancellation")
def cancel_order(order_id):
    order = store.get_order(order_id)
    if order is None:
        raise errors.order_not_found(order_id)

    if order.status not in CANCELLABLE_STATUSES:
        # Assignment 2's CANNOT_CANCEL.
        raise errors.cannot_cancel(
            f"Order {order_id} is '{order.status}' and can no longer be cancelled."
        )

    order.status = "CANCELLED"
    store.save_order(order)
    return jsonify(order.as_json()), 200


# ---------------------------------------------------------------------
# C6: one error shape everywhere
# ---------------------------------------------------------------------
@app.errorhandler(ApiError)
def handle_api_error(err):
    return jsonify(err.body), err.status


@app.errorhandler(404)
def handle_404(_err):
    return jsonify(errors.problem(
        "not-found", "Not found", 404, "The requested URL does not exist."
    )), 404


if __name__ == "__main__":
    app.run(port=5000, debug=False)
