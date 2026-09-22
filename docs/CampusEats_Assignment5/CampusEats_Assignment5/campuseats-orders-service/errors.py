"""Common RFC-7807-style JSON error responses for CampusEats."""

BASE_TYPE = "https://campuseats.example.com/errors"


def problem(slug, title, status, detail):
    return {"type": f"{BASE_TYPE}/{slug}", "title": title, "status": status, "detail": detail}


class ApiError(Exception):
    def __init__(self, slug, title, status, detail):
        super().__init__(detail)
        self.body = problem(slug, title, status, detail)
        self.status = status


def malformed_body(detail):
    return ApiError("malformed-body", "Malformed request body", 400, detail)


def empty_cart():
    return ApiError("empty-cart", "Empty cart", 400, "An order must contain at least one item.")


def invalid_address(detail):
    return ApiError("invalid-address", "Invalid delivery address", 422, detail)


def item_unavailable(detail):
    return ApiError("item-unavailable", "Item unavailable", 422, detail)


def payment_declined(detail):
    return ApiError("payment-declined", "Payment declined", 422, detail)


def payment_unavailable(detail):
    return ApiError("payment-service-unavailable", "Payment service unavailable", 503, detail)


def order_not_found(order_id):
    return ApiError("order-not-found", "Order not found", 404, f"Order {order_id} does not exist.")


def cannot_cancel(detail):
    return ApiError("order-conflict", "Order cannot be cancelled", 409, detail)


def unauthorized(detail):
    return ApiError("unauthorized", "Unauthorized", 401, detail)


def not_acceptable(detail):
    return ApiError("not-acceptable", "Not acceptable", 406, detail)


def method_not_allowed(detail):
    return ApiError("method-not-allowed", "Method not allowed", 405, detail)


def precondition_failed(detail):
    return ApiError("precondition-failed", "Precondition failed", 412, detail)


def idempotency_conflict(detail):
    return ApiError("idempotency-conflict", "Idempotency key conflict", 409, detail)


def rate_limited(detail):
    return ApiError("rate-limited", "Too many requests", 429, detail)
