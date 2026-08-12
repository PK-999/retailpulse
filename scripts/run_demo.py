from __future__ import annotations

import os
from pathlib import Path

from retailpulse.config import Settings
from retailpulse.incident import generate_report
from retailpulse.monitoring import evaluate, publish
from retailpulse.pipeline import LocalMedallionPipeline
from retailpulse.producer import produce


def main() -> None:
    if "RETAILPULSE_DATA_DIR" not in os.environ:
        os.environ["RETAILPULSE_DATA_DIR"] = str(Path("data").resolve())
    settings = Settings.from_env()
    settings.ensure_directories()
    pipeline = LocalMedallionPipeline(settings)

    print("1/4 Generating normal traffic")
    produce(settings, count=100, scenario="normal", seed=42)
    normal = pipeline.process()
    publish(settings, normal, evaluate(normal))
    print(f"    {normal.records_written} valid events reached Silver")

    print("2/4 Building Gold marts")
    gold = pipeline.build_gold()
    print(f"    orders={gold['orders']} revenue={gold['revenue']}")

    print("3/4 Injecting duplicate traffic")
    produce(settings, count=60, scenario="duplicate", seed=7)
    degraded = pipeline.process()
    alerts = evaluate(degraded)
    publish(settings, degraded, alerts)
    print(f"    duplicate_rate={degraded.duplicate_rate:.1%}, alerts={len(alerts)}")

    print("4/4 Generating incident analysis")
    report, source = generate_report(settings, degraded, alerts)
    print(f"    source={source}\n\n{report}")


if __name__ == "__main__":
    main()
