import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from retailpulse.storage import connect
from scripts.run_local_e2e import main


def test_e2e_command_rejects_existing_directory(tmp_path, monkeypatch, capsys):
    sentinel = tmp_path / "keep.txt"
    sentinel.write_text("Existing user data")
    monkeypatch.setattr(sys, "argv", ["run_local_e2e.py", "--work-dir", str(tmp_path)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert "exists" in capsys.readouterr().err
    assert sentinel.read_text() == "Existing user data"


def test_e2e_help_does_not_generate_or_modify_data(tmp_path):
    result = subprocess.run(
        [sys.executable, "scripts/run_local_e2e.py", "--help", "--work-dir", str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "--work-dir" in result.stdout
    assert list(tmp_path.iterdir()) == []


def test_complete_attended_demo_reconciles_all_classifications_and_gold(tmp_path):
    output = tmp_path / "proof.json"
    demo = tmp_path / "demo"
    user_data = tmp_path / "existing-data"
    user_data.mkdir()
    sentinel = user_data / "keep.txt"
    sentinel.write_text("Existing user data")
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_local_e2e.py",
            "--work-dir",
            str(demo),
            "--output",
            str(output),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env={
            **os.environ,
            "RETAILPULSE_DATA_DIR": str(user_data),
            "KAFKA_ENABLED": "true",
            "KAFKA_BOOTSTRAP_SERVERS": "localhost:1",
        },
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    proof = json.loads(output.read_text())
    assert proof["counts"] == {"bronze_events": 295, "silver_events": 266, "quarantine": 10}
    assert proof["incident"]["source"] == "rules"
    assert "duplicate_rate" in proof["batches"][1]["alert_metrics"]
    assert all(
        proof["dbt"][run]["nodes_passed"] == 37 for run in ("clean", "incremental", "full_refresh")
    )
    assert proof["dbt"]["unchanged_rerun"] and proof["dbt"]["full_refresh_equivalent"]
    assert proof["gold"] == {"items": 18, "orders": 10, "units": 57, "revenue": "268.55"}
    with connect(demo / "retailpulse.db") as connection:
        orders = connection.execute(
            "SELECT COUNT(*), SUM(units), SUM(order_total) FROM fact_orders"
        ).fetchone()
    assert tuple(orders[:2]) == (10, 57)
    assert orders[2] == pytest.approx(268.55)
    summary = json.loads((demo / "gold" / "summary.json").read_text())
    assert summary["orders"] == 10
    assert summary["revenue"] == pytest.approx(268.55)
    assert sentinel.read_text() == "Existing user data"
    assert list(user_data.iterdir()) == [sentinel]
