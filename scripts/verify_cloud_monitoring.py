#!/usr/bin/env python3
"""Read-only Azure Monitor preflight and definition/state verification.

Every Azure request is a GET. A matching rule, receiver, or Fired alert never
proves delivery; the report deliberately leaves that evidence unverified.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlencode

ROOT = Path(__file__).resolve().parents[1]
METRIC = "PipelineFailedRuns"
LOGS = {"PipelineRuns", "ActivityRuns", "TriggerRuns"}


def collection(payload: dict | list) -> list[dict]:
    if isinstance(payload, list):
        return payload
    return payload.get("value", [])


class AzureReader:
    def __init__(self, timeout: int) -> None:
        self.deadline = time.monotonic() + timeout
        self.env = {**os.environ}
        self.env.setdefault("AZURE_CONFIG_DIR", str(ROOT / ".azure"))

    def read(self, *arguments: str) -> dict | list | str:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("inventory_deadline_exceeded")
        result = subprocess.run(
            ["az", *arguments, "--output", "json", "--only-show-errors"],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=min(15, remaining),
            check=False,
        )
        if result.returncode:
            # Raw CLI stderr can contain private resource IDs. Keep published evidence minimal.
            raise RuntimeError(f"azure_read_failed_exit_{result.returncode}")
        return json.loads(result.stdout)

    def get(self, path: str, version: str, **query: str) -> dict:
        url = (
            "https://management.azure.com"
            + path
            + "?"
            + urlencode(
                {
                    "api-version": version,
                    **query,
                }
            )
        )
        return self.read("rest", "--method", "get", "--url", url)


def azure_inventory(args: argparse.Namespace) -> dict:
    reader = AzureReader(args.timeout_seconds)
    subscription = reader.read("account", "show", "--query", "id")
    group = f"/subscriptions/{subscription}/resourceGroups/{quote(args.resource_group, safe='')}"
    factory = (
        group
        + "/providers/Microsoft.DataFactory/factories/"
        + quote(
            args.factory_name,
            safe="",
        )
    )
    requests = {
        "factory": (factory, "2018-06-01", {}),
        "metric_definitions": (
            factory + "/providers/Microsoft.Insights/metricDefinitions",
            "2018-01-01",
            {},
        ),
        "alert_rules": (group + "/providers/Microsoft.Insights/metricAlerts", "2018-03-01", {}),
        "action_groups": (group + "/providers/Microsoft.Insights/actionGroups", "2023-01-01", {}),
        "diagnostic_settings": (
            factory + "/providers/Microsoft.Insights/diagnosticSettings",
            "2021-05-01-preview",
            {},
        ),
        "alert_instances": (
            group + "/providers/Microsoft.AlertsManagement/alerts",
            "2019-03-01",
            {"targetResource": factory, "timeRange": "1d", "pageCount": "25"},
        ),
    }
    payload = {"inventory_errors": {}}
    for name, (path, version, query) in requests.items():
        try:
            payload[name] = reader.get(path, version, **query)
        except (
            OSError,
            RuntimeError,
            TimeoutError,
            subprocess.TimeoutExpired,
            ValueError,
        ) as error:
            payload[name] = {}
            payload["inventory_errors"][name] = (
                "request_timed_out" if isinstance(error, subprocess.TimeoutExpired) else str(error)
            )
    return payload


def verify_rule(rule: dict | None, factory_id: str) -> dict:
    if rule is None:
        return {"status": "missing", "issues": ["not_deployed"]}
    properties = rule.get("properties", {})
    expected = {
        "enabled": True,
        "severity": 2,
        "autoMitigate": True,
        "evaluationFrequency": "PT5M",
        "windowSize": "PT15M",
    }
    issues = [name for name, value in expected.items() if properties.get(name) != value]
    scopes = [scope.lower() for scope in properties.get("scopes", [])]
    if not factory_id or scopes != [factory_id.lower()]:
        issues.append("scopes")
    criteria = properties.get("criteria", {}).get("allOf", [])
    if len(criteria) != 1:
        issues.append("criteria_count")
    else:
        condition = criteria[0]
        expected_condition = {
            "metricName": METRIC,
            "timeAggregation": "Total",
            "operator": "GreaterThan",
            "threshold": 0,
        }
        issues += [
            name for name, value in expected_condition.items() if condition.get(name) != value
        ]
        if condition.get("metricNamespace", "").lower() != "microsoft.datafactory/factories":
            issues.append("metricNamespace")
        if condition.get("dimensions"):
            issues.append("dimensions")
    return {"status": "invalid" if issues else "verified", "issues": issues}


def verify_notifications(rule: dict | None, groups: list[dict]) -> dict:
    actions = (rule or {}).get("properties", {}).get("actions", [])
    status = "not_configured" if not actions else "verified"
    receivers = 0
    by_id = {group.get("id", "").lower(): group for group in groups}
    for action in actions:
        properties = by_id.get(action.get("actionGroupId", "").lower(), {}).get("properties", {})
        emails = properties.get("emailReceivers", [])
        if properties.get("enabled") is not True or not emails:
            status = "invalid"
        receivers += len(emails)
        if any(
            email.get("useCommonAlertSchema") is not True
            or email.get("status", "Enabled") != "Enabled"
            for email in emails
        ):
            status = "invalid"
    return {
        "configuration_status": status,
        "email_receiver_count": receivers,
        "delivery_status": "unverified",
    }


def verify_diagnostics(
    settings: list[dict], factory_id: str, storage_name: str, expected: bool
) -> dict:
    storage_id = (
        factory_id.split("/providers/")[0]
        + "/providers/Microsoft.Storage/storageAccounts/"
        + storage_name
    )
    candidates = [
        setting.get("properties", {})
        for setting in settings
        if setting.get("properties", {}).get("storageAccountId", "").lower() == storage_id.lower()
    ]
    complete = any(
        {log.get("category") for log in candidate.get("logs", []) if log.get("enabled") is True}
        >= LOGS
        for candidate in candidates
    )
    status = "verified" if complete else "invalid" if candidates else "missing"
    if not expected and not candidates:
        status = "not_requested"
    return {"status": status, "archive_delivery_status": "unverified"}


def evaluate(payload: dict, args: argparse.Namespace, source: str) -> dict:
    factory = payload.get("factory", {})
    factory_id = factory.get("id", "")
    provisioning = factory.get("properties", {}).get("provisioningState", "unknown")
    definition = next(
        (
            metric
            for metric in collection(payload.get("metric_definitions", {}))
            if metric.get("name", {}).get("value") == METRIC
        ),
        {},
    )
    metric_available = definition.get("primaryAggregationType") == "Total" and any(
        grain.get("timeGrain") == "PT1M" for grain in definition.get("metricAvailabilities", [])
    )
    rule = next(
        (
            rule
            for rule in collection(payload.get("alert_rules", {}))
            if rule.get("name") == args.alert_name
        ),
        None,
    )
    rule_report = {"name": args.alert_name, **verify_rule(rule, factory_id)}
    notifications = verify_notifications(rule, collection(payload.get("action_groups", {})))
    diagnostics = verify_diagnostics(
        collection(payload.get("diagnostic_settings", {})),
        factory_id,
        args.storage_account_name,
        args.expect_diagnostics,
    )
    matching_alerts = []
    for alert in collection(payload.get("alert_instances", {})):
        essentials = alert.get("properties", {}).get("essentials", {})
        if (
            factory_id
            and essentials.get("targetResource", "").lower() == factory_id.lower()
            and essentials.get("alertRule") in {args.alert_name, (rule or {}).get("id")}
        ):
            matching_alerts.append(essentials)
    errors = payload.get("inventory_errors", {})
    preflight_ready = bool(factory_id) and provisioning == "Succeeded" and metric_available
    verified = rule_report["status"] == "verified"
    if args.require_notifications:
        verified = verified and notifications["configuration_status"] == "verified"
    if args.expect_diagnostics:
        verified = verified and diagnostics["status"] == "verified"
    alert_payload = payload.get("alert_instances", {})
    complete = not isinstance(alert_payload, dict) or not alert_payload.get("nextLink")
    return {
        "schema_version": 1,
        "source": source,
        "checked_at": datetime.now(UTC).isoformat(),
        "mode": "preflight" if args.preflight else "verify",
        "preflight_ready": preflight_ready,
        "definition_verified": verified and not errors,
        "target": {"factory": args.factory_name, "provisioning_state": provisioning},
        "metric": {"name": METRIC, "total_at_one_minute_available": metric_available},
        "rule": rule_report,
        "notifications": notifications,
        "diagnostics": diagnostics,
        "alert_state": {
            "window": "1d",
            "observed_count": len(matching_alerts),
            "fired": sum(alert.get("monitorCondition") == "Fired" for alert in matching_alerts),
            "resolved": sum(
                alert.get("monitorCondition") == "Resolved" for alert in matching_alerts
            ),
            "inventory_complete": complete and "alert_instances" not in errors,
        },
        "end_to_end_test": "unverified",
        "inventory_errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource-group", default="rg-retailpulse-dev-rp999")
    parser.add_argument("--factory-name", default="adf-retailpulse-dev-rp999")
    parser.add_argument("--storage-account-name", default="stretailpulsedevrp999")
    parser.add_argument("--alert-name")
    parser.add_argument(
        "--fixture", type=Path, help="Captured API-shaped input; never contacts Azure"
    )
    parser.add_argument("--output", type=Path, help="Write the sanitized JSON report to this path")
    parser.add_argument(
        "--preflight", action="store_true", help="Allow a rule that is not deployed yet"
    )
    parser.add_argument("--expect-diagnostics", action="store_true")
    parser.add_argument("--require-notifications", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=60)
    args = parser.parse_args()
    if not 5 <= args.timeout_seconds <= 60:
        parser.error("--timeout-seconds must be between 5 and 60")
    args.alert_name = args.alert_name or (
        "alert-" + args.factory_name.removeprefix("adf-") + "-adf-failed-runs"
    )
    try:
        payload = json.loads(args.fixture.read_text()) if args.fixture else azure_inventory(args)
        report = evaluate(payload, args, "offline_fixture" if args.fixture else "azure_read_only")
    except (OSError, ValueError, RuntimeError, TimeoutError, subprocess.TimeoutExpired) as error:
        report = {
            "schema_version": 1,
            "source": "offline_fixture" if args.fixture else "azure_read_only",
            "preflight_ready": False,
            "definition_verified": False,
            "end_to_end_test": "unverified",
            "inventory_errors": {"inventory": str(error)},
        }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    if report["inventory_errors"]:
        return 2
    return (
        0 if report["preflight_ready"] and (args.preflight or report["definition_verified"]) else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
