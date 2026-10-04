from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

import httpx

from retailpulse.config import Settings
from retailpulse.monitoring import Alert
from retailpulse.pipeline import RunStats
from retailpulse.storage import write_text


def normalize_ollama_report(response: str) -> str:
    """Remove model chatter while preserving the required four-section report."""
    lines = [
        line.strip().replace("**", "") for line in response.strip().splitlines() if line.strip()
    ]
    required = ("Incident", "Evidence", "Likely cause", "Action")
    sections: list[str] = []
    for heading in required:
        pattern = re.compile(
            rf"^(?:#+\s*)?{re.escape(heading)}\s*:\s*(.+)$",
            re.IGNORECASE,
        )
        match = next((pattern.match(line) for line in lines if pattern.match(line)), None)
        if match is None:
            raise ValueError(f"Ollama response is missing the {heading!r} section")
        sections.append(f"{heading}: {match.group(1).strip()}")
    return "\n".join(sections)


def deterministic_report(stats: RunStats, alerts: list[Alert]) -> str:
    if not alerts:
        return (
            f"Incident check: {stats.pipeline_name}\n\n"
            "No incident detected. Data-quality rates are within configured thresholds."
        )
    causes: list[str] = []
    actions: list[str] = []
    if any(alert.metric == "pipeline_failure" for alert in alerts):
        causes.append("the run failed; its metrics alone do not identify the exception")
        actions.append(
            "inspect the exception and audit, restore storage access, and rerun "
            "from committed input offsets"
        )
    if any(alert.metric == "duplicate_rate" for alert in alerts):
        causes.append("events were likely replayed by a producer or consumer retry")
        actions.append("verify producer idempotency and retain event_id deduplication before MERGE")
    if any(alert.metric == "rejection_rate" for alert in alerts):
        causes.append("payloads no longer conform to schema version 1")
        actions.append("inspect quarantine samples and coordinate a versioned contract change")
    if any(alert.metric == "late_event_rate" for alert in alerts):
        causes.append("upstream delivery exceeded the 30-minute watermark")
        actions.append("check producer clocks and transport backlog before adjusting the watermark")
    metrics = ", ".join(
        "pipeline_failure=failed" if a.metric == "pipeline_failure" else f"{a.metric}={a.value:.1%}"
        for a in alerts
    )
    return (
        f"Incident: {stats.pipeline_name}\n\n"
        f"Detected anomalous data quality in run {stats.run_id}: {metrics}.\n\n"
        f"Likely cause: {'; '.join(causes)}.\n\n"
        f"Recommended action: {'; '.join(actions)}. Quarantined data remains available for replay."
    )


def generate_report(
    settings: Settings, stats: RunStats, alerts: list[Alert], use_ollama: bool = False
) -> tuple[str, str]:
    fallback = deterministic_report(stats, alerts)
    source = "rules"
    report = fallback
    if use_ollama:
        prompt = (
            "You are a DataOps incident editor. Rewrite the deterministic draft below in at most "
            "75 words using exactly these headings: Incident, Evidence, Likely cause, Action. "
            "The draft is the only allowed factual source. Do not introduce new causes, metrics, "
            "risks, or recommendations. Never discuss a metric unless it appears in the draft.\n\n"
            f"Deterministic draft:\n{fallback}\n\nMachine context for identifiers only:\n"
            + json.dumps(
                {"run": asdict(stats), "alerts": [asdict(alert) for alert in alerts]}, default=str
            )
        )
        try:
            response = httpx.post(
                f"{settings.ollama_url}/api/generate",
                json={
                    "model": settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.0, "num_predict": 140},
                },
                timeout=settings.ollama_timeout_seconds,
            )
            response.raise_for_status()
            report = normalize_ollama_report(response.json()["response"])
            source = "ollama"
        except (httpx.HTTPError, KeyError, ValueError):
            source = "rules-fallback"
    output: Path = settings.data_dir / "incidents" / f"{stats.run_id}.md"
    write_text(output, report + "\n")
    return report, source
