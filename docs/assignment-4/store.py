"""
store.py
In-process storage for the Orders service (Part C1: no other service may
import this module).

Scope note (see NOTES.md): Assignment 2's placeOrder() calls three other
services -- Account (validateAddress), Catalogue (checkItem) and Payment
(charge). Assignment 4 only requires ONE real, hardened HTTP call (Part D),
so Account and Catalogue are simulated here as simple in-memory lookup
tables, exactly standing in for "call Account" / "call Catalogue" without
standing up two more Flask services. Only the Payments call in
payment_client.py is a real outbound HTTP request with a timeout, retry,
backoff+jitter and an idempotency key.
"""

import itertools

# ---------------------------------------------------------------------
# Orders storage
# ---------------------------------------------------------------------
_orders = {}                 # order_id -> Order
_idempotency_keys = {}       # idempotency_key -> order_id
_id_counter = itertools.count(1)


def next_order_id():
    return next(_id_counter)


def save_order(order):
    _orders[order.order_id] = order
    if order.idempotency_key:
        _idempotency_keys[order.idempotency_key] = order.order_id
    return order


def get_order(order_id):
    return _orders.get(order_id)


def find_by_idempotency_key(key):
    order_id = _idempotency_keys.get(key)
    return _orders.get(order_id) if order_id else None


def list_orders(student_id=None, status=None):
    results = list(_orders.values())
    if student_id is not None:
        results = [o for o in results if o.student_id == student_id]
    if status is not None:
        results = [o for o in results if o.status == status]
    return sorted(results, key=lambda o: o.order_id)


def reset():
    """Test-only helper to wipe state between test cases."""
    _orders.clear()
    _idempotency_keys.clear()
    global _id_counter
    _id_counter = itertools.count(1)


# ---------------------------------------------------------------------
# Simulated Account Service (validateAddress) -- see scope note above
# ---------------------------------------------------------------------
# studentId -> set of addressIds that belong to them
_KNOWN_ADDRESSES = {
    "STU-778812": {10, 11},
    "STU-001": {20},
}


def validate_address(student_id, address_id):
    """Stand-in for Account Service validateAddress(studentId, addressId)."""
    return address_id in _KNOWN_ADDRESSES.get(student_id, set())


# ---------------------------------------------------------------------
# Simulated Catalogue Service (checkItem) -- see scope note above
# ---------------------------------------------------------------------
# itemId -> (available, unitPrice, stock)
_CATALOGUE = {
    101: (True, 120.00, 50),
    102: (True, 45.50, 3),
    103: (False, 60.00, 0),   # always unavailable, for testing ITEM_UNAVAILABLE
    104: (True, 500.00, 100), # price chosen so payments_stub always returns 503 (D3 fallback demo)
}


def check_item(item_id, quantity):
    """Stand-in for Catalogue Service checkItem(itemId, quantity).

    Returns (available: bool, unit_price: float|None).
    Price is only ever read here, server-side -- never taken from the
    client request, matching the Assignment 2 placeOrder design.
    """
    entry = _CATALOGUE.get(item_id)
    if entry is None:
        return False, None
    available, unit_price, stock = entry
    if not available or stock < quantity:
        return False, unit_price
    return True, unit_price
