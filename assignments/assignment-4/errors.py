"""
errors.py
One error shape for the whole Orders service (Part C6).

Every failure response, from every endpoint, is built by problem().
No endpoint is allowed to hand-roll its own error JSON.
"""

BASE_TYPE = "https://campuseats.example.com/errors"


def problem(slug, title, status, detail):
    """
    Build an RFC-7807-style problem body.

    slug   -> short machine id, e.g. "empty-cart"   (becomes the `type` URL)
    title  -> short human summary, e.g. "Empty cart"
    status -> HTTP status code (int), repeated in the body on purpose
    detail -> one sentence describing *this* failure
    """
    return {
        "type": f"{BASE_TYPE}/{slug}",
        "title": title,
        "status": status,
        "detail": detail,
    }


class ApiError(Exception):
    """
    Raised anywhere in the request-handling code. app.py's error handler
    catches this and turns it into a problem() response with the right
    status code. This is what keeps every endpoint using the same shape --
    handlers never build their own error dict, they just raise ApiError.
    """

    def __init__(self, slug, title, status, detail):
        super().__init__(detail)
        self.body = problem(slug, title, status, detail)
        self.status = status


# Convenience constructors for the domain error codes carried over from
# the Assignment 2 ORDERS CONTRACT (EMPTY_CART, INVALID_ADDRESS,
# ITEM_UNAVAILABLE, PAYMENT_DECLINED, ORDER_NOT_FOUND, CANNOT_CANCEL).
# Mapping chosen and justified in NOTES.md / Q2.

def malformed_body(detail):
    return ApiError("malformed-body", "Malformed request body", 400, detail)


def empty_cart():
    return ApiError(
        "empty-cart", "Empty cart", 400,
        "An order must contain at least one item."
    )


def invalid_address(detail):
    return ApiError("invalid-address", "Invalid delivery address", 422, detail)


def item_unavailable(detail):
    return ApiError("item-unavailable", "Item unavailable", 422, detail)


def payment_declined(detail):
    return ApiError("payment-declined", "Payment declined", 422, detail)


def payment_unavailable(detail):
    return ApiError(
        "payment-service-unavailable", "Payment service unavailable", 503, detail
    )


def order_not_found(order_id):
    return ApiError(
        "order-not-found", "Order not found", 404,
        f"Order {order_id} does not exist."
    )


def cannot_cancel(detail):
    return ApiError("order-conflict", "Order cannot be cancelled", 409, detail)
