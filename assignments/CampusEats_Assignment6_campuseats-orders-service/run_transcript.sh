#!/usr/bin/env bash
# Regenerates transcript.txt with REAL curl -i output against live local servers.
#   bash run_transcript.sh
# Starts: Payments stub :5001, Orders :5000, rate-limit demo :5003 (RATE_LIMIT=3),
# fault demo :5002. Boilerplate headers (Server, Date, Connection, Vary, HSTS,
# nosniff, Access-Control-*) are filtered out for readability: edit FILTER below
# to see everything.
cd "$(dirname "$0")"
OUT=transcript.txt
LOG=$(mktemp -d)
B=http://localhost:5000
TOKEN='Authorization: Bearer campuseats-demo-token'
JSON='Content-Type: application/json'
FILTER='^(Server|Date|Connection|Vary|Strict-Transport-Security|X-Content-Type-Options|Access-Control-[A-Za-z-]+):'
PIDS=()

start() { # name, env..., -- command
  local name=$1; shift
  ( env "$@" setsid nohup python3 ${CMD[$name]} > "$LOG/$name.log" 2>&1 < /dev/null & echo $! > "$LOG/$name.pid" )
  PIDS+=("$(cat "$LOG/$name.pid")")
}
declare -A CMD=( [stub]="payments_stub.py" [app]="app.py" [rate]="app.py" [fault]="fault_demo.py" )
cleanup() { for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null; done; pkill -f payments_stub.py 2>/dev/null; true; }
trap cleanup EXIT
wait_up() { for _ in $(seq 40); do curl -s -o /dev/null "$1" && return 0; sleep 0.25; done; echo "server $1 did not start" >&2; exit 1; }

start stub X=1;                 wait_up http://localhost:5001
start app PORT=5000;            wait_up $B/orders
start rate PORT=5003 RATE_LIMIT=3; wait_up http://localhost:5003/orders
start fault PORT=5002;          wait_up http://localhost:5002/orders

quote() { if [[ $1 =~ ^[A-Za-z0-9_./:=%+@,-]+$ ]]; then printf '%s' "$1"; else printf "'%s'" "$1"; fi; }
show() { # print the command, then its real output
  printf '$ curl -i'; for a in "$@"; do printf ' '; quote "$a"; done; printf '\n'
  curl -si "$@" | tr -d '\r' | grep -v -i -E "$FILTER"
  printf '\n'
}
section() { printf '\n%s\n%s\n' "$1" "$(printf '=%.0s' $(seq ${#1}))"; }
note() { printf '# %s\n' "$@"; }

{
echo "CS543 Web Services - Team 23 - Yogita Gothi (20251651107), Janvi Goud (20251651047), Shreya Verma (20251651086), Sonali Choudhary (20251651088)"
echo "CampusEats Orders Service - Assignment 6 - curl transcript"
echo "Generated $(date -u +%Y-%m-%dT%H:%M:%SZ) by run_transcript.sh against live local servers."
echo "Orders :5000 (default RATE_LIMIT=60), Payments stub :5001. Boilerplate headers filtered (see script)."

section "D1. SUCCESS PATH"
note "Happy path: 201 Created, Location header, JSON body."
show -X POST $B/orders -H "$TOKEN" -H "$JSON" -H 'Idempotency-Key: demo-001' \
  -d '{"studentId":"STU-778812","items":[{"itemId":101,"quantity":2}],"addressId":10,"paymentMethod":"CARD"}'
note "Follow the Location header:"
show $B/orders/1 -H "$TOKEN"
note "Second order (used below for the illegal-transition demo):"
show -X POST $B/orders -H "$TOKEN" -H "$JSON" -H 'Idempotency-Key: demo-002' \
  -d '{"studentId":"STU-778812","items":[{"itemId":102,"quantity":1}],"addressId":10,"paymentMethod":"UPI"}'

section "D2. FAILURE PATHS (every one a Problem Details body, application/problem+json)"
note "Empty cart -> 422 empty-cart"
show -X POST $B/orders -H "$TOKEN" -H "$JSON" \
  -d '{"studentId":"STU-778812","items":[],"addressId":10,"paymentMethod":"CARD"}'
note "quantity 0 -> 422 validation-error, field items[0].quantity"
show -X POST $B/orders -H "$TOKEN" -H "$JSON" \
  -d '{"studentId":"STU-778812","items":[{"itemId":101,"quantity":0}],"addressId":10,"paymentMethod":"CARD"}'
note "quantity -3 -> 422 (same field, same type)"
show -X POST $B/orders -H "$TOKEN" -H "$JSON" \
  -d '{"studentId":"STU-778812","items":[{"itemId":101,"quantity":-3}],"addressId":10,"paymentMethod":"CARD"}'
note "TWO bad fields at once (quantity 0 AND addressId missing) -> ONE 422 listing both"
show -X POST $B/orders -H "$TOKEN" -H "$JSON" \
  -d '{"studentId":"STU-778812","items":[{"itemId":101,"quantity":0}],"paymentMethod":"CARD"}'
note "Everything wrong at once -> six entries in errors[]"
show -X POST $B/orders -H "$TOKEN" -H "$JSON" \
  -d '{"items":[{"quantity":0},"x"],"paymentMethod":"CHEQUE"}'
note "Body is not JSON -> 400 malformed-body (cannot even be validated)"
show -X POST $B/orders -H "$TOKEN" -H "$JSON" -d '{not json'
note "Wrong media type -> 415 unsupported-media-type"
show -X POST $B/orders -H "$TOKEN" -H 'Content-Type: text/plain' -d 'studentId=STU-778812'
note "Unknown order id -> 404 order-not-found"
show $B/orders/999999 -H "$TOKEN"
note "Unknown URL -> 404 not-found"
show $B/menu -H "$TOKEN"
note "Illegal transition: cancel order 2 (200), then cancel it again -> 409 illegal-transition"
show -X POST $B/orders/2/cancellation -H "$TOKEN"
show -X POST $B/orders/2/cancellation -H "$TOKEN"
note "Cancel an unknown order -> 404"
show -X POST $B/orders/999999/cancellation -H "$TOKEN"
note "Stale If-Match -> 412 precondition-failed"
show -X POST $B/orders/1/cancellation -H "$TOKEN" -H 'If-Match: "stale-etag"'
note "Item unavailable (item 103 is switched off, 999 does not exist) -> 422 item-unavailable, one entry per item"
show -X POST $B/orders -H "$TOKEN" -H "$JSON" \
  -d '{"studentId":"STU-778812","items":[{"itemId":103,"quantity":1},{"itemId":999,"quantity":1}],"addressId":10,"paymentMethod":"CARD"}'
note "Address that is not this student's -> 422 invalid-address"
show -X POST $B/orders -H "$TOKEN" -H "$JSON" \
  -d '{"studentId":"STU-778812","items":[{"itemId":101,"quantity":1}],"addressId":20,"paymentMethod":"CARD"}'
note "Payment declined (Payments stub declines amount 999) -> 422 payment-declined; upstream bank text NOT passed on"
show -X POST $B/orders -H "$TOKEN" -H "$JSON" -H 'Idempotency-Key: demo-declined' \
  -d '{"studentId":"STU-778812","items":[{"itemId":105,"quantity":1}],"addressId":10,"paymentMethod":"CARD"}'
note "Same key replayed -> same 422, Idempotency-Replayed: true (a decline is permanent, so it is remembered)"
show -X POST $B/orders -H "$TOKEN" -H "$JSON" -H 'Idempotency-Key: demo-declined' \
  -d '{"studentId":"STU-778812","items":[{"itemId":105,"quantity":1}],"addressId":10,"paymentMethod":"CARD"}'
note "Idempotency-Key reused with a DIFFERENT body -> 409 idempotency-conflict"
show -X POST $B/orders -H "$TOKEN" -H "$JSON" -H 'Idempotency-Key: demo-001' \
  -d '{"studentId":"STU-778812","items":[{"itemId":101,"quantity":5}],"addressId":10,"paymentMethod":"CARD"}'
note "Payments gateway keeps failing (stub returns 503 for amount 500; Orders retries 3x with backoff) -> 503 + Retry-After, total time shown"
show -w '\n[curl] total time: %{time_total}s\n' -X POST $B/orders -H "$TOKEN" -H "$JSON" -H 'Idempotency-Key: demo-503' \
  -d '{"studentId":"STU-778812","items":[{"itemId":104,"quantity":1}],"addressId":10,"paymentMethod":"CARD"}'
note "No / bad token -> 401 unauthorized (+ WWW-Authenticate)"
show $B/orders/1
note "Accept: text/html -> 406 not-acceptable"
show $B/orders/1 -H "$TOKEN" -H 'Accept: text/html'
note "Methods that are not offered -> 405 method-not-allowed with Allow"
show -X DELETE $B/orders/1 -H "$TOKEN"
show -X PATCH $B/orders/1 -H "$TOKEN" -H "$JSON" -d '{"status":"CANCELLED"}'
note "Bad query parameters -> one 422 naming each"
show "$B/orders?status=BOGUS&page=0&pageSize=abc&sortOrder=up" -H "$TOKEN"
note "Rate limit (separate instance on :5003 with RATE_LIMIT=3): three OK, the fourth is 429 + Retry-After"
for i in 1 2 3; do show http://localhost:5003/orders -H "$TOKEN"; done
show http://localhost:5003/orders -H "$TOKEN"
note "Unexpected server fault (fault_demo.py on :5002 makes the store raise a DB-style error for order 666) -> clean 500"
show http://localhost:5002/orders/666 -H "$TOKEN"
note "What stayed in the SERVER log (never sent to the client):"
grep -E "unhandled error|psycopg2|SELECT|Traceback" "$LOG/fault.log" | sed 's/^/  log> /' | head -6
printf '\n'

section "D3. CONTENT NEGOTIATION"
note "Same order as JSON (default) ..."
show $B/orders/1 -H "$TOKEN" -H 'Accept: application/json'
note "... and as XML. Note the different Content-Type and ETag."
show $B/orders/1 -H "$TOKEN" -H 'Accept: application/xml'
note "q-values: JSON preferred (0.9 > 0.5)"
show $B/orders/1 -H "$TOKEN" -H 'Accept: application/xml;q=0.5, application/json;q=0.9'
note "Wildcard with XML preferred"
show $B/orders/1 -H "$TOKEN" -H 'Accept: application/xml, */*;q=0.1'
note "List as XML"
show "$B/orders?studentId=STU-778812&status=PLACED" -H "$TOKEN" -H 'Accept: application/xml'
note "Create as XML (201 + Location)"
show -X POST $B/orders -H "$TOKEN" -H "$JSON" -H 'Accept: application/xml' \
  -d '{"studentId":"STU-001","items":[{"itemId":101,"quantity":1}],"addressId":20,"paymentMethod":"COD"}'
note "Errors follow the same negotiation: 404 as application/problem+xml"
show $B/orders/999999 -H "$TOKEN" -H 'Accept: application/xml'
note "422 as XML"
show -X POST $B/orders -H "$TOKEN" -H "$JSON" -H 'Accept: application/xml' \
  -d '{"studentId":"STU-778812","items":[{"itemId":101,"quantity":0}],"paymentMethod":"CARD"}'
note "Cannot produce what was asked -> 406 (answered as problem+json, the default)"
show $B/orders/1 -H "$TOKEN" -H 'Accept: application/pdf'

section "D4. NO REGRESSIONS (A5 checks re-run)"
note "Idempotency: repeat of demo-001 returns the ORIGINAL order #1 (Idempotency-Replayed: true), no second order/charge"
show -X POST $B/orders -H "$TOKEN" -H "$JSON" -H 'Idempotency-Key: demo-001' \
  -d '{"studentId":"STU-778812","items":[{"itemId":101,"quantity":2}],"addressId":10,"paymentMethod":"CARD"}'
note "Still exactly one PLACED order for item 101 x2 (order 2 was cancelled, order 1 untouched):"
show "$B/orders?studentId=STU-778812&status=PLACED" -H "$TOKEN"
note "Conditional GET still works: 304, no body, no Content-Type"
ETAG=$(curl -sI $B/orders/1 -H "$TOKEN" | tr -d '\r' | awk -F': ' 'tolower($1)=="etag"{print $2}')
show $B/orders/1 -H "$TOKEN" -H "If-None-Match: $ETAG"
note "Retries: STOP the Payments service -> connection refused; Orders retries 3x with exponential backoff + jitter, then a clean 503. No host/port in the body."
note "(The 2-second read-timeout path is exercised by tests/test_app.py: test_timeout_is_retried_then_unavailable.)"
kill "$(cat "$LOG/stub.pid")" 2>/dev/null; pkill -f payments_stub.py 2>/dev/null; sleep 0.5
show -w '\n[curl] total time: %{time_total}s\n' -X POST $B/orders -H "$TOKEN" -H "$JSON" -H 'Idempotency-Key: demo-retry' \
  -d '{"studentId":"STU-778812","items":[{"itemId":101,"quantity":1}],"addressId":10,"paymentMethod":"CARD"}'
note "What stayed in the SERVER log (upstream detail the client never sees):"
grep -E "payments unavailable" "$LOG/app.log" | tail -1 | cut -c1-230 | sed 's/^/  log> /'
printf '\n'
note "Payments comes back; the client retries with the SAME Idempotency-Key -> 201 (the 503 was not cached)"
start stub X=1; wait_up http://localhost:5001
show -X POST $B/orders -H "$TOKEN" -H "$JSON" -H 'Idempotency-Key: demo-retry' \
  -d '{"studentId":"STU-778812","items":[{"itemId":101,"quantity":1}],"addressId":10,"paymentMethod":"CARD"}'
echo "(end of transcript)"
} > "$OUT" 2>&1
echo "wrote $OUT ($(wc -l < "$OUT") lines)"
