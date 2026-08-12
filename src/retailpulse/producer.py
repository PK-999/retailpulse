from __future__ import annotations

from pathlib import Path

from retailpulse.config import Settings
from retailpulse.events import EventGenerator, GeneratedMessage, Scenario
from retailpulse.storage import append_raw


class FileSink:
    def __init__(self, inbox: Path) -> None:
        self.inbox = inbox

    def send(self, message: GeneratedMessage) -> None:
        append_raw(self.inbox / f"{message.topic}.jsonl", message.payload)

    def close(self) -> None:
        pass


class KafkaSink:
    def __init__(self, bootstrap_servers: str) -> None:
        try:
            from confluent_kafka import Producer
        except ImportError as error:
            raise RuntimeError("Install the Kafka extra: pip install -e '.[kafka]'") from error
        self.producer = Producer(
            {"bootstrap.servers": bootstrap_servers, "enable.idempotence": True}
        )

    def send(self, message: GeneratedMessage) -> None:
        self.producer.produce(message.topic, message.payload.encode("utf-8"))
        self.producer.poll(0)

    def close(self) -> None:
        remaining = self.producer.flush(10)
        if remaining:
            raise RuntimeError(f"Kafka delivery timed out for {remaining} event(s)")


def produce(settings: Settings, count: int, scenario: Scenario, seed: int | None = None) -> int:
    settings.ensure_directories()
    sink = (
        KafkaSink(settings.kafka_bootstrap_servers)
        if settings.kafka_enabled
        else FileSink(settings.data_dir / "inbox")
    )
    produced = 0
    try:
        for message in EventGenerator(seed=seed).generate(count, scenario):
            sink.send(message)
            produced += 1
    finally:
        sink.close()
    return produced
