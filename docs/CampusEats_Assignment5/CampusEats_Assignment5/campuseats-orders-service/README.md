# CampusEats Orders Service – Assignment 5

## CS543 – Web Services – HTTP Methods & Headers

This is the submission-ready CampusEats Orders Service folder for Assignment 5. It contains the updated REST service, tests, OpenAPI contract, curl evidence, and `NOTES.md` required by the assignment sheet.

### Submission files

- `openapi.yaml` – methods, query parameters, status codes, conditional headers and response headers.
- `app.py`, `errors.py`, `models.py`, `store.py`, `payment_client.py`, `payments_stub.py` – source files.
- `tests/test_app.py` – automated tests.
- `curl-transcript.txt` – `curl -v` evidence for 201, idempotent replay, 304, 412, 400, 404 and 401, plus other checks.
- `NOTES.md` – method map, headers table, safe-retry plan and all eight answers.
- `requirements.txt` – Python dependencies.

### Run

```bash
pip install -r requirements.txt
python payments_stub.py
```

In another terminal:

```bash
# Windows PowerShell
$env:PAYMENTS_URL="http://localhost:5001"
$env:DEMO_BEARER_TOKEN="campuseats-demo-token"
python app.py
```

Run tests:

```bash
pytest tests/ -v
python -m openapi_spec_validator openapi.yaml
```

Production deployment should use HTTPS; the local demo uses HTTP for localhost.
