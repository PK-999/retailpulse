from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from retailpulse.config import Settings
from retailpulse.events import Scenario
from retailpulse.incident import generate_report
from retailpulse.monitoring import evaluate, publish
from retailpulse.pipeline import LocalMedallionPipeline
from retailpulse.producer import produce as produce_events
from retailpulse.storage import connect

app = typer.Typer(help="RetailPulse local data-platform CLI", no_args_is_help=True)
console = Console()


@app.command()
def init() -> None:
    """Create the local medallion directory structure and metadata database."""
    settings = Settings.from_env()
    LocalMedallionPipeline(settings)
    console.print(f"Initialized RetailPulse at [cyan]{settings.data_dir}[/cyan]")


@app.command()
def produce(
    count: Annotated[int, typer.Option(min=1, max=100_000)] = 100,
    scenario: Scenario = "normal",
    seed: int | None = None,
) -> None:
    """Generate normal or intentionally degraded retail events."""
    settings = Settings.from_env()
    total = produce_events(settings, count=count, scenario=scenario, seed=seed)
    destination = "Kafka" if settings.kafka_enabled else str(settings.data_dir / "inbox")
    console.print(f"Produced [green]{total}[/green] {scenario} events to {destination}")


@app.command()
def process(
    analyze: Annotated[bool, typer.Option(help="Generate an incident report")] = True,
    ollama: Annotated[bool, typer.Option(help="Use Ollama; gracefully fall back to rules")] = False,
) -> None:
    """Incrementally process file-backed local streams through Bronze and Silver."""
    settings = Settings.from_env()
    pipeline = LocalMedallionPipeline(settings)
    stats = pipeline.process()
    metrics = pipeline.build_gold()
    alerts = evaluate(stats)
    publish(settings, stats, alerts)
    table = Table(title=f"Pipeline run {stats.run_id}")
    table.add_column("read")
    table.add_column("written")
    table.add_column("rejected")
    table.add_column("duplicates")
    table.add_column("late")
    table.add_column("alerts")
    table.add_row(
        *map(
            str,
            (
                stats.records_read,
                stats.records_written,
                stats.records_rejected,
                stats.records_duplicate,
                stats.records_late,
                len(alerts),
            ),
        )
    )
    console.print(table)
    console.print("Gold:", json.dumps(metrics))
    if analyze:
        report, source = generate_report(settings, stats, alerts, use_ollama=ollama)
        console.print(f"\n[bold]Incident analysis ({source})[/bold]\n{report}")


@app.command()
def status() -> None:
    """Show recent pipeline executions."""
    settings = Settings.from_env()
    pipeline = LocalMedallionPipeline(settings)
    with connect(pipeline.database) as connection:
        rows = connection.execute(
            "SELECT * FROM pipeline_run_log ORDER BY start_time DESC LIMIT 10"
        ).fetchall()
    table = Table("run_id", "status", "read", "written", "rejected", "duplicate", "late")
    for row in rows:
        table.add_row(
            row["run_id"][:8],
            row["status"],
            str(row["records_read"]),
            str(row["records_written"]),
            str(row["records_rejected"]),
            str(row["records_duplicate"]),
            str(row["records_late"]),
        )
    console.print(table)


@app.command()
def reset(
    yes: Annotated[bool, typer.Option("--yes", help="Confirm deletion of local data")] = False,
) -> None:
    """Delete generated local state. Azure resources are never affected."""
    if not yes:
        raise typer.BadParameter("Pass --yes to delete generated local data")
    settings = Settings.from_env()
    protected = {Path("/"), Path.home().resolve(), Path.cwd().resolve()}
    if settings.data_dir.resolve() in protected:
        raise typer.BadParameter(f"Refusing to remove protected path: {settings.data_dir}")
    if settings.data_dir.exists():
        shutil.rmtree(settings.data_dir)
    console.print(f"Removed generated data at {settings.data_dir}")


if __name__ == "__main__":
    app()
