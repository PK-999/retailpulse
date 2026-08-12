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

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            data_dir=Path(os.getenv("RETAILPULSE_DATA_DIR", "data")).resolve(),
            kafka_bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092"),
            kafka_enabled=os.getenv("KAFKA_ENABLED", "false").lower() in {"1", "true", "yes"},
            ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
            ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
            ollama_timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180")),
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
