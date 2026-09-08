# CampusEats Orders Service — Assignment 4

REST rebuild of the Order Service from `docs/assignment-2/desgin1.pdf`'s
ORDERS CONTRACT. See `NOTES.md` for the resource table, the design
write-up, and the five comparison questions against
`docs/Assignment3_SOAP/partner.wsdl`.

## Layout

```
openapi.yaml       API contract (written before any handler code)
models.py          Order / OrderItem — stored record vs published JSON
store.py           in-memory storage + simulated Account/Catalogue lookups
errors.py          single problem() error shape + ApiError
payment_client.py  hardened outbound call to Payments (Part D)
payments_stub.py   minimal stand-in Payments service to call locally
app.py             the four endpoints
tests/test_app.py  pytest suite
curl-transcript.txt   real captured curl -i run (success + every failure path)
NOTES.md           resource table, A5, D3, Q1–Q5
```

## Run it

```bash
pip install -r requirements.txt

# terminal 1
python3 payments_stub.py

# terminal 2
export PAYMENTS_URL=http://localhost:5001
python3 app.py

# terminal 3
pytest tests/ -v
python3 -m openapi_spec_validator openapi.yaml
```
