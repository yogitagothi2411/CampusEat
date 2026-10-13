# CS543 – Web Services – Assignment 6

## CampusEats Orders Service – Honest responses: status codes, errors & validation

### Team Members

| Roll No | Name |
|---|---|
| 20251651107 | Yogita Gothi |
| 20251651047 | Janvi Goud |
| 20251651086 | Shreya Verma |
| 20251651088 | Sonali Choudhary |

**Team ID:** 23

This is the **same Orders service as Assignment 5** (same endpoints, store, payment client) with the way it reports outcomes rebuilt. No new service.

| File | What it is |
|---|---|
| `app.py`, `errors.py`, `store.py`, `models.py`, `payment_client.py`, `payments_stub.py` | Service source (`errors.py` = the one Problem Details catalogue; `app.py` = validation, negotiation, handlers) |
| `openapi.yaml` | Status codes + Problem Details schema per endpoint, XML representations, `Retry-After` |
| `transcript.txt` | Real `curl -i` output: success, every failure, negotiation, A5 re-checks. Regenerate with `bash run_transcript.sh` |
| `tests/test_app.py`, `test-output.txt` | 51 tests (A5 regression + A6) and their output |
| `fault_demo.py`, `run_transcript.sh` | Demo harness (forces a 500 for the transcript) and the transcript generator |

---

# Part A – Status codes

## A1. Status map (every outcome)

The success status and **each real failure** for every endpoint. Every failure body is Problem Details; the `type` slug is in the second column (full URI = `https://campuseats.example.com/errors/<slug>`).

### `POST /orders` – create and charge

| Status | Slug | Why this status |
|---|---|---|
| **201** | – | A new resource now exists; `Location: /orders/{id}` points at it. |
| 400 | `malformed-body` | Body missing, not valid JSON, or not a JSON object – it cannot even be *validated*. |
| 401 | `unauthorized` | No / wrong bearer token. Carries `WWW-Authenticate`. |
| 406 | `not-acceptable` | `Accept` allows neither JSON nor XML. |
| 409 | `idempotency-conflict` | Same `Idempotency-Key` re-used with a *different* body – the key's meaning would be ambiguous. |
| 415 | `unsupported-media-type` | Body sent as something other than `application/json`. |
| 422 | `validation-error` | JSON is well-formed but a field is wrong (quantity ≤ 0, address missing…). `errors[]` lists every bad field. |
| 422 | `empty-cart` | `items` is `[]` – valid JSON, but business-meaningless. |
| 422 | `invalid-address` | `addressId` does not exist or is not this student's. |
| 422 | `item-unavailable` | An item does not exist, is switched off, or lacks stock. `errors[]` lists each one. |
| 422 | `payment-declined` | Payments said no. The request was understood; the *money* was refused. Permanent. |
| 429 | `rate-limited` | Per-client budget used up. Transient; `Retry-After`. |
| 500 | `internal-error` | Unexpected fault on our side. Generic body + `errorId`. |
| 503 | `payment-service-unavailable` | Payments still failing after 3 retries. Transient; `Retry-After`. |

### `GET /orders` – list

| Status | Slug | Why |
|---|---|---|
| **200** | – | Success, including an **empty array** (no matches is a valid answer, not a failure). |
| 401 / 406 / 429 / 500 | as above | |
| 422 | `validation-error` | Bad `status`, `sortBy`, `sortOrder`, `page`, `pageSize`; all bad parameters reported at once. |

### `GET /orders/{orderId}` – read one

| Status | Slug | Why |
|---|---|---|
| **200** | – | Order returned (JSON or XML). |
| **304** | – | `If-None-Match` matched: not an error, no body. |
| 404 | `order-not-found` | No such order. |
| 401 / 406 / 429 / 500 | as above | |

### Cancel – `POST /orders/{orderId}/cancellation`

Our A5 design models "cancel" as a state-changing sub-resource (not `PATCH` / `DELETE`; the order is kept for history).

| Status | Slug | Why |
|---|---|---|
| **200** | – | Order is now `CANCELLED`; new `ETag`. |
| 404 | `order-not-found` | No such order. |
| 409 | `illegal-transition` | Order is already `CANCELLED` – the state machine forbids it. |
| 412 | `precondition-failed` | `If-Match` ETag is stale: someone changed the order since the client read it. |
| 401 / 406 / 429 / 500 | as above | |

### Everything else

| Request | Status | Why |
|---|---|---|
| `PATCH /orders/{id}`, `DELETE /orders/{id}` (and any unsupported method) | **405** `method-not-allowed` + `Allow` | Not offered in this API. |
| Unknown URL | **404** `not-found` | |
| `OPTIONS` on an order path | **204**, no body | Preflight / discovery. |
| `HEAD` on the GET routes | **200**, no body | |

## A2. Fix responses – audit result

I read every route and handler for a `200` that carries a failure (`{"ok": false}`, an `"error"` key, an empty body meaning "nope"). **There was none in A5**: failures already raised real 4xx/5xx. `tests/test_app.py::test_no_200_with_ok_false_anywhere` now locks that in. What *was* dishonest or wrong, and is fixed:

| # | In A5 | Now |
|---|---|---|
| 1 | Empty cart, `quantity: 0`, missing address all returned **400** | **422** – the JSON is fine, the *content* is invalid (400 is kept only for "cannot parse") |
| 2 | A transient **503 was cached under the `Idempotency-Key`**: retrying with the same key replayed the 503 forever, so the advertised "retry with the same key" could never succeed | 503 is not remembered; a same-key retry is a fresh attempt (shown live in `transcript.txt`, D4). A permanent 422 decline *is* still remembered. |
| 3 | Errors were `application/json` | `application/problem+json; charset=utf-8` (or `+xml`) |
| 4 | `Retry-After` only on 429 | Also on 503 |
| 5 | `detail` for a payment outage was the raw exception text (host, port, library message) | Fixed generic text; detail goes to the log (see Q6) |
| 6 | Any unexpected exception → Flask's default HTML 500 page | Clean `internal-error` Problem Details |
| 7 | `OPTIONS` answered **200** instead of the documented 204 (Flask's automatic OPTIONS handler shadowed ours – A5's own test would have failed) | **204** with `Allow` |
| 8 | `HEAD` got a **405** even though `Allow` listed it | HEAD works on the GET routes |
| 9 | `quantity: true` passed validation (`bool` is an `int` in Python) | rejected |

## A3. `Location` on create

`POST /orders` → `201 Created`, `Location: /orders/{id}`. A replayed create (same `Idempotency-Key`) returns the same `Location`. Tested by following the header (`test_location_points_at_new_order`); see `transcript.txt` D1.

## A4. Retry-safety

`429` and `503` always carry `Retry-After` (seconds). Which endpoints are safe to retry – and on which codes – is Answer 5 below.

---

# Part B – One error shape

## B1. Problem Details everywhere

`errors.problem(slug, detail, …)` is the only place an error body is built, and `render_error()` is the only way one leaves the service. Every route raises `ApiError`; three handlers catch everything else (`ApiError`, werkzeug `HTTPException`, and a catch-all `Exception`). Every body has `type`, `title`, `status`, `detail`, and is labelled `Content-Type: application/problem+json; charset=utf-8` (`application/problem+xml` if the client asked for XML). `status` in the body always equals the HTTP status.

## B2. Type catalogue

See Answer 2. Slugs are **stable**: never renamed or reused. A5's `order-conflict` became the more precise `illegal-transition`.

## B3. Field-level 422

`errors[]` entries are `{"field": "<path>", "message": "<why>"}`; paths use `items[0].quantity` style. See Answer 4.

## B4. No leaks

Risky work is wrapped; detail is logged server-side, and a mapped clean error goes out. See Answer 6.

---

# Part C – Request validation & formats

## C1. Body description

Enforced by explicit checks in `validate_create_order()`; the equivalent JSON Schema (also `OrderCreateRequest` in `openapi.yaml`):

```json
{
  "type": "object",
  "required": ["studentId", "items", "addressId", "paymentMethod"],
  "properties": {
    "studentId":     { "type": "string", "minLength": 1 },
    "addressId":     { "type": "integer" },
    "paymentMethod": { "enum": ["CARD", "UPI", "WALLET", "COD"] },
    "items": {
      "type": "array", "minItems": 1,
      "items": {
        "type": "object", "required": ["itemId", "quantity"],
        "properties": {
          "itemId":   { "type": "integer" },
          "quantity": { "type": "integer", "minimum": 1 }
        }
      }
    }
  }
}
```

## C2. Validate, then act

Order of work in `POST /orders`: parse body (400/415) → **validate the whole body, collecting every error** (one 422) → address check → catalogue check (collecting every unavailable item) → create order → charge. Nothing is looked up, charged or stored until validation passes (`test_nothing_done_when_invalid`). Business rules that need a lookup (address, stock) come after, as 422s with their own types.

## C3. Content negotiation

`negotiate()` parses `Accept` properly: q-values, `application/*`, `*/*`, `q=0` exclusions; a more specific range beats a wildcard; ties go to JSON.

| `Accept` | Result |
|---|---|
| absent, `*/*`, `application/*` | JSON (default) |
| `application/json` | JSON |
| `application/xml` (or `application/xml, */*;q=0.1`) | XML |
| `application/xml;q=0.5, application/json;q=0.9` | JSON |
| `text/html`, `application/pdf`, `application/json;q=0` | **406** |

Applies to success bodies *and* errors (`application/problem+xml`, namespace `urn:ietf:rfc:9457`). ETags differ per representation; `If-Match` / `If-None-Match` accept either. An idempotent replay is re-rendered for the *current* request's `Accept`.

## C4. Every body is labelled

JSON `application/json; charset=utf-8`, errors `application/problem+json; charset=utf-8`, XML `application/xml; charset=utf-8`. Bodiless responses (204, 304) carry no `Content-Type`. Tested across 8 different response kinds in `ContentTypeEverywhere`.

---

# Part D – Proof

| | Where |
|---|---|
| D1 success transcript | `transcript.txt` § D1 |
| D2 failure transcript (empty cart, qty ≤ 0, unknown id, illegal transition, rate limit, + 15 more) | `transcript.txt` § D2 |
| D3 negotiation | `transcript.txt` § D3 |
| D4 no regressions | `transcript.txt` § D4 and the *A5Regression* / *PaymentClientRetries* test classes |

**What was and wasn't run (honest account):**

- `python -m unittest -v tests.test_app` → **51 tests, all pass** (`test-output.txt`). The tests are plain `unittest`, so `pytest tests/` collects them too, but I ran them with unittest because pytest was not installable in my environment.
- `transcript.txt` is real `curl -i` output from live local servers, produced by `run_transcript.sh`. Boilerplate headers (`Server`, `Date`, `Vary`, HSTS, CORS…) are filtered out for readability; the script says how to unfilter.
- `openapi.yaml`: I checked that it parses, every one of its 26 `$ref`s resolves and every response has a description. **I could not run `openapi-spec-validator` here (not installable offline) – please run `python -m openapi_spec_validator openapi.yaml` before submitting.**
- D4 timeouts: with the Payments stub stopped the transcript shows connection-refused → 3 attempts → 503. The 2-second *read-timeout* path is covered by `test_timeout_is_retried_then_unavailable` rather than a live slow server.
- One catalogue entry was added for the demo: item `105` (price 999.00) so the Payments stub's "decline amount 999" hook can be hit.

### Run

```bash
pip install -r requirements.txt
python payments_stub.py                      # terminal 1  (:5001)
python app.py                                # terminal 2  (:5000)
python -m unittest -v tests.test_app         # tests
bash run_transcript.sh                       # regenerate transcript.txt
```

---

# Answers

## 1. Your status map: every endpoint, its success status, and the status for each failure – one line on why each.

See **A1** above for the full table with a reason per line. In short:

| Endpoint | Success | Failures |
|---|---|---|
| `POST /orders` | 201 + `Location` | 400 can't parse · 401 no token · 406 can't produce · 409 key reused with other body · 415 not JSON · 422 invalid content (validation / empty cart / address / item / declined) · 429 slow down · 500 our fault · 503 Payments down |
| `GET /orders` | 200 (even if empty) | 401 · 406 · 422 bad query parameter · 429 · 500 |
| `GET /orders/{id}` | 200 / 304 | 401 · 404 no such order · 406 · 429 · 500 |
| cancel `POST /orders/{id}/cancellation` | 200 | 401 · 404 · 406 · 409 illegal transition · 412 stale ETag · 429 · 500 |
| `PATCH` / `DELETE /orders/{id}` | – | 405 + `Allow` (not offered) |

## 2. Your type catalogue: the stable string for each failure and what triggers it.

Base: `https://campuseats.example.com/errors/`

| Slug | Status | Triggered by |
|---|---|---|
| `empty-cart` | 422 | `items` is `[]` |
| `item-unavailable` | 422 | item id unknown, item switched off, or stock < quantity |
| `payment-declined` | 422 | Payments service refused the charge (4xx) |
| `order-not-found` | 404 | `GET` / cancel an order id that does not exist |
| `illegal-transition` | 409 | cancelling an order that is already `CANCELLED` |
| `validation-error` | 422 | any other bad body field or query parameter; see `errors[]` |
| `invalid-address` | 422 | `addressId` unknown or not the student's |
| `idempotency-conflict` | 409 | `Idempotency-Key` re-used with a different body |
| `precondition-failed` | 412 | `If-Match` ETag is stale |
| `malformed-body` | 400 | body missing / not JSON / not an object |
| `unsupported-media-type` | 415 | body not `application/json` |
| `unauthorized` | 401 | missing / invalid bearer token |
| `not-found` | 404 | unknown URL |
| `method-not-allowed` | 405 | method not offered on that path |
| `not-acceptable` | 406 | `Accept` allows neither JSON nor XML |
| `rate-limited` | 429 | request budget used up |
| `payment-service-unavailable` | 503 | Payments still failing after retries |
| `internal-error` | 500 | any unexpected exception |
| `http-error` | varies | fallback for other framework-level HTTP errors |

When `items` is empty the type is `empty-cart` even if other fields are also wrong; `errors[]` still lists every bad field.

## 3. Paste one Problem Details body from your service and label its fields.

`GET /orders/999999` → `404`, `Content-Type: application/problem+json; charset=utf-8`:

```json
{
  "type": "https://campuseats.example.com/errors/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "Order 999999 does not exist."
}
```

| Field | Meaning |
|---|---|
| `type` | Stable URI naming the *kind* of problem (`…/order-not-found`). Clients switch on this, never on `detail`. |
| `title` | Short human summary; identical for every occurrence of this type. |
| `status` | The HTTP status, repeated in the body (always equals the response status). |
| `detail` | Explanation of *this* occurrence (names the id that was not found). Never contains stack traces, SQL or upstream text. |
| `errors` | *(only on 422)* list of `{field, message}` – see Answer 4. |
| `errorId` | *(only on 500)* short id that matches a line in the server log. |

## 4. Show a field-level 422 that reports two bad fields at once.

`POST /orders` with `quantity: 0` **and** no `addressId`:

```http
POST /orders HTTP/1.1
Content-Type: application/json

{"studentId":"STU-778812","items":[{"itemId":101,"quantity":0}],"paymentMethod":"CARD"}
```

```http
HTTP/1.1 422 UNPROCESSABLE ENTITY
Content-Type: application/problem+json; charset=utf-8
```
```json
{
  "type": "https://campuseats.example.com/errors/validation-error",
  "title": "Validation failed",
  "status": 422,
  "detail": "The request body has 2 invalid fields. See 'errors'.",
  "errors": [
    {
      "field": "items[0].quantity",
      "message": "must be an integer >= 1"
    },
    {
      "field": "addressId",
      "message": "is required"
    }
  ]
}
```

One response, both problems – the client can fix everything in one round trip. (`transcript.txt` also shows a request with six bad fields reported together.)

## 5. Which endpoints are safe to retry, and which status codes tell a client so?

**The signal:** `429` and `503`, each with a `Retry-After` header (seconds), plus a network error / timeout where no response arrived. Those are the *only* transient outcomes. A `4xx` other than `429` is **never** retried unchanged – it would fail identically.

| Endpoint | Safe to retry? | When |
|---|---|---|
| `GET /orders`, `GET /orders/{id}`, `HEAD`, `OPTIONS` | **Yes** (safe + idempotent) | network error, `429`, `503`; wait `Retry-After`. A `500` may be retried once with backoff. |
| `POST /orders` | **Only with an `Idempotency-Key`**, and always the *same* key | network error / timeout, `429`, `503`. The key makes the server return the original order instead of creating or charging twice; a retry after a `503` really is a fresh attempt. **Without a key it is not safe** – a lost response could mean an order was placed and charged. |
| cancel `POST …/cancellation` | **`429`: yes** (rejected before any work). **After a network error: no, not blindly** – `GET` the order first (if it is `CANCELLED`, it worked; a blind repeat would give 409). This endpoint never returns 503. | |

Never retry unchanged: `400`, `401` (fix the token), `404`, `405`, `406`, `409`, `415`, `422` (including `payment-declined` – a same-key replay just returns the same 422). `412` is retried only *after* re-reading the order and using the new `ETag`. `500` has no retry promise.

## 6. Where did you map an internal error to a clean client error, and what did you hide from the caller?

Three places, all in `app.py` / `payment_client.py`, all tested:

1. **Payments unreachable / failing** (`PaymentServiceUnavailable`) → `503 payment-service-unavailable` + `Retry-After: 5`, fixed text. **Hidden:** the exception text, e.g. `Payments service unreachable after 3 attempts: HTTPConnectionPool(host='localhost', port=5001): Max retries exceeded…` – i.e. the internal host and port, the HTTP library, and the retry count. It is logged with `app.logger.error`; `transcript.txt` D4 shows the log line next to the clean response. (In A5 this exception text was copied straight into `detail` – a leak that is now fixed.)
2. **Payments declined** (`PaymentDeclined`) → `422 payment-declined`, fixed text. **Hidden:** the upstream provider's own wording (e.g. an "insufficient funds" message from the bank), which is logged at WARNING, not forwarded.
3. **Anything unexpected** (catch-all `@app.errorhandler(Exception)`) → `500 internal-error`. **Hidden:** exception class and message, the stack trace, file paths and – in the demo – a database-style message with an IP and a SQL statement. The client gets a generic sentence plus an `errorId`; the full traceback is in the server log under that same id. `transcript.txt` D2 forces this with `fault_demo.py` and shows the client body next to the log lines; `test_unexpected_exception_is_clean_500` asserts that none of `psycopg2`, the IP, `SELECT`, `Traceback`, `RuntimeError` or `.py` appear in the response, and that all of them appear in the log.

(Also still true from A5: `Order.as_json()` never publishes the internal `idempotency_key` or the Payments `transaction_id`.)

## 7. Show the same order as JSON and as XML, and the Accept header that chose each.

`GET /orders/1` with `Accept: application/json` (also what you get with no `Accept` at all):

```http
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
```
```json
{
  "orderId": 1,
  "studentId": "STU-778812",
  "addressId": 10,
  "paymentMethod": "CARD",
  "status": "PLACED",
  "total": 240.0,
  "items": [
    {
      "itemId": 101,
      "quantity": 2,
      "unitPrice": 120.0
    }
  ],
  "createdAt": "2026-10-13T11:54:21.437395+00:00"
}
```

`GET /orders/1` with `Accept: application/xml` (XML re-indented here for reading; the service sends it on one line):

```http
HTTP/1.1 200 OK
Content-Type: application/xml; charset=utf-8
```
```xml
<?xml version='1.0' encoding='utf-8'?>
<order>
  <orderId>1</orderId>
  <studentId>STU-778812</studentId>
  <addressId>10</addressId>
  <paymentMethod>CARD</paymentMethod>
  <status>PLACED</status>
  <total>240.0</total>
  <items>
    <item>
      <itemId>101</itemId>
      <quantity>2</quantity>
      <unitPrice>120.0</unitPrice>
    </item>
  </items>
  <createdAt>2026-10-13T11:54:21.437395+00:00</createdAt>
</order>
```

The two representations get different `ETag`s. `Accept: text/html` (or `application/pdf`) gets `406 not-acceptable`; errors are negotiated too – an unknown order with `Accept: application/xml` returns `application/problem+xml`. All shown in `transcript.txt` § D3.
