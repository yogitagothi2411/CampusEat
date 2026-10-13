"""
payments_stub.py
A minimal stand-in for the Payments service so the Orders service has a
real HTTP endpoint to call for Part D. It is a REST rebuild of the same
chargePayment operation described in docs/Assignment3_SOAP/partner.wsdl.

This is NOT part of the Assignment 4 deliverable itself (that's the
Orders service). It only exists so payment_client.py has something real
to talk to for the curl transcript. Run it on a separate port:

    python3 payments_stub.py

Test hooks (so the curl transcript can show every path):
  - amount == 999          -> 422 payment-declined (mirrors soap-fault.xml's
                               "card_declined" / insufficient funds fault)
  - studentId == "STU-BAD" -> 400 malformed-request
  - amount == 500          -> always 503, to exercise the Orders service's
                               retry + eventual fallback path
  - Idempotency-Key reuse  -> returns the original transaction, doesn't
                               charge twice
"""

import itertools
from flask import Flask, jsonify, request

app = Flask(__name__)

_transactions_by_key = {}
_txn_counter = itertools.count(1)


@app.post("/payments/charge")
def charge():
    body = request.get_json(silent=True) or {}
    idem_key = request.headers.get("Idempotency-Key")

    if idem_key and idem_key in _transactions_by_key:
        return jsonify(_transactions_by_key[idem_key]), 200

    student_id = body.get("studentId")
    amount = body.get("amount")
    merchant_order_id = body.get("merchantOrderId")

    if not student_id or amount is None or not merchant_order_id:
        return jsonify({
            "type": "https://campuspay.example.com/errors/malformed-request",
            "title": "Malformed request",
            "status": 400,
            "detail": "studentId, amount and merchantOrderId are required.",
        }), 400

    if student_id == "STU-BAD":
        return jsonify({
            "type": "https://campuspay.example.com/errors/malformed-request",
            "title": "Malformed request",
            "status": 400,
            "detail": "Unknown student.",
        }), 400

    if amount == 500:
        # Simulate the gateway being down, to exercise retry/backoff.
        return jsonify({
            "type": "https://campuspay.example.com/errors/gateway-unavailable",
            "title": "Payment gateway unavailable",
            "status": 503,
            "detail": "Upstream bank gateway timed out.",
        }), 503

    if amount == 999:
        # Same fault as docs/Assignment3_SOAP/soap-fault.xml, as a 422.
        return jsonify({
            "type": "https://campuspay.example.com/errors/payment-declined",
            "title": "Payment declined",
            "status": 422,
            "detail": "The issuing bank declined the transaction due to insufficient funds.",
        }), 422

    txn = {
        "transactionId": f"TXN-{next(_txn_counter):08d}",
        "merchantOrderId": merchant_order_id,
        "status": "CAPTURED",
        "amountCharged": amount,
        "currency": body.get("currency", "INR"),
        "authCode": f"AUTH-{next(_txn_counter):06d}",
    }
    if idem_key:
        _transactions_by_key[idem_key] = txn
    return jsonify(txn), 200


if __name__ == "__main__":
    app.run(port=5001)
