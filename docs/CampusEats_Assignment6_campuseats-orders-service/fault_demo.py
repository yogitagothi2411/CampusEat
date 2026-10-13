"""Demo harness ONLY (not part of the service): runs the real app but makes the
order store blow up for order #666 with a nasty, DB-looking exception. Used by
run_transcript.sh to show that the client gets a clean 500 while the log keeps
the detail. Run: PORT=5002 python3 fault_demo.py"""
import os

import app as service
import store

_real_get_order = store.get_order


def exploding_get_order(order_id):
    if order_id == 666:
        raise RuntimeError("psycopg2.OperationalError: could not connect to server at 10.0.3.14:5432 "
                           "while running: SELECT * FROM orders WHERE id = 666")
    return _real_get_order(order_id)


store.get_order = exploding_get_order

if __name__ == "__main__":
    service.app.run(port=int(os.environ.get("PORT", "5002")), debug=False)
