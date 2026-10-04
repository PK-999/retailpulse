"""Exercise monitoring verification against hand-checked Azure response fixtures."""

from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FACTORY = (
    "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-fixture"
    "/providers/Microsoft.DataFactory/factories/adf-fixture"
)
STORAGE = FACTORY.split("/providers/")[0] + "/providers/Microsoft.Storage/storageAccounts/stfixture"
RULE = FACTORY.split("/providers/")[0] + "/providers/Microsoft.Insights/metricAlerts/alert-fixture"
GROUP = FACTORY.split("/providers/")[0] + "/providers/Microsoft.Insights/actionGroups/ag-fixture"


def inventory() -> dict:
    return {
        "factory": {
            "id": FACTORY,
            "name": "adf-fixture",
            "properties": {
                "provisioningState": "Succeeded",
            },
        },
        "metric_definitions": {
            "value": [
                {
                    "name": {"value": "PipelineFailedRuns"},
                    "primaryAggregationType": "Total",
                    "metricAvailabilities": [{"timeGrain": "PT1M", "retention": "P93D"}],
                }
            ]
        },
        "alert_rules": {
            "value": [
                {
                    "id": RULE,
                    "name": "alert-fixture",
                    "properties": {
                        "enabled": True,
                        "severity": 2,
                        "autoMitigate": True,
                        "scopes": [FACTORY],
                        "evaluationFrequency": "PT5M",
                        "windowSize": "PT15M",
                        "criteria": {
                            "allOf": [
                                {
                                    "metricNamespace": "Microsoft.DataFactory/factories",
                                    "metricName": "PipelineFailedRuns",
                                    "timeAggregation": "Total",
                                    "operator": "GreaterThan",
                                    "threshold": 0,
                                    "dimensions": [],
                                }
                            ]
                        },
                        "actions": [],
                    },
                }
            ]
        },
        "action_groups": {"value": []},
        "diagnostic_settings": {"value": []},
        "alert_instances": {"value": []},
    }


def verify(tmp_path: Path, payload: dict, *flags: str) -> tuple[int, dict, str]:
    fixture = tmp_path / "inventory.json"
    fixture.write_text(json.dumps(payload))
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/verify_cloud_monitoring.py"),
            "--fixture",
            str(fixture),
            "--factory-name",
            "adf-fixture",
            "--alert-name",
            "alert-fixture",
            "--storage-account-name",
            "stfixture",
            *flags,
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.stdout.strip(), result.stderr
    return result.returncode, json.loads(result.stdout), result.stdout


def test_valid_rule_is_verified_without_claiming_notification_delivery(tmp_path) -> None:
    code, report, _ = verify(tmp_path, inventory())
    assert code == 0
    assert report["source"] == "offline_fixture"
    assert report["definition_verified"] is True
    assert report["rule"]["status"] == "verified"
    assert report["notifications"] == {
        "configuration_status": "not_configured",
        "email_receiver_count": 0,
        "delivery_status": "unverified",
    }
    assert report["alert_state"]["observed_count"] == 0
    assert report["end_to_end_test"] == "unverified"


@pytest.mark.parametrize(
    "field,value",
    [
        ("enabled", False),
        ("scopes", [STORAGE]),
        ("windowSize", "PT1H"),
    ],
)
def test_rule_drift_fails_verification(tmp_path, field, value) -> None:
    payload = inventory()
    payload["alert_rules"]["value"][0]["properties"][field] = value
    code, report, _ = verify(tmp_path, payload)
    assert code == 1
    assert report["definition_verified"] is False
    assert field in report["rule"]["issues"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("threshold", 1),
        ("timeAggregation", "Average"),
        ("dimensions", [{"name": "Name", "operator": "Include", "values": ["*"]}]),
    ],
)
def test_metric_condition_drift_fails_verification(tmp_path, field, value) -> None:
    payload = inventory()
    payload["alert_rules"]["value"][0]["properties"]["criteria"]["allOf"][0][field] = value
    code, report, _ = verify(tmp_path, payload)
    assert code == 1
    assert field in report["rule"]["issues"]


def test_missing_rule_is_preflight_ready_but_not_deployed(tmp_path) -> None:
    payload = inventory()
    payload["alert_rules"] = {"value": []}
    code, report, _ = verify(tmp_path, payload, "--preflight")
    assert code == 0
    assert report["preflight_ready"] is True
    assert report["definition_verified"] is False
    assert report["rule"]["status"] == "missing"
    code, report, _ = verify(tmp_path, payload)
    assert code == 1
    assert report["rule"]["status"] == "missing"


def test_disabled_factory_blocks_preflight_even_when_definition_matches(tmp_path) -> None:
    payload = inventory()
    payload["factory"]["properties"]["provisioningState"] = "Disabled"
    code, report, _ = verify(tmp_path, payload, "--preflight")
    assert code == 1
    assert report["preflight_ready"] is False
    assert report["target"]["provisioning_state"] == "Disabled"


def test_metric_must_support_total_aggregation(tmp_path) -> None:
    payload = inventory()
    payload["metric_definitions"]["value"][0]["primaryAggregationType"] = "Average"
    code, report, _ = verify(tmp_path, payload, "--preflight")
    assert code == 1
    assert report["preflight_ready"] is False


def test_email_configuration_and_fired_state_do_not_prove_delivery(tmp_path) -> None:
    payload = inventory()
    payload["alert_rules"]["value"][0]["properties"]["actions"] = [{"actionGroupId": GROUP}]
    payload["action_groups"] = {
        "value": [
            {
                "id": GROUP,
                "properties": {
                    "enabled": True,
                    "emailReceivers": [
                        {
                            "name": "operator",
                            "emailAddress": "operator@example.invalid",
                            "useCommonAlertSchema": True,
                            "status": "Enabled",
                        }
                    ],
                },
            }
        ]
    }
    payload["alert_instances"] = {
        "value": [
            {
                "properties": {
                    "essentials": {
                        "targetResource": FACTORY,
                        "alertRule": "alert-fixture",
                        "monitorCondition": "Fired",
                        "alertState": "New",
                        "startDateTime": "2026-10-04T12:00:00Z",
                    }
                }
            }
        ]
    }
    code, report, output = verify(tmp_path, payload, "--require-notifications")
    assert code == 0
    assert report["notifications"] == {
        "configuration_status": "verified",
        "email_receiver_count": 1,
        "delivery_status": "unverified",
    }
    assert report["alert_state"]["fired"] == 1
    assert report["end_to_end_test"] == "unverified"
    assert "operator@example.invalid" not in output


def test_unrelated_alerts_do_not_count_as_firing_evidence(tmp_path) -> None:
    payload = inventory()
    unrelated = {
        "properties": {
            "essentials": {
                "targetResource": STORAGE,
                "alertRule": "alert-fixture",
                "monitorCondition": "Fired",
            }
        }
    }
    wrong_rule = deepcopy(unrelated)
    wrong_rule["properties"]["essentials"].update(targetResource=FACTORY, alertRule="other")
    payload["alert_instances"] = {"value": [unrelated, wrong_rule], "nextLink": "https://unused"}
    code, report, _ = verify(tmp_path, payload)
    assert code == 0
    assert report["alert_state"]["observed_count"] == 0
    assert report["alert_state"]["inventory_complete"] is False


def test_optional_archival_requires_correct_destination_and_all_run_logs(tmp_path) -> None:
    payload = inventory()
    payload["diagnostic_settings"] = {
        "value": [
            {
                "name": "archive",
                "properties": {
                    "storageAccountId": STORAGE,
                    "logs": [
                        {"category": category, "enabled": True}
                        for category in ["PipelineRuns", "ActivityRuns", "TriggerRuns"]
                    ],
                },
            }
        ]
    }
    code, report, _ = verify(tmp_path, payload, "--expect-diagnostics")
    assert code == 0
    assert report["diagnostics"]["status"] == "verified"
    assert report["diagnostics"]["archive_delivery_status"] == "unverified"
    payload["diagnostic_settings"]["value"][0]["properties"]["logs"].pop()
    code, report, _ = verify(tmp_path, payload, "--expect-diagnostics")
    assert code == 1
    assert report["diagnostics"]["status"] == "invalid"


def test_opted_in_notifications_require_an_action_group(tmp_path) -> None:
    code, report, _ = verify(tmp_path, inventory(), "--require-notifications")
    assert code == 1
    assert report["notifications"]["configuration_status"] == "not_configured"
