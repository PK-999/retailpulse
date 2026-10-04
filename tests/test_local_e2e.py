import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.run_local_e2e import main


def test_e2e_command_rejects_existing_directory(tmp_path, monkeypatch):
    sentinel = tmp_path / "keep.txt"
    sentinel.write_text("Existing user data")
    monkeypatch.setattr(sys, "argv", ["run_local_e2e.py", "--work-dir", str(tmp_path)])
    with pytest.raises(FileExistsError):
        main()
    assert sentinel.read_text() == "Existing user data"


def test_complete_attended_demo_reconciles_all_classifications_and_gold(tmp_path):
    output = tmp_path / "proof.json"
    result = subprocess.run(
        [sys.executable, "scripts/run_local_e2e.py", "--output", str(output)],
        cwd=Path(__file__).resolve().parents[1],
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
