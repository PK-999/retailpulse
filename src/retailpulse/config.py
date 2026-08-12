from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    kafka_bootstrap_servers: str
    kafka_enabled: bool
    ollama_url: str
    ollama_model: str
    ollama_timeout_seconds: float = 180.0
    kafka_security_protocol: str = "PLAINTEXT"
    kafka_sasl_mechanism: str = "PLAIN"
    kafka_sasl_username: str = "$ConnectionString"
    kafka_sasl_password: str | None = None
    kafka_run_id: str = "local"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            data_dir=Path(os.getenv("RETAILPULSE_DATA_DIR", "data")).resolve(),
            kafka_bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092"),
            kafka_enabled=os.getenv("KAFKA_ENABLED", "false").lower() in {"1", "true", "yes"},
            ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
            ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
            ollama_timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180")),
            kafka_security_protocol=os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT"),
            kafka_sasl_mechanism=os.getenv("KAFKA_SASL_MECHANISM", "PLAIN"),
            kafka_sasl_username=os.getenv("KAFKA_SASL_USERNAME", "$ConnectionString"),
            kafka_sasl_password=os.getenv("KAFKA_SASL_PASSWORD"),
            kafka_run_id=os.getenv("KAFKA_RUN_ID", "local"),
        )

    def ensure_directories(self) -> None:
        for name in (
            "landing",
            "bronze",
            "silver",
            "gold",
            "checkpoints",
            "quarantine",
            "inbox",
            "metrics",
            "incidents",
        ):
            (self.data_dir / name).mkdir(parents=True, exist_ok=True)
