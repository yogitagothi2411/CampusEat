"""Assignment 6 tests (plain unittest; `pytest tests/` also runs them).

Part 1 re-checks the Assignment 5 behaviour (idempotency, timeouts/503, ETag,
conditional writes) so we can show there are no regressions.
Part 2 covers A6: status codes, Problem Details, 422 field errors,
content negotiation, Retry-After and the clean 500.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module  # noqa: E402
import errors  # noqa: E402
import store  # noqa: E402
from payment_client import PaymentDeclined, PaymentServiceUnavailable  # noqa: E402

AUTH = {"Authorization": "Bearer campuseats-demo-token"}
VALID_ORDER = {
    "studentId": "STU-778812",
    "items": [{"itemId": 101, "quantity": 2}],
    "addressId": 10,
    "paymentMethod": "CARD",
}
PROBLEM_JSON = "application/problem+json; charset=utf-8"


def ok_charge(order_id, student_id, amount, payment_method, idempotency_key):
    return {"transactionId": "TXN-TEST-1", "status": "CAPTURED"}


class Base(unittest.TestCase):
    def setUp(self):
        store.reset()
        app_module._rate_state.clear()
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        patcher = mock.patch.object(app_module, "charge_payment", ok_charge)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(store.reset)

    def post(self, body=VALID_ORDER, headers=None, **kw):
        return self.client.post("/orders", json=body, headers={**AUTH, **(headers or {})}, **kw)

    def assert_problem(self, resp, status, slug):
        self.assertEqual(resp.status_code, status)
        self.assertEqual(resp.headers["Content-Type"], PROBLEM_JSON)
        body = resp.get_json()
        self.assertEqual(set(["type", "title", "status", "detail"]) - set(body), set())
        self.assertEqual(body["status"], status)
        self.assertTrue(body["type"].endswith("/" + slug), body["type"])
        return body


# ------------------------------------------------------------------ A5 regression
class A5Regression(Base):
    def test_create_order_succeeds(self):
        resp = self.post(headers={"Idempotency-Key": "key-1"})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.headers["Location"], f"/orders/{resp.get_json()['orderId']}")
        self.assertEqual(resp.headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(resp.get_json()["status"], "PLACED")

    def test_idempotent_repeat_returns_original(self):
        first = self.post(headers={"Idempotency-Key": "same-key"})
        second = self.post(headers={"Idempotency-Key": "same-key"})
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second.headers["Idempotency-Replayed"], "true")
        self.assertEqual(second.get_json()["orderId"], first.get_json()["orderId"])
        self.assertEqual(second.headers["Location"], first.headers["Location"])
        self.assertEqual(len(self.client.get("/orders", headers=AUTH).get_json()), 1)

    def test_idempotency_key_reuse_with_different_body_is_409(self):
        self.post(headers={"Idempotency-Key": "same"})
        changed = dict(VALID_ORDER, paymentMethod="UPI")
        resp = self.post(changed, headers={"Idempotency-Key": "same"})
        self.assert_problem(resp, 409, "idempotency-conflict")

    def test_charge_called_once_for_replayed_key(self):
        calls = []
        def counting(**kw):
            calls.append(kw)
            return {"transactionId": "T"}
        with mock.patch.object(app_module, "charge_payment", counting):
            self.post(headers={"Idempotency-Key": "once"})
            self.post(headers={"Idempotency-Key": "once"})
        self.assertEqual(len(calls), 1)

    def test_etag_and_conditional_get(self):
        oid = self.post().get_json()["orderId"]
        first = self.client.get(f"/orders/{oid}", headers=AUTH)
        self.assertEqual(first.status_code, 200)
        second = self.client.get(f"/orders/{oid}", headers={**AUTH, "If-None-Match": first.headers["ETag"]})
        self.assertEqual(second.status_code, 304)
        self.assertEqual(second.data, b"")
        self.assertNotIn("Content-Type", second.headers)

    def test_if_match_stale_returns_412(self):
        oid = self.post().get_json()["orderId"]
        resp = self.client.post(f"/orders/{oid}/cancellation", headers={**AUTH, "If-Match": '"stale"'})
        self.assert_problem(resp, 412, "precondition-failed")

    def test_if_match_current_etag_allows_cancel(self):
        oid = self.post().get_json()["orderId"]
        etag = self.client.get(f"/orders/{oid}", headers=AUTH).headers["ETag"]
        resp = self.client.post(f"/orders/{oid}/cancellation", headers={**AUTH, "If-Match": etag})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "CANCELLED")

    def test_options_returns_allow(self):
        resp = self.client.options("/orders", headers={"Origin": "http://localhost:3000"})
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(resp.headers["Allow"], "GET, POST, OPTIONS")

    def test_cors_and_security_headers(self):
        resp = self.client.options("/orders")
        self.assertEqual(resp.headers["Access-Control-Allow-Origin"], "*")
        self.assertEqual(resp.headers["X-Content-Type-Options"], "nosniff")

    def test_payment_client_timeout_budget_unchanged(self):
        import payment_client
        self.assertEqual(payment_client.TIMEOUT_SECONDS, 2.0)
        self.assertEqual(payment_client.MAX_ATTEMPTS, 3)


class PaymentClientRetries(unittest.TestCase):
    """A5 timeout/retry behaviour: network errors and 5xx retried, 4xx never."""

    def test_timeout_is_retried_then_unavailable(self):
        import requests
        import payment_client
        with mock.patch.object(payment_client.requests, "post", side_effect=requests.Timeout("slow")) as post, \
                mock.patch.object(payment_client, "_sleep_backoff"):
            with self.assertRaises(PaymentServiceUnavailable):
                payment_client.charge_payment(1, "S", 10.0, "CARD", "k")
        self.assertEqual(post.call_count, 3)
        self.assertEqual(post.call_args.kwargs["timeout"], 2.0)

    def test_4xx_is_never_retried(self):
        import payment_client
        resp = mock.Mock(status_code=422, text="no", json=lambda: {"detail": "declined"})
        with mock.patch.object(payment_client.requests, "post", return_value=resp) as post:
            with self.assertRaises(PaymentDeclined):
                payment_client.charge_payment(1, "S", 10.0, "CARD", "k")
        self.assertEqual(post.call_count, 1)

    def test_same_idempotency_key_on_every_attempt(self):
        import requests
        import payment_client
        with mock.patch.object(payment_client.requests, "post", side_effect=requests.ConnectionError("x")) as post, \
                mock.patch.object(payment_client, "_sleep_backoff"):
            with self.assertRaises(PaymentServiceUnavailable):
                payment_client.charge_payment(1, "S", 10.0, "CARD", "stable-key")
        keys = {c.kwargs["headers"]["Idempotency-Key"] for c in post.call_args_list}
        self.assertEqual(keys, {"stable-key"})


# ------------------------------------------------------------------ A6: status + Problem Details
class StatusMap(Base):
    def test_unknown_order_404(self):
        body = self.assert_problem(self.client.get("/orders/999999", headers=AUTH), 404, "order-not-found")
        self.assertIn("999999", body["detail"])

    def test_unknown_url_404_is_problem_json(self):
        self.assert_problem(self.client.get("/nope", headers=AUTH), 404, "not-found")

    def test_missing_auth_401(self):
        resp = self.client.get("/orders/1")
        self.assert_problem(resp, 401, "unauthorized")
        self.assertIn("WWW-Authenticate", resp.headers)

    def test_illegal_transition_409(self):
        oid = self.post().get_json()["orderId"]
        self.assertEqual(self.client.post(f"/orders/{oid}/cancellation", headers=AUTH).status_code, 200)
        resp = self.client.post(f"/orders/{oid}/cancellation", headers=AUTH)
        body = self.assert_problem(resp, 409, "illegal-transition")
        self.assertIn("CANCELLED", body["detail"])

    def test_cancel_unknown_order_404(self):
        self.assert_problem(self.client.post("/orders/77/cancellation", headers=AUTH), 404, "order-not-found")

    def test_patch_and_delete_are_405_with_allow(self):
        for method in ("patch", "delete"):
            resp = getattr(self.client, method)("/orders/1", headers=AUTH)
            self.assert_problem(resp, 405, "method-not-allowed")
            self.assertIn("GET", resp.headers["Allow"])

    def test_head_works_on_get_resources(self):
        oid = self.post().get_json()["orderId"]
        resp = self.client.head(f"/orders/{oid}", headers=AUTH)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, b"")

    def test_location_points_at_new_order(self):
        resp = self.post()
        self.assertEqual(resp.status_code, 201)
        oid = resp.get_json()["orderId"]
        self.assertEqual(resp.headers["Location"], f"/orders/{oid}")
        self.assertEqual(self.client.get(resp.headers["Location"], headers=AUTH).status_code, 200)

    def test_no_200_with_ok_false_anywhere(self):
        failing = [
            self.post({}), self.post({**VALID_ORDER, "items": []}),
            self.client.get("/orders/424242", headers=AUTH),
            self.client.get("/orders?status=BOGUS", headers=AUTH),
            self.client.get("/orders/1", headers={**AUTH, "Accept": "text/html"}),
        ]
        for resp in failing:
            self.assertGreaterEqual(resp.status_code, 400)
            self.assertNotEqual(resp.status_code, 200)
            self.assertNotIn("ok", resp.get_json())


class Validation(Base):
    def test_empty_cart_422(self):
        resp = self.post({**VALID_ORDER, "items": []})
        body = self.assert_problem(resp, 422, "empty-cart")
        self.assertEqual(body["errors"][0]["field"], "items")

    def test_quantity_zero_negative_float_and_bool(self):
        for bad in (0, -3, 1.5, "2", True):
            resp = self.post({**VALID_ORDER, "items": [{"itemId": 101, "quantity": bad}]})
            body = self.assert_problem(resp, 422, "validation-error")
            self.assertEqual(body["errors"][0]["field"], "items[0].quantity")

    def test_two_bad_fields_reported_at_once(self):
        resp = self.post({"studentId": "STU-778812", "items": [{"itemId": 101, "quantity": 0}],
                          "paymentMethod": "CARD"})
        body = self.assert_problem(resp, 422, "validation-error")
        self.assertEqual([e["field"] for e in body["errors"]], ["items[0].quantity", "addressId"])
        for e in body["errors"]:
            self.assertTrue(e["message"])

    def test_all_errors_collected_not_just_first(self):
        resp = self.post({"items": [{"quantity": 0}, "x"], "paymentMethod": "CHEQUE"})
        fields = [e["field"] for e in resp.get_json()["errors"]]
        self.assertEqual(fields, ["studentId", "items[0].itemId", "items[0].quantity",
                                  "items[1]", "addressId", "paymentMethod"])

    def test_nothing_done_when_invalid(self):
        calls = []
        with mock.patch.object(app_module, "charge_payment", lambda **k: calls.append(k)):
            self.post({**VALID_ORDER, "addressId": None})
        self.assertEqual(calls, [])
        self.assertEqual(self.client.get("/orders", headers=AUTH).get_json(), [])

    def test_address_required(self):
        body = {k: v for k, v in VALID_ORDER.items() if k != "addressId"}
        resp = self.post(body)
        self.assertEqual(resp.get_json()["errors"], [{"field": "addressId", "message": "is required"}])

    def test_malformed_json_is_400_not_422(self):
        resp = self.client.post("/orders", data="{not json", headers={**AUTH, "Content-Type": "application/json"})
        body = self.assert_problem(resp, 400, "malformed-body")
        self.assertNotIn("Traceback", str(body))

    def test_missing_body_is_400(self):
        self.assert_problem(self.client.post("/orders", headers=AUTH), 400, "malformed-body")

    def test_json_array_body_is_400(self):
        self.assert_problem(self.post([1, 2]), 400, "malformed-body")

    def test_wrong_content_type_415(self):
        resp = self.client.post("/orders", data="studentId=1", headers={**AUTH, "Content-Type": "text/plain"})
        self.assert_problem(resp, 415, "unsupported-media-type")

    def test_unavailable_item_422_lists_each(self):
        resp = self.post({**VALID_ORDER, "items": [{"itemId": 103, "quantity": 1}, {"itemId": 999, "quantity": 1},
                                                   {"itemId": 101, "quantity": 1}]})
        body = self.assert_problem(resp, 422, "item-unavailable")
        self.assertEqual([e["field"] for e in body["errors"]], ["items[0].itemId", "items[1].itemId"])

    def test_foreign_address_422(self):
        body = self.assert_problem(self.post({**VALID_ORDER, "addressId": 20}), 422, "invalid-address")
        self.assertEqual(body["errors"][0]["field"], "addressId")

    def test_bad_query_params_422_all_at_once(self):
        resp = self.client.get("/orders?status=BOGUS&page=0&pageSize=abc&sortOrder=up", headers=AUTH)
        body = self.assert_problem(resp, 422, "validation-error")
        self.assertEqual([e["field"] for e in body["errors"]], ["status", "sortOrder", "page", "pageSize"])
        self.assertIn("query string", body["detail"])


# ------------------------------------------------------------------ A6: payment + retry-safety + internals
class PaymentAndRetry(Base):
    def test_payment_declined_422_clean_detail(self):
        with mock.patch.object(app_module, "charge_payment",
                               mock.Mock(side_effect=PaymentDeclined("bank 4111 insufficient funds acct 99"))):
            resp = self.post()
        body = self.assert_problem(resp, 422, "payment-declined")
        self.assertNotIn("4111", str(body))
        self.assertNotIn("acct", str(body))

    def test_503_has_retry_after_and_hides_upstream_text(self):
        exc = PaymentServiceUnavailable("HTTPConnectionPool(host='10.0.0.7', port=5001): Max retries exceeded")
        with mock.patch.object(app_module, "charge_payment", mock.Mock(side_effect=exc)):
            resp = self.post(headers={"Idempotency-Key": "k503"})
        body = self.assert_problem(resp, 503, "payment-service-unavailable")
        self.assertEqual(resp.headers["Retry-After"], "5")
        self.assertNotIn("10.0.0.7", str(body))
        self.assertNotIn("HTTPConnectionPool", str(body))

    def test_503_is_not_cached_so_same_key_retry_can_succeed(self):
        exc = PaymentServiceUnavailable("down")
        with mock.patch.object(app_module, "charge_payment", mock.Mock(side_effect=exc)):
            self.assertEqual(self.post(headers={"Idempotency-Key": "retry-me"}).status_code, 503)
        retry = self.post(headers={"Idempotency-Key": "retry-me"})   # payments recovered
        self.assertEqual(retry.status_code, 201)
        self.assertNotIn("Idempotency-Replayed", retry.headers)

    def test_declined_is_remembered_and_replayed_unchanged(self):
        with mock.patch.object(app_module, "charge_payment", mock.Mock(side_effect=PaymentDeclined("no"))):
            first = self.post(headers={"Idempotency-Key": "dec"})
        second = self.post(headers={"Idempotency-Key": "dec"})  # charge not called again
        self.assertEqual((first.status_code, second.status_code), (422, 422))
        self.assertEqual(second.headers["Idempotency-Replayed"], "true")
        self.assertEqual(second.headers["Content-Type"], PROBLEM_JSON)

    def test_429_has_retry_after(self):
        with mock.patch.object(app_module, "RATE_LIMIT", 2):
            self.client.get("/orders", headers=AUTH)
            self.client.get("/orders", headers=AUTH)
            resp = self.client.get("/orders", headers=AUTH)
        self.assert_problem(resp, 429, "rate-limited")
        self.assertGreaterEqual(int(resp.headers["Retry-After"]), 1)

    def test_unexpected_exception_is_clean_500(self):
        secret = 'psycopg2.OperationalError: could not connect to 10.0.3.14: SELECT * FROM orders'
        with mock.patch.object(store, "get_order", side_effect=RuntimeError(secret)):
            with self.assertLogs(app_module.app.logger, level="ERROR") as logs:
                resp = self.client.get("/orders/1", headers=AUTH)
        body = self.assert_problem(resp, 500, "internal-error")
        text = resp.get_data(as_text=True)
        for leak in ("psycopg2", "10.0.3.14", "SELECT", "Traceback", "RuntimeError", ".py"):
            self.assertNotIn(leak, text)
        self.assertEqual(len(body["errorId"]), 12)
        joined = "\n".join(logs.output)            # ... but the server log has everything
        self.assertIn(body["errorId"], joined)
        self.assertIn("psycopg2", joined)
        self.assertIn("Traceback", joined)


# ------------------------------------------------------------------ A6: content negotiation
class Negotiation(Base):
    def test_default_is_json(self):
        self.assertEqual(self.client.get("/orders", headers=AUTH).headers["Content-Type"],
                         "application/json; charset=utf-8")

    def test_negotiate_function(self):
        n = app_module.negotiate
        self.assertEqual(n(None), "json")
        self.assertEqual(n("*/*"), "json")
        self.assertEqual(n("application/xml"), "xml")
        self.assertEqual(n("application/xml, */*"), "xml")
        self.assertEqual(n("application/*"), "json")
        self.assertEqual(n("application/xml;q=0.5, application/json;q=0.9"), "json")
        self.assertEqual(n("application/json;q=0, application/xml"), "xml")
        self.assertEqual(n("text/html, */*;q=0.1"), "json")
        self.assertIsNone(n("text/html"))
        self.assertIsNone(n("application/json;q=0"))

    def test_xml_order(self):
        oid = self.post().get_json()["orderId"]
        resp = self.client.get(f"/orders/{oid}", headers={**AUTH, "Accept": "application/xml"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["Content-Type"], "application/xml; charset=utf-8")
        from xml.etree import ElementTree as ET
        root = ET.fromstring(resp.data)
        self.assertEqual(root.tag, "order")
        self.assertEqual(root.findtext("orderId"), str(oid))
        self.assertEqual(root.findtext("items/item/quantity"), "2")

    def test_xml_create_and_list(self):
        resp = self.post(headers={"Accept": "application/xml"})
        self.assertEqual((resp.status_code, resp.headers["Content-Type"]), (201, "application/xml; charset=utf-8"))
        lst = self.client.get("/orders", headers={**AUTH, "Accept": "application/xml"})
        self.assertTrue(lst.data.decode().count("<order>") == 1 and "<orders>" in lst.data.decode())

    def test_xml_error_is_problem_xml(self):
        resp = self.client.get("/orders/5", headers={**AUTH, "Accept": "application/xml"})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.headers["Content-Type"], "application/problem+xml; charset=utf-8")
        self.assertIn("urn:ietf:rfc:9457", resp.get_data(as_text=True))

    def test_xml_422_lists_errors(self):
        resp = self.post({**VALID_ORDER, "items": [{"itemId": 101, "quantity": 0}], "addressId": None},
                         headers={"Accept": "application/xml"})
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.get_data(as_text=True).count("<error>"), 2)

    def test_406_for_unproducible(self):
        resp = self.client.get("/orders/1", headers={**AUTH, "Accept": "text/html"})
        self.assert_problem(resp, 406, "not-acceptable")

    def test_etag_differs_per_representation_and_either_works_for_if_match(self):
        oid = self.post().get_json()["orderId"]
        j = self.client.get(f"/orders/{oid}", headers=AUTH).headers["ETag"]
        x = self.client.get(f"/orders/{oid}", headers={**AUTH, "Accept": "application/xml"}).headers["ETag"]
        self.assertNotEqual(j, x)
        self.assertEqual(self.client.get(f"/orders/{oid}", headers={**AUTH, "Accept": "application/xml",
                                                                     "If-None-Match": x}).status_code, 304)
        self.assertEqual(self.client.post(f"/orders/{oid}/cancellation",
                                          headers={**AUTH, "If-Match": x}).status_code, 200)

    def test_replay_follows_current_accept(self):
        self.post(headers={"Idempotency-Key": "neg"})
        replay = self.post(headers={"Idempotency-Key": "neg", "Accept": "application/xml"})
        self.assertEqual(replay.headers["Content-Type"], "application/xml; charset=utf-8")
        self.assertEqual(replay.headers["Idempotency-Replayed"], "true")


class ContentTypeEverywhere(Base):
    def test_every_body_has_charset(self):
        probes = [
            self.client.get("/orders", headers=AUTH),
            self.client.get("/orders/9", headers=AUTH),
            self.client.get("/orders/9"),
            self.client.get("/nope", headers=AUTH),
            self.client.delete("/orders/1", headers=AUTH),
            self.post({}),
            self.post(),
            self.client.get("/orders/1", headers={**AUTH, "Accept": "image/png"}),
        ]
        for resp in probes:
            self.assertIn("charset=utf-8", resp.headers["Content-Type"].lower(), resp.status_code)


if __name__ == "__main__":
    unittest.main()
