"""Problem Details (RFC 9457 / 7807) errors for CampusEats.

Every failure the service can produce is built here with problem() and
raised as an ApiError, so there is exactly ONE error shape:

    { "type": "...", "title": "...", "status": 4xx/5xx, "detail": "...",
      "errors": [ {"field": "...", "message": "..."} ]   # only on 422 }

The type catalogue (stable strings, never renamed once published) lives in
TYPES below and is documented in NOTES.md and openapi.yaml.
"""

BASE_TYPE = "https://campuseats.example.com/errors"

# slug -> (title, status). The slug is the stable part of the type URI.
TYPES = {
    "malformed-body":              ("Malformed request body", 400),
    "unauthorized":                ("Unauthorized", 401),
    "not-found":                   ("Not found", 404),
    "order-not-found":             ("Order not found", 404),
    "method-not-allowed":          ("Method not allowed", 405),
    "not-acceptable":              ("Not acceptable", 406),
    "illegal-transition":          ("Illegal state transition", 409),
    "idempotency-conflict":        ("Idempotency key conflict", 409),
    "precondition-failed":         ("Precondition failed", 412),
    "unsupported-media-type":      ("Unsupported media type", 415),
    "validation-error":            ("Validation failed", 422),
    "empty-cart":                  ("Empty cart", 422),
    "invalid-address":             ("Invalid delivery address", 422),
    "item-unavailable":            ("Item unavailable", 422),
    "payment-declined":            ("Payment declined", 422),
    "rate-limited":                ("Too many requests", 429),
    "internal-error":              ("Internal server error", 500),
    "payment-service-unavailable": ("Payment service unavailable", 503),
    "http-error":                  ("HTTP error", 500),   # fallback for other framework errors
}


def problem(slug, detail, status=None, title=None, errors=None, **extra):
    """Build a Problem Details dict. The single place error bodies are made."""
    default_title, default_status = TYPES.get(slug, ("Error", status or 500))
    body = {
        "type": f"{BASE_TYPE}/{slug}",
        "title": title or default_title,
        "status": status or default_status,
        "detail": detail,
    }
    if errors:
        body["errors"] = errors
    body.update(extra)
    return body


class ApiError(Exception):
    """An error that is safe to show the client. `headers` are extra response
    headers (Retry-After, WWW-Authenticate, Allow)."""

    def __init__(self, slug, detail, errors=None, headers=None, **extra):
        super().__init__(detail)
        self.body = problem(slug, detail, errors=errors, **extra)
        self.status = self.body["status"]
        self.headers = dict(headers or {})


def malformed_body(detail):
    return ApiError("malformed-body", detail)


def unsupported_media_type(detail):
    return ApiError("unsupported-media-type", detail)


def validation_error(field_errors, source="body"):
    """422 listing every bad field. `source` is "body" or "query" (wording only)."""
    n = len(field_errors)
    if source == "query":
        subject, noun = "The query string", "parameter"
    else:
        subject, noun = "The request body", "field"
    return ApiError(
        "validation-error",
        f"{subject} has {n} invalid {noun}{'s' if n != 1 else ''}. See 'errors'.",
        errors=field_errors,
    )


def empty_cart(field_errors):
    return ApiError("empty-cart", "An order must contain at least one item.", errors=field_errors)


def invalid_address(detail, field_errors=None):
    return ApiError("invalid-address", detail, errors=field_errors)


def item_unavailable(detail, field_errors=None):
    return ApiError("item-unavailable", detail, errors=field_errors)


def payment_declined(detail="The payment provider declined the charge. No order was placed."):
    return ApiError("payment-declined", detail)


def payment_unavailable(retry_after=5):
    return ApiError(
        "payment-service-unavailable",
        "The payment service is temporarily unavailable. Retry later.",
        headers={"Retry-After": str(retry_after)},
    )


def order_not_found(order_id):
    return ApiError("order-not-found", f"Order {order_id} does not exist.")


def illegal_transition(detail):
    return ApiError("illegal-transition", detail)


def unauthorized(detail):
    return ApiError("unauthorized", detail,
                    headers={"WWW-Authenticate": 'Bearer realm="CampusEats Orders"'})


def not_acceptable(detail):
    return ApiError("not-acceptable", detail)


def method_not_allowed(detail, allow=None):
    return ApiError("method-not-allowed", detail, headers={"Allow": allow} if allow else None)


def precondition_failed(detail):
    return ApiError("precondition-failed", detail)


def idempotency_conflict(detail):
    return ApiError("idempotency-conflict", detail)


def rate_limited(retry_after):
    return ApiError(
        "rate-limited",
        f"Rate limit exceeded. Retry after {retry_after} seconds.",
        headers={"Retry-After": str(retry_after)},
    )


def internal_error(error_id):
    # Deliberately generic: no exception text, no stack, no SQL, no paths.
    return ApiError(
        "internal-error",
        "An unexpected error occurred. If it persists, quote the errorId to support.",
        errorId=error_id,
    )
