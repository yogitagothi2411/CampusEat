# CampusEats Orders Service – Assignment 6

**CS543 – Web Services – Honest responses: status codes, errors & validation**  
Team 23 – Yogita Gothi (20251651107), Janvi Goud (20251651047), Shreya Verma (20251651086), Sonali Choudhary (20251651088)

The same Orders service as Assignment 5, now reporting outcomes honestly: correct status codes, one Problem Details error shape, field-level 422 validation, `Accept` negotiation (JSON / XML / 406), and clean errors that never leak internals.

## Submission files

- `app.py`, `errors.py`, `models.py`, `store.py`, `payment_client.py`, `payments_stub.py` – service source.
- `openapi.yaml` – status codes and the Problem Details schema for every endpoint.
- `transcript.txt` – real `curl -i` output: success, every failure path, negotiation, A5 re-checks.
- `NOTES.md` – status map, type catalogue and the seven answers.
- `tests/test_app.py`, `test-output.txt` – 51 tests and their output.
- `run_transcript.sh`, `fault_demo.py` – regenerate the transcript; demo harness that forces a 500.
- `requirements.txt` – Python dependencies.

## Run

```bash
pip install -r requirements.txt
python payments_stub.py        # terminal 1, port 5001
python app.py                  # terminal 2, port 5000  (PORT=... to change)
python -m unittest -v tests.test_app     # or: pytest tests/ -v
python -m openapi_spec_validator openapi.yaml
bash run_transcript.sh         # rewrites transcript.txt
```

Demo token: `campuseats-demo-token` (`DEMO_BEARER_TOKEN` to change). Production must use HTTPS.
