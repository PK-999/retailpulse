import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from retailpulse.contracts import RetailEvent
from retailpulse.events import EventGenerator


def test_normal_events_follow_contract() -> None:
    messages = list(EventGenerator(seed=42).generate(25, "normal"))
    assert len(messages) == 25
    assert {message.topic for message in messages} <= {
        "customer-events",
        "order-events",
        "inventory-events",
    }
    assert all(RetailEvent.model_validate_json(message.payload) for message in messages)


def test_duplicate_scenario_replays_event_id() -> None:
    messages = list(EventGenerator(seed=42).generate(12, "duplicate"))
    ids = [json.loads(message.payload)["event_id"] for message in messages]
    assert len(set(ids)) < len(ids)


def test_malformed_scenario_contains_bad_json() -> None:
    messages = list(EventGenerator(seed=42).generate(8, "malformed"))
    malformed = 0
    for message in messages:
        try:
            json.loads(message.payload)
        except json.JSONDecodeError:
            malformed += 1
    assert malformed == 2


def test_traffic_spike_multiplies_volume() -> None:
    assert len(list(EventGenerator(seed=1).generate(10, "traffic-spike"))) == 100


def test_order_identity_and_customer_country_are_consistent():
    orders, customers = {}, {}
    for seed in (42, 7):
        generator = EventGenerator(seed=seed, customer_count=5, order_count=3)
        for message in generator.generate(300):
            event = RetailEvent.model_validate_json(message.payload)
            assert customers.setdefault(event.customer_id, event.country) == event.country
            if event.order_id:
                identity = (event.customer_id, event.country)
                assert orders.setdefault(event.order_id, identity) == identity


@pytest.mark.parametrize("missing", ["schema_version", "order_id", "price"])
def test_purchase_requires_fields_used_by_gold(missing) -> None:
    payload = {
        "event_id": str(uuid4()),
        "event_type": "purchase",
        "product_id": "P1",
        "order_id": "O1",
        "quantity": 2,
        "price": "3.50",
        "event_timestamp": datetime.now(UTC).isoformat(),
        "schema_version": 1,
    }
    del payload[missing]
    with pytest.raises(ValidationError):
        RetailEvent.model_validate(payload)
