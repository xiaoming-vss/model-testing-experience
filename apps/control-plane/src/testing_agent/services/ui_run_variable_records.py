"""Persist UI run variable usage and write-back records without leaking secrets."""

from __future__ import annotations

import json
from typing import Any

from testing_agent.core.config import get_settings
from testing_agent.services.execution_secrets import private_payload
from testing_agent.services.integration_credentials import IntegrationCredentialCipher

MASK = "********"


def record_step_variable_usage(run: Any, step_results: Any) -> None:
    """Append `usedVariables` reported by a worker to the run record."""
    entries = _usage_entries(step_results)
    if not entries:
        return
    public = list(getattr(run, "used_variables_json", None) or [])
    private = private_payload(run)
    private_used = list(private.get("usedVariables") or [])
    secrets = set(private.get("secrets") or [])

    for entry in entries:
        public_entry = {"name": entry["name"], "orderNo": entry["orderNo"]}
        if entry["secret"]:
            public_entry["value"] = MASK
            public_entry["masked"] = True
            private_used.append(entry)
            if entry["value"]:
                secrets.add(entry["value"])
        else:
            public_entry["value"] = entry["value"]
        public.append(public_entry)

    run.used_variables_json = public
    _save_private(run, private, used=private_used, secrets=secrets)


def record_variable_writes(run: Any, records: list[dict[str, Any]]) -> None:
    """Append extraction write-backs, masking values that belong to secret variables."""
    public = list(getattr(run, "variable_writes_json", None) or [])
    private = private_payload(run)
    private_writes = list(private.get("variableWrites") or [])
    secrets = set(private.get("secrets") or [])

    for record in records:
        secret = bool(record.get("secret"))
        public.append(
            {
                "name": record["name"],
                "previousValue": MASK if secret else record.get("previousValue"),
                "value": MASK if secret else record.get("value"),
                "orderNo": record.get("orderNo"),
                "created": bool(record.get("created")),
            }
        )
        private_writes.append(record)
        if secret:
            for value in (record.get("previousValue"), record.get("value")):
                if value:
                    secrets.add(str(value))

    run.variable_writes_json = public
    _save_private(run, private, writes=private_writes, secrets=secrets)


def _save_private(
    run: Any,
    private: dict[str, Any],
    *,
    used: list[dict[str, Any]] | None = None,
    writes: list[dict[str, Any]] | None = None,
    secrets: set[str] | None = None,
) -> None:
    payload = dict(private)
    if used is not None:
        payload["usedVariables"] = used
    if writes is not None:
        payload["variableWrites"] = writes
    if secrets is not None:
        payload["secrets"] = sorted(secrets)
    if not payload:
        return
    run.private_payload = IntegrationCredentialCipher(get_settings().integration_key).encrypt(
        json.dumps(payload)
    )


def _usage_entries(step_results: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not isinstance(step_results, list):
        return entries
    for step in step_results:
        if not isinstance(step, dict):
            continue
        order_no = step.get("orderNo")
        for item in step.get("usedVariables") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            entries.append(
                {
                    "name": name,
                    "value": "" if item.get("value") is None else str(item.get("value")),
                    "orderNo": order_no,
                    "secret": bool(item.get("secret")),
                }
            )
    return entries
