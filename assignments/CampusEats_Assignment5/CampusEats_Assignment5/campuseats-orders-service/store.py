"""In-memory Orders storage plus simulated Account/Catalogue lookups."""

import itertools
import json

_orders = {}
_idempotency_keys = {}
_idempotency_payloads = {}
_idempotency_results = {}
_id_counter = itertools.count(1)


def next_order_id():
    return next(_id_counter)


def canonical_payload(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def save_order(order, canonical_payload=None):
    _orders[order.order_id] = order
    if order.idempotency_key:
        _idempotency_keys[order.idempotency_key] = order.order_id
        if canonical_payload is not None:
            _idempotency_payloads[order.idempotency_key] = globals()["canonical_payload"](canonical_payload)
    return order


def get_order(order_id):
    return _orders.get(order_id)


def find_by_idempotency_key(key):
    order_id = _idempotency_keys.get(key)
    return _orders.get(order_id) if order_id else None


def idempotency_payload(key):
    return _idempotency_payloads.get(key)


def save_idempotency_result(key, status, body, headers=None):
    if key:
        _idempotency_results[key] = {"status": status, "body": body, "headers": headers or {}}


def idempotency_result(key):
    return _idempotency_results.get(key)


def list_orders(student_id=None, status=None):
    results = list(_orders.values())
    if student_id is not None:
        results = [o for o in results if o.student_id == student_id]
    if status is not None:
        results = [o for o in results if o.status == status]
    return sorted(results, key=lambda o: o.order_id)


def reset():
    _orders.clear()
    _idempotency_keys.clear()
    _idempotency_payloads.clear()
    _idempotency_results.clear()
    global _id_counter
    _id_counter = itertools.count(1)


_KNOWN_ADDRESSES = {"STU-778812": {10, 11}, "STU-001": {20}}


def validate_address(student_id, address_id):
    return address_id in _KNOWN_ADDRESSES.get(student_id, set())


_CATALOGUE = {
    101: (True, 120.00, 50),
    102: (True, 45.50, 3),
    103: (False, 60.00, 0),
    104: (True, 500.00, 100),
}


def check_item(item_id, quantity):
    entry = _CATALOGUE.get(item_id)
    if entry is None:
        return False, None
    available, unit_price, stock = entry
    if not available or stock < quantity:
        return False, unit_price
    return True, unit_price
