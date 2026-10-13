"""
models.py
The Order model (Part C2). The class holds everything the service needs
to *store*; as_json() decides what the service is willing to *publish*.

Internal-only fields (never returned to a client):
  - idempotency_key : the Idempotency-Key the create request came in with
  - transaction_id  : the Payments service's internal transaction id

Those two fields exist on the record but are deliberately left out of
as_json(), which is the "differ in at least one field" requirement.
"""

from datetime import datetime, timezone

VALID_STATUSES = {"PENDING", "PLACED", "CANCELLED"}


class OrderItem:
    """One line of an order -- mirrors the OrderItem table from Assignment 2."""

    def __init__(self, item_id, quantity, unit_price):
        self.item_id = item_id
        self.quantity = quantity
        self.unit_price = unit_price  # fetched server-side, never trusted from client

    def as_json(self):
        return {
            "itemId": self.item_id,
            "quantity": self.quantity,
            "unitPrice": self.unit_price,
        }


class Order:
    """Mirrors the Orders table from Assignment 2 (docs/assignment-2/schema.sql)."""

    def __init__(
        self,
        order_id,
        student_id,
        address_id,
        payment_method,
        items,               # list[OrderItem]
        total_amount,
        status="PENDING",
        idempotency_key=None,
        transaction_id=None,
        created_at=None,
    ):
        self.order_id = order_id
        self.student_id = student_id
        self.address_id = address_id
        self.payment_method = payment_method
        self.items = items
        self.total_amount = total_amount
        self.status = status
        self.idempotency_key = idempotency_key   # internal only
        self.transaction_id = transaction_id      # internal only
        self.created_at = created_at or datetime.now(timezone.utc)

    def as_json(self):
        """What the client is allowed to see. No idempotency_key, no transaction_id."""
        return {
            "orderId": self.order_id,
            "studentId": self.student_id,
            "addressId": self.address_id,
            "paymentMethod": self.payment_method,
            "status": self.status,
            "total": round(self.total_amount, 2),
            "items": [i.as_json() for i in self.items],
            "createdAt": self.created_at.isoformat(),
        }
