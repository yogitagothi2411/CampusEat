import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import app as app_module
import store

AUTH = {"Authorization": "Bearer campuseats-demo-token"}
VALID_ORDER = {
    "studentId": "STU-778812",
    "items": [{"itemId": 101, "quantity": 2}],
    "addressId": 10,
    "paymentMethod": "CARD",
}


@pytest.fixture(autouse=True)
def reset_state():
    store.reset()
    app_module._rate_state.clear()
    yield
    store.reset()
    app_module._rate_state.clear()


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
    resp = client.post("/orders", json=VALID_ORDER, headers={**AUTH, "Idempotency-Key": "key-1"})
    assert resp.status_code == 201
    assert resp.headers["Location"] == f"/orders/{resp.get_json()['orderId']}"
    assert resp.headers["Content-Type"].startswith("application/json")
    assert resp.get_json()["status"] == "PLACED"


def test_idempotent_repeat_returns_original(client, fake_charge_success):
    first = client.post("/orders", json=VALID_ORDER, headers={**AUTH, "Idempotency-Key": "same-key"})
    second = client.post("/orders", json=VALID_ORDER, headers={**AUTH, "Idempotency-Key": "same-key"})
    assert first.status_code == second.status_code == 201
    assert second.headers["Idempotency-Replayed"] == "true"
    assert second.get_json()["orderId"] == first.get_json()["orderId"]
    assert len(client.get("/orders", headers=AUTH).get_json()) == 1


def test_idempotency_key_reuse_with_different_body_is_409(client, fake_charge_success):
    client.post("/orders", json=VALID_ORDER, headers={**AUTH, "Idempotency-Key": "same"})
    changed = dict(VALID_ORDER)
    changed["paymentMethod"] = "UPI"
    resp = client.post("/orders", json=changed, headers={**AUTH, "Idempotency-Key": "same"})
    assert resp.status_code == 409


def test_malformed_body_returns_400(client):
    resp = client.post("/orders", json={"studentId": "STU-778812"}, headers=AUTH)
    assert resp.status_code == 400
    assert resp.get_json()["status"] == 400


def test_unknown_order_returns_404(client):
    resp = client.get("/orders/999999", headers=AUTH)
    assert resp.status_code == 404


def test_auth_missing_returns_401(client):
    resp = client.get("/orders/1")
    assert resp.status_code == 401
    assert "WWW-Authenticate" in resp.headers


def test_accept_negotiation_returns_406(client):
    resp = client.get("/orders/1", headers={**AUTH, "Accept": "text/html"})
    assert resp.status_code == 406


def test_etag_and_conditional_get(client, fake_charge_success):
    created = client.post("/orders", json=VALID_ORDER, headers={**AUTH, "Idempotency-Key": "etag"})
    oid = created.get_json()["orderId"]
    first = client.get(f"/orders/{oid}", headers=AUTH)
    assert first.status_code == 200
    assert first.headers["ETag"]
    second = client.get(f"/orders/{oid}", headers={**AUTH, "If-None-Match": first.headers["ETag"]})
    assert second.status_code == 304
    assert second.data == b""


def test_if_match_stale_returns_412(client, fake_charge_success):
    created = client.post("/orders", json=VALID_ORDER, headers={**AUTH, "Idempotency-Key": "ifmatch"})
    oid = created.get_json()["orderId"]
    resp = client.post(f"/orders/{oid}/cancellation", headers={**AUTH, "If-Match": '"stale"'})
    assert resp.status_code == 412


def test_cancel_conflict_returns_409(client, fake_charge_success):
    created = client.post("/orders", json=VALID_ORDER, headers={**AUTH, "Idempotency-Key": "cancel"})
    oid = created.get_json()["orderId"]
    assert client.post(f"/orders/{oid}/cancellation", headers=AUTH).status_code == 200
    assert client.post(f"/orders/{oid}/cancellation", headers=AUTH).status_code == 409


def test_options_returns_allow(client):
    resp = client.options("/orders", headers={"Origin": "http://localhost:3000"})
    assert resp.status_code == 204
    assert resp.headers["Allow"] == "GET, POST, OPTIONS"
    assert "Authorization" in resp.headers["Access-Control-Allow-Headers"]


def test_cors_and_security_headers(client):
    resp = client.options("/orders")
    assert resp.headers["Access-Control-Allow-Origin"] == "*"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert "Strict-Transport-Security" in resp.headers


def test_payment_unavailable_falls_back_to_503(client, monkeypatch):
    from payment_client import PaymentServiceUnavailable
    monkeypatch.setattr(app_module, "charge_payment", lambda *a, **k: (_ for _ in ()).throw(PaymentServiceUnavailable("down")))
    resp = client.post("/orders", json=VALID_ORDER, headers={**AUTH, "Idempotency-Key": "key-503"})
    assert resp.status_code == 503
