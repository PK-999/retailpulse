import json
from pathlib import Path

import pytest

from retailpulse.events import EventGenerator
from retailpulse.profiles import load_profile


@pytest.mark.parametrize("name", ["dev", "demo", "azure"])
def test_execution_profiles_are_valid(name: str) -> None:
    profile = load_profile(name, Path("config"))
    assert profile.name == name
    assert profile.dataset.events > 0


def test_azure_profile_has_bounded_job_compute() -> None:
    profile = load_profile("azure")
    assert profile.databricks.compute_mode in {"job", "serverless_job"}
    assert 1 <= profile.databricks.max_runtime_minutes <= 30


def test_scaled_generator_uses_profile_identifier_domains() -> None:
    generator = EventGenerator(
        seed=7,
        customer_count=10,
        product_count=5,
        order_count=20,
    )
    events = [json.loads(message.payload) for message in generator.generate(50)]
    assert all(str(event["customer_id"]).startswith("CUST-") for event in events)
    assert all(
        event["product_id"] is None or str(event["product_id"]).startswith("PROD-")
        for event in events
    )
