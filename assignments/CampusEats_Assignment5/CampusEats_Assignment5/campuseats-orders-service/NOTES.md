# CS543 – Web Services – Assignment 4

## CampusEats Orders Service – HTTP Methods & Headers

### Team Members

| Roll No | Name |
|---|---|
| 20251651107 | Yogita Gothi |
| 20251651047 | Janvi Goud |
| 20251651086 | Shreya Verma |
| 20251651088 | Sonali Choudhary |

**Team ID:** 23

---

# Part A – HTTP Methods

## A1. CampusEats Method Map

| Method | Endpoint | Purpose | Safe? | Idempotent? | Success |
|---|---|---|---|---|---|
| GET | `/orders` | List/filter orders using `studentId` and `status` query parameters | Yes | Yes | 200 |
| GET | `/orders/{orderId}` | Read one order | Yes | Yes | 200 |
| POST | `/orders` | Create/place an order and charge payment | No | Not inherently; made retry-safe with `Idempotency-Key` | 201 |
| POST | `/orders/{orderId}/cancellation` | Change order state to CANCELLED | No | Not inherently; guarded with ETag/If-Match | 200 |
| OPTIONS | `/orders`, `/orders/{orderId}`, cancellation | Discover allowed methods / CORS preflight | Yes | Yes | 204 |

Cancellation is intentionally a **POST sub-resource**. We do not use `POST /cancelOrder` because the URL should identify the order resource and its cancellation sub-resource.

## A2. Non-CRUD Actions

`cancelOrder()` becomes:

```text
POST /orders/{orderId}/cancellation
```

The order is retained for history; cancellation changes its state instead of physically deleting it.

## A3. Safe and Idempotent Operations

- GET is safe and idempotent because it only reads state.
- OPTIONS is safe and idempotent because it only describes the interface.
- POST `/orders` is not naturally idempotent because a retry could create a second order/payment. `Idempotency-Key` makes the same retry return the original result.
- Cancellation is a state-changing POST. `If-Match` prevents updating an order from a stale representation.

## A4. List, Filter, Sort and Pagination

The list resource stays a GET and supports filtering, sorting and pagination through query parameters:

```text
GET /orders?studentId=STU-778812&status=PLACED&sortBy=total&sortOrder=desc&page=1&pageSize=10
```

Supported query parameters are `studentId`, `status`, `sortBy`, `sortOrder`, `page` and `pageSize`. The operation remains a pure read.

## A5. OPTIONS and Method Override

`OPTIONS` is implemented on the three order resources. It returns `204 No Content` and an `Allow` header such as:

```text
Allow: GET, POST, OPTIONS
```

CORS preflight headers are also returned.

`X-HTTP-Method-Override` is supported as a compatibility tunnel for POST-only clients/proxies. The header must contain a supported HTTP method; unsupported combinations result in a normal HTTP method error.

## A6. Complete HTTP Exchange Example

```http
POST /orders HTTP/1.1
Host: localhost:5000
Authorization: Bearer campuseats-demo-token
Content-Type: application/json
Accept: application/json
Idempotency-Key: demo-order-001

{
  "studentId": "STU-778812",
  "items": [{"itemId": 101, "quantity": 2}],
  "addressId": 10,
  "paymentMethod": "CARD"
}

HTTP/1.1 201 Created
Content-Type: application/json
Location: /orders/1
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 59
X-Content-Type-Options: nosniff
Strict-Transport-Security: max-age=31536000; includeSubDomains

{
  "orderId": 1,
  "studentId": "STU-778812",
  "addressId": 10,
  "paymentMethod": "CARD",
  "status": "PLACED",
  "total": 240.0,
  "items": [{"itemId": 101, "quantity": 2, "unitPrice": 120.0}],
  "createdAt": "2026-09-22T10:00:00+00:00"
}
```

The implementation uses HTTP/1.1 when run behind the normal Flask development server.

---

# Part B – Headers and Status Codes

## B1. Content-Type, Accept and Compression

JSON request bodies must use `Content-Type: application/json`. Responses use JSON. If a client sends an `Accept` value that does not include `application/json`, the service returns `406 Not Acceptable`.

For responses of at least 1024 bytes, gzip compression is enabled when the client sends `Accept-Encoding: gzip`.

## B2. Status Code Policy

- `201 Created` + `Location` for a new order.
- `200 OK` for successful reads and cancellation.
- `204 No Content` for OPTIONS.
- `304 Not Modified` for an unchanged conditional GET.
- `400 Bad Request` for malformed JSON/fields.
- `401 Unauthorized` for missing/invalid bearer token.
- `404 Not Found` for an unknown order.
- `409 Conflict` for business/idempotency conflicts.
- `412 Precondition Failed` for stale `If-Match`.
- `422 Unprocessable Content` for valid JSON rejected by a domain rule.
- `429 Too Many Requests` after the per-client request budget is exceeded.
- `503 Service Unavailable` when Payments remains unavailable after retries.

## B3. Authorization

Protected endpoints require:

```text
Authorization: Bearer campuseats-demo-token
```

The token is a demonstration token, not a production authentication system. Missing or invalid authorization returns `401` and `WWW-Authenticate`.

The token can be changed with the `DEMO_BEARER_TOKEN` environment variable.

## B4. Cache-Control and ETag

`GET /orders/{orderId}` returns:

```text
Cache-Control: private, max-age=30
ETag: "..."
```

The ETag is derived from the current published order representation. When the order changes, its representation and therefore its ETag changes.

## B5. Rate Limiting

Each authorization identity gets a 60-request budget per 60-second window by default. Responses include:

```text
X-RateLimit-Limit: 60
X-RateLimit-Remaining: <remaining>
```

When the budget is exceeded:

```text
HTTP/1.1 429 Too Many Requests
Retry-After: <seconds>
```

The limit can be changed using `RATE_LIMIT`.

## B6. CORS

The service returns:

```text
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE, OPTIONS
Access-Control-Allow-Headers: Authorization, Content-Type, Accept, Idempotency-Key, If-None-Match, If-Match, X-HTTP-Method-Override
```

`OPTIONS` supports browser preflight requests.

## B7. Security and General Headers

The service returns:

```text
X-Content-Type-Options: nosniff
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

Production deployment must use HTTPS before enabling HSTS. The framework may also add normal server/date headers.

---

# Part C – Conditional Requests and Retry Safety

## C1. If-None-Match / 304

Example:

```http
GET /orders/1 HTTP/1.1
Authorization: Bearer campuseats-demo-token
Accept: application/json
If-None-Match: "existing-etag"
```

If the ETag still matches, the server returns `304 Not Modified` with no body. This saves bandwidth and avoids sending an unchanged JSON representation.

## C2. If-Match / 412

Cancellation is an update. A client can send:

```http
POST /orders/1/cancellation HTTP/1.1
Authorization: Bearer campuseats-demo-token
If-Match: "old-etag"
```

If the resource has changed since that ETag was obtained, the service returns `412 Precondition Failed`. This prevents a stale client from overwriting a newer state.

## C3. Idempotency-Key

A risky create request uses:

```text
Idempotency-Key: order-attempt-123
```

If the response is lost and the client retries with the same key, CampusEats returns the original result and does not repeat order/payment work. Reusing the same key with a different request body returns `409 Conflict`.

Without idempotency, a timeout after payment could cause the client to retry and accidentally create two orders or two charges.

## C4. Retry-Safety Plan

| Situation | Mechanism | Safe action |
|---|---|---|
| Read one order again | `If-None-Match` | Retry GET; 304 means unchanged |
| Update/cancel from a possibly stale client | `If-Match` | Retry only after fetching the latest ETag |
| Create order after lost response | `Idempotency-Key` | Retry the same key |
| Payment service transient failure | Client library timeout + exponential backoff + jitter | Same payment idempotency key is reused on every attempt |

---

# Part D – Testing and Evidence

## D1. Curl Cases

`curl-transcript.txt` contains example commands for:

1. Successful create → 201 + Location.
2. Same create with same Idempotency-Key → original result.
3. Conditional GET → 304.
4. Stale conditional write → 412.
5. Malformed request → 400.
6. Missing order → 404.
7. Missing/invalid authorization → 401.
8. Unsupported Accept → 406.
9. Rate limit → 429.
10. OPTIONS/CORS preflight → 204.

## D2. Header Matrix

| Endpoint | Request headers needed/used | Response headers set/important |
|---|---|---|
| GET `/orders` | Authorization, Accept | Content-Type, X-RateLimit-Limit, X-RateLimit-Remaining, CORS, nosniff, HSTS |
| POST `/orders` | Authorization, Content-Type, Accept, Idempotency-Key, optional X-HTTP-Method-Override | Location, Content-Type, Idempotency-Replayed (replay), X-RateLimit-Limit, X-RateLimit-Remaining, CORS, nosniff, HSTS |
| GET `/orders/{orderId}` | Authorization, Accept, optional If-None-Match | ETag, Cache-Control, Content-Type, rate-limit and security/CORS headers; 304 has no body |
| POST `/orders/{orderId}/cancellation` | Authorization, Accept, optional If-Match, optional X-HTTP-Method-Override | ETag, Cache-Control: no-store, Content-Type, rate-limit and security/CORS headers |
| OPTIONS resource | Origin, Access-Control-Request-Method, Access-Control-Request-Headers | Allow, Access-Control-Allow-Origin, Access-Control-Allow-Methods, Access-Control-Allow-Headers, security headers |

## D3. Submission Contents

The final ZIP contains:

- source code
- tests
- `openapi.yaml`
- `NOTES.md`
- `curl-transcript.txt`
- `pytest-output.txt`
- `openapi-validation.txt`
- README and requirements
- Payments stub used for the outbound-call demonstration

---

# Eight Required Questions

## 1. For three endpoints, give the method, success status and most important response header.

**POST `/orders`** uses POST because it creates an order. Success is `201 Created`; the important response header is `Location`, which tells the client where the new order can be retrieved.

**GET `/orders/{orderId}`** uses GET because it reads an order. Success is `200 OK`; `ETag` identifies the current representation and enables conditional caching.

**POST `/orders/{orderId}/cancellation`** uses POST because cancellation is a state-changing action represented as a sub-resource. Success is `200 OK`; `ETag` identifies the new representation and supports later concurrency checks.

## 2. Which operations are safe, idempotent, or neither? How are retries made safe?

GET and OPTIONS are safe and idempotent. Create-order POST is neither inherently safe nor idempotent, so `Idempotency-Key` makes a repeated attempt return the original result. Cancellation is not safe; `If-Match` protects it against stale state.

## 3. Explain ETag, 304 and 412.

`ETag` is a validator for a representation. `If-None-Match` with a matching ETag lets the server return `304 Not Modified`, saving response bytes. `If-Match` is used before a state-changing request; a stale value produces `412 Precondition Failed`, preventing a lost update.

## 4. Give an exact request for 422 and 400 and explain the difference.

**400 example:**

```http
POST /orders HTTP/1.1
Authorization: Bearer campuseats-demo-token
Content-Type: application/json

{"studentId":"STU-778812"}
```

The request is malformed because required fields are missing.

**422 example:**

```http
POST /orders HTTP/1.1
Authorization: Bearer campuseats-demo-token
Content-Type: application/json

{"studentId":"STU-778812","items":[{"itemId":103,"quantity":1}],"addressId":10,"paymentMethod":"CARD"}
```

The JSON is structurally valid, but item `103` is unavailable, so a domain rule rejects it with 422.

## 5. A browser gets 200 but the frontend still cannot read it. Who blocks it and which header fixes it?

The browser enforces the same-origin policy and CORS rules. The server must provide an appropriate `Access-Control-Allow-Origin` header. For preflighted requests, the server also needs the relevant `OPTIONS` response and allow-method/header values.

## 6. Give one cacheable response and one no-store response and explain why.

`GET /orders/{id}` is cacheable for a short private period with `Cache-Control: private, max-age=30` because it is a read representation and has an ETag. The cancellation response uses `Cache-Control: no-store` because it is the result of a state-changing operation and should not be reused from a cache.

## 7. When is POST reasonable for search instead of GET, and what is given up?

POST can be reasonable when a search request contains a large or structured body, sensitive search criteria that should not appear in a URL, or a complex query document. The trade-off is that POST is not naturally cacheable like GET, URLs are no longer sufficient to identify the query, and generic HTTP tooling loses some of GET's standard semantics.

For the current CampusEats list search, GET remains appropriate because the filters are small query parameters.

## 8. What does Location mean on 201 versus 3xx?

For `201 Created`, `Location` identifies the newly created resource, for example `/orders/42`. In a `3xx` response, `Location` tells the client where to redirect or continue the request. The meaning is therefore related to creation versus redirection.

---

## Run Commands

```bash
pip install -r requirements.txt

# Terminal 1
python payments_stub.py

# Terminal 2
# Windows PowerShell:
$env:PAYMENTS_URL="http://localhost:5001"
$env:DEMO_BEARER_TOKEN="campuseats-demo-token"
python app.py

# Terminal 3
pytest tests/ -v
python -m openapi_spec_validator openapi.yaml
```

### Demo token

```text
campuseats-demo-token
```

This is intentionally a local demonstration token. A production CampusEats deployment should use a real identity provider/token validation system and HTTPS.
