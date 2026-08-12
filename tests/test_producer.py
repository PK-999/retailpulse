import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from retailpulse.config import Settings
from retailpulse.events import GeneratedMessage
from retailpulse.producer import KafkaSink


class FakeProducer:
    instances: list["FakeProducer"] = []

    def __init__(self, configuration: dict[str, object]) -> None:
        self.configuration = configuration
        self.messages: list[dict[str, object]] = []
        self.__class__.instances.append(self)

    def produce(self, topic, payload, headers, on_delivery) -> None:
        self.messages.append({"topic": topic, "payload": payload, "headers": headers})
        on_delivery(None, None)

    def poll(self, _timeout: float) -> None:
        return None

    def flush(self, _timeout: float) -> int:
        return 0


def settings(password: str | None) -> Settings:
    return Settings(
        data_dir=Path("data"),
        kafka_bootstrap_servers="example.servicebus.windows.net:9093",
        kafka_enabled=True,
        ollama_url="http://localhost:11434",
        ollama_model="test",
        kafka_security_protocol="SASL_SSL",
        kafka_sasl_password=password,
        kafka_run_id="stage07-run",
    )


def test_event_hubs_producer_uses_sasl_idempotence_and_lineage_headers(monkeypatch) -> None:
    FakeProducer.instances.clear()
    monkeypatch.setitem(sys.modules, "confluent_kafka", SimpleNamespace(Producer=FakeProducer))

    sink = KafkaSink(settings("secret-value"))
    sink.send(GeneratedMessage("order-events", "{}", "malformed"))
    sink.close()

    producer = FakeProducer.instances[0]
    assert producer.configuration == {
        "bootstrap.servers": "example.servicebus.windows.net:9093",
        "enable.idempotence": True,
        "acks": "all",
        "security.protocol": "SASL_SSL",
        "sasl.mechanism": "PLAIN",
        "sasl.username": "$ConnectionString",
        "sasl.password": "secret-value",
        "request.timeout.ms": 60000,
    }
    assert producer.messages[0]["headers"] == [
        ("retailpulse_scenario", b"malformed"),
        ("retailpulse_run_id", b"stage07-run"),
    ]


def test_authenticated_kafka_requires_password(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "confluent_kafka", SimpleNamespace(Producer=FakeProducer))
    with pytest.raises(ValueError, match="KAFKA_SASL_PASSWORD"):
        KafkaSink(settings(None))
