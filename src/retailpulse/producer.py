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
    def __init__(self, settings: Settings) -> None:
        try:
            from confluent_kafka import Producer
        except ImportError as error:
            raise RuntimeError("Install the Kafka extra: pip install -e '.[kafka]'") from error
        configuration: dict[str, object] = {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "enable.idempotence": True,
            "acks": "all",
        }
        if settings.kafka_security_protocol != "PLAINTEXT":
            if not settings.kafka_sasl_password:
                raise ValueError("KAFKA_SASL_PASSWORD is required for authenticated Kafka")
            configuration.update(
                {
                    "security.protocol": settings.kafka_security_protocol,
                    "sasl.mechanism": settings.kafka_sasl_mechanism,
                    "sasl.username": settings.kafka_sasl_username,
                    "sasl.password": settings.kafka_sasl_password,
                    "request.timeout.ms": 60000,
                }
            )
        self.delivery_errors: list[str] = []
        self.run_id = settings.kafka_run_id
        self.producer = Producer(configuration)

    def _delivery_report(self, error, _message) -> None:
        if error is not None:
            self.delivery_errors.append(str(error))

    def send(self, message: GeneratedMessage) -> None:
        self.producer.produce(
            message.topic,
            message.payload.encode("utf-8"),
            headers=[
                ("retailpulse_scenario", message.scenario.encode("utf-8")),
                ("retailpulse_run_id", self.run_id.encode("utf-8")),
            ],
            on_delivery=self._delivery_report,
        )
        self.producer.poll(0)

    def close(self) -> None:
        remaining = self.producer.flush(60)
        if remaining:
            raise RuntimeError(f"Kafka delivery timed out for {remaining} event(s)")
        if self.delivery_errors:
            raise RuntimeError(
                f"Kafka delivery failed for {len(self.delivery_errors)} event(s): "
                f"{self.delivery_errors[0]}"
            )


def produce(
    settings: Settings,
    count: int,
    scenario: Scenario,
    seed: int | None = None,
    generator: EventGenerator | None = None,
) -> int:
    settings.ensure_directories()
    sink = (
        KafkaSink(settings)
        if settings.kafka_enabled
        else FileSink(settings.data_dir / "inbox")
    )
    produced = 0
    try:
        event_generator = generator or EventGenerator(seed=seed)
        for message in event_generator.generate(count, scenario):
            sink.send(message)
            produced += 1
    finally:
        sink.close()
    return produced
