from __future__ import annotations

import json
import random
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from retailpulse.contracts import TOPIC_BY_EVENT, RetailEvent

Scenario = Literal["normal", "duplicate", "late-data", "malformed", "traffic-spike"]

PRODUCTS = [
    ("85123A", "Cream Hanging Heart", Decimal("2.55")),
    ("71053", "White Metal Lantern", Decimal("3.39")),
    ("84406B", "Cream Cupid Hearts Coat Hanger", Decimal("2.75")),
    ("84029G", "Knitted Union Flag Hot Water Bottle", Decimal("3.39")),
    ("22752", "Set 7 Babushka Nesting Boxes", Decimal("7.65")),
]
COUNTRIES = ["United Kingdom", "France", "Germany", "Netherlands", "Spain"]
EVENT_TYPES = [
    "product_view",
    "search",
    "add_to_cart",
    "checkout",
    "purchase",
    "payment",
    "inventory_update",
]


@dataclass
class GeneratedMessage:
    topic: str
    payload: str


class EventGenerator:
    def __init__(
        self,
        seed: int | None = None,
        *,
        customer_count: int | None = None,
        product_count: int | None = None,
        order_count: int | None = None,
    ) -> None:
        for label, value in (
            ("customer_count", customer_count),
            ("product_count", product_count),
            ("order_count", order_count),
        ):
            if value is not None and value < 1:
                raise ValueError(f"{label} must be positive")
        self.random = random.Random(seed)
        self.customer_count = customer_count
        self.product_count = product_count
        self.order_count = order_count

    def _customer_id(self) -> str:
        if self.customer_count is None:
            return str(self.random.randint(12346, 18287))
        return f"CUST-{self.random.randrange(self.customer_count):08d}"

    def _product(self) -> tuple[str, Decimal]:
        if self.product_count is None:
            product_id, _, price = self.random.choice(PRODUCTS)
            return product_id, price
        index = self.random.randrange(self.product_count)
        price = Decimal((index % 10000) + 100) / Decimal("100")
        return f"PROD-{index:08d}", price

    def _order_id(self) -> str:
        if self.order_count is None:
            return f"ORD-{self.random.randint(100000, 999999)}"
        return f"ORD-{self.random.randrange(self.order_count):09d}"

    def _event(self, late: bool = False) -> RetailEvent:
        event_type = self.random.choices(EVENT_TYPES, weights=[30, 12, 20, 8, 12, 10, 8])[0]
        product_id, price = self._product()
        timestamp = datetime.now(UTC)
        if late:
            timestamp -= timedelta(minutes=self.random.randint(31, 180))
        order_id = self._order_id()
        values = {
            "event_id": uuid4(),
            "event_type": event_type,
            "customer_id": self._customer_id(),
            "product_id": product_id if event_type != "search" else None,
            "order_id": order_id if event_type in {"checkout", "purchase", "payment"} else None,
            "quantity": self.random.randint(1, 5)
            if event_type in {"purchase", "inventory_update"}
            else None,
            "price": (
                price
                if event_type in {"add_to_cart", "checkout", "purchase", "payment"}
                else None
            ),
            "country": self.random.choice(COUNTRIES),
            "query": "gift" if event_type == "search" else None,
            "event_timestamp": timestamp,
        }
        if event_type == "checkout":
            values["product_id"] = None
        if event_type == "payment":
            values["product_id"] = None
        return RetailEvent.model_validate(values)

    def generate(self, count: int, scenario: Scenario = "normal") -> Iterator[GeneratedMessage]:
        multiplier = 10 if scenario == "traffic-spike" else 1
        previous: GeneratedMessage | None = None
        for index in range(count * multiplier):
            if scenario == "malformed" and index % 4 == 0:
                yield GeneratedMessage("order-events", '{"event_id": "broken", "event_type":')
                continue
            if scenario == "duplicate" and previous and index % 3 == 0:
                yield previous
                continue
            event = self._event(late=scenario == "late-data" and index % 3 == 0)
            payload = event.model_dump_json()
            previous = GeneratedMessage(TOPIC_BY_EVENT[event.event_type], payload)
            yield previous


def payload_as_dict(payload: str) -> dict[str, object]:
    return json.loads(payload)
