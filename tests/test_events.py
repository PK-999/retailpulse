import json

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
