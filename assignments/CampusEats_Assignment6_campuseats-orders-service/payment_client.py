"""
payment_client.py
Part D: the ONE real outbound HTTP call this service makes, to the
Payments service (docs/Assignment3_SOAP/partner.wsdl -- chargePayment --
rebuilt here as a REST call to a small stub, payments_stub.py, since the
Tutorial 4 implementation wasn't part of the uploaded repo).

D1 -- address comes from an environment variable, never hard-coded.
D2 -- timeout + retry with exponential backoff and jitter. Only network
      errors, timeouts and 5xx are retried. A 4xx is NEVER retried.
      The retried call carries the same Idempotency-Key every attempt.
"""

import os
import random
import time

import requests

PAYMENTS_URL = os.environ.get("PAYMENTS_URL", "http://localhost:5001")

TIMEOUT_SECONDS = 2.0
MAX_ATTEMPTS = 3
BASE_BACKOFF = 0.2   # seconds
JITTER = 0.15        # seconds, added on top of backoff


class PaymentDeclined(Exception):
    """The Payments service reached a verdict and declined the charge (4xx)."""

    def __init__(self, detail):
        super().__init__(detail)
        self.detail = detail


class PaymentServiceUnavailable(Exception):
    """The Payments service could not be reached / kept failing after retries."""


def charge_payment(order_id, student_id, amount, payment_method, idempotency_key):
    """
    POST {PAYMENTS_URL}/payments/charge

    Body mirrors the WSDL's ChargePaymentRequest (merchantOrderId, studentId,
    amount, currency, paymentMethod), sent as JSON instead of a SOAP envelope.
    Returns the parsed JSON body on success (mirrors ChargePaymentResponse).
    Raises PaymentDeclined on a 4xx (never retried) and
    PaymentServiceUnavailable if every retry is exhausted.
    """
    url = f"{PAYMENTS_URL}/payments/charge"
    body = {
        "merchantOrderId": str(order_id),
        "studentId": student_id,
        "amount": amount,
        "currency": "INR",
        "paymentMethod": payment_method,
    }
    headers = {"Idempotency-Key": idempotency_key}

    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(url, json=body, headers=headers, timeout=TIMEOUT_SECONDS)
        except (requests.ConnectionError, requests.Timeout) as exc:
            # Network-level failure: safe to retry.
            last_error = str(exc)
            if attempt < MAX_ATTEMPTS:
                _sleep_backoff(attempt)
                continue
            raise PaymentServiceUnavailable(
                f"Payments service unreachable after {MAX_ATTEMPTS} attempts: {last_error}"
            )

        if resp.status_code == 200:
            return resp.json()

        if 400 <= resp.status_code < 500:
            # Client/domain-level failure (e.g. card declined). NEVER retried.
            try:
                detail = resp.json().get("detail", resp.text)
            except ValueError:
                detail = resp.text
            raise PaymentDeclined(detail)

        # 5xx from Payments: safe to retry.
        last_error = f"HTTP {resp.status_code}"
        if attempt < MAX_ATTEMPTS:
            _sleep_backoff(attempt)
            continue
        raise PaymentServiceUnavailable(
            f"Payments service returned {last_error} after {MAX_ATTEMPTS} attempts"
        )

    # Unreachable, but keep linters happy.
    raise PaymentServiceUnavailable(last_error or "unknown error")


def _sleep_backoff(attempt):
    """Exponential backoff (base * 2^(attempt-1)) plus random jitter."""
    delay = BASE_BACKOFF * (2 ** (attempt - 1)) + random.uniform(0, JITTER)
    time.sleep(delay)
