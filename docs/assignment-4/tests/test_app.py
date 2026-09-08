"""
tests/test_app.py
Part C8: one test per required behaviour.

  1. test_create_order_succeeds        -> 201 + Location header
  2. test_idempotent_repeat_returns_original -> same Idempotency-Key twice
     does not create a second order
  3. test_malformed_body_returns_400   -> a failure path returns the right 4xx
  4. test_unknown_order_returns_404    -> unknown id -> 404

A couple of extra tests are included for the other documented status codes
(409 conflict, 503 fallback) since they were easy wins, but the four above
are the required minimum.

The Payments call is monkeypatched so these tests don't depend on a real
network hop -- payment_client.py itself is exercised separately via the
curl transcript against payments_stub.py.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import app as app_module
import store
from payment_client import PaymentDeclined, PaymentServiceUnavailable


VALID_ORDER = {
    "studentId": "STU-778812",
    "items": [{"itemId": 101, "quantity": 2}],
    "addressId": 10,
    "paymentMethod": "CARD",
}


@pytest.fixture(autouse=True)
def reset_state():
    store.reset()
    yield
    store.reset()


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture
def fake_charge_success(monkeypatch):
    def _fake(order_id, student_id, amount, payment_method, idempotency_key):
        return {"transactionId": "TXN-TEST-1", "status": "CAPTURED"}
    monkeypatch.setattr(app_module, "charge_payment", _fake)


def test_create_order_succeeds(client, fake_charge_success):
    resp = client.post("/orders", json=VALID_ORDER,
                        headers={"Idempotency-Key": "key-1"})
    assert resp.status_code == 201
    assert resp.headers["Location"] == f"/orders/{resp.get_json()['orderId']}"
    body = resp.get_json()
    assert body["status"] == "PLACED"
    assert body["studentId"] == "STU-778812"
    assert "idempotencyKey" not in body  # internal field must not leak


def test_idempotent_repeat_returns_original(client, fake_charge_success):
    first = client.post("/orders", json=VALID_ORDER,
                         headers={"Idempotency-Key": "same-key"})
    assert first.status_code == 201
    first_id = first.get_json()["orderId"]

    second = client.post("/orders", json=VALID_ORDER,
                          headers={"Idempotency-Key": "same-key"})
    assert second.status_code == 201
    assert second.get_json()["orderId"] == first_id  # no second order created

    all_orders = client.get("/orders").get_json()
    assert len(all_orders) == 1


def test_malformed_body_returns_400(client):
    bad = {"studentId": "STU-778812"}  # missing items/addressId/paymentMethod
    resp = client.post("/orders", json=bad)
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["status"] == 400
    assert "type" in body and "title" in body and "detail" in body


def test_unknown_order_returns_404(client):
    resp = client.get("/orders/999999")
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["status"] == 404
    assert "type" in body and "title" in body and "detail" in body


def test_cancel_conflict_returns_409(client, fake_charge_success):
    created = client.post("/orders", json=VALID_ORDER,
                           headers={"Idempotency-Key": "key-cancel"})
    order_id = created.get_json()["orderId"]

    first_cancel = client.post(f"/orders/{order_id}/cancellation")
    assert first_cancel.status_code == 200
    assert first_cancel.get_json()["status"] == "CANCELLED"

    second_cancel = client.post(f"/orders/{order_id}/cancellation")
    assert second_cancel.status_code == 409


def test_payment_unavailable_falls_back_to_503(client, monkeypatch):
    def _fake(**kwargs):
        raise PaymentServiceUnavailable("payments down for test")
    monkeypatch.setattr(app_module, "charge_payment", lambda *a, **k: _fake())

    resp = client.post("/orders", json=VALID_ORDER,
                        headers={"Idempotency-Key": "key-503"})
    assert resp.status_code == 503

    # order should exist internally as CANCELLED, not silently PLACED
    all_orders = store.list_orders()
    assert len(all_orders) == 1
    assert all_orders[0].status == "CANCELLED"
