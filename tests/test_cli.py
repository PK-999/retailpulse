import json

from typer.testing import CliRunner

from retailpulse.cli import app
from retailpulse.pipeline import LocalMedallionPipeline

runner = CliRunner()


def test_cli_runs_local_pipeline_and_reports_status(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RETAILPULSE_DATA_DIR", str(tmp_path / "demo"))
    monkeypatch.setenv("KAFKA_ENABLED", "false")
    for arguments in (
        ["init"],
        ["produce", "--count", "100", "--seed", "42"],
        ["process", "--no-analyze"],
        ["status"],
    ):
        result = runner.invoke(app, arguments)
        assert result.exit_code == 0, result.output
    assert "SUCCESS" in result.output
    summary = json.loads((tmp_path / "demo" / "gold" / "summary.json").read_text())
    assert summary["orders"] == 7
    assert summary["revenue"] == 113.2


def test_cli_reset_requires_confirmation_and_protects_workspace(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RETAILPULSE_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["reset"])
    assert result.exit_code != 0
    assert tmp_path.exists()
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["reset", "--yes"])
    assert result.exit_code != 0
    assert tmp_path.exists()


def test_cli_failure_publishes_failed_run_metrics(tmp_path, monkeypatch):
    monkeypatch.setenv("RETAILPULSE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KAFKA_ENABLED", "false")
    assert runner.invoke(app, ["produce", "--scenario", "malformed", "--count", "4"]).exit_code == 0

    def unavailable(*args):
        raise OSError("Quarantine unavailable")

    monkeypatch.setattr(LocalMedallionPipeline, "_quarantine", unavailable)
    assert runner.invoke(app, ["process"]).exit_code != 0
    snapshot = json.loads((tmp_path / "metrics" / "latest.json").read_text())
    assert snapshot["run"]["status"] == "FAILED"
    assert any(alert["metric"] == "pipeline_failure" for alert in snapshot["alerts"])
    assert (
        "retailpulse_pipeline_failed 1" in (tmp_path / "metrics" / "retailpulse.prom").read_text()
    )
