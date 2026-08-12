from __future__ import annotations

import argparse
import json

from retailpulse.config import Settings
from retailpulse.events import EventGenerator
from retailpulse.producer import produce
from retailpulse.profiles import load_profile

LARGE_RUN_THRESHOLD = 100_000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate profile-sized RetailPulse events.")
    parser.add_argument("--scale", choices=("dev", "demo", "azure"), default="dev")
    parser.add_argument("--count", type=int, help="Override the profile event count.")
    parser.add_argument(
        "--scenario",
        choices=("normal", "duplicate", "late-data", "malformed", "traffic-spike"),
        default="normal",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true", help="Validate and print the profile.")
    parser.add_argument(
        "--yes", action="store_true", help="Confirm generation above 100,000 events."
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profile = load_profile(args.scale)
    count = args.count if args.count is not None else profile.dataset.events
    if count < 1:
        raise SystemExit("--count must be positive")
    effective_count = count * (10 if args.scenario == "traffic-spike" else 1)

    summary = {
        "profile": profile.name,
        "execution": profile.execution.model_dump(),
        "dataset": profile.dataset.model_dump() | {"events_to_generate": effective_count},
    }
    if args.dry_run:
        print(json.dumps(summary, indent=2))
        return
    if effective_count > LARGE_RUN_THRESHOLD and not args.yes:
        raise SystemExit(
            f"Refusing to generate {effective_count:,} events without --yes; "
            "use --dry-run to inspect."
        )

    generator = EventGenerator(
        seed=args.seed,
        customer_count=profile.dataset.customers,
        product_count=profile.dataset.products,
        order_count=profile.dataset.orders,
    )
    settings = Settings.from_env()
    total = produce(settings, count, args.scenario, generator=generator)
    destination = "Kafka" if settings.kafka_enabled else str(settings.data_dir / "inbox")
    print(f"Produced {total:,} {args.scenario} events with {profile.name} scale to {destination}")


if __name__ == "__main__":
    main()
