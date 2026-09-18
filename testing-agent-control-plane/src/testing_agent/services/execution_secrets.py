"""Encrypted executor inputs and scrubbed project-visible API execution history."""

import json
from urllib.parse import quote, quote_plus

from testing_agent.core.config import get_settings
from testing_agent.core.errors import ErrForbidden
from testing_agent.services.integration_credentials import IntegrationCredentialCipher

FIELDS = (
    "request_snapshot_json",
    "response_snapshot_json",
    "runtime_vars_json",
    "extract_results_json",
    "assert_results_json",
    "error_message",
)


def redact(value, secrets):
    if isinstance(value, str):
        for secret in sorted(
            {
                v
                for s in secrets
                if s
                for v in (s, quote(s, safe=""), quote_plus(s), json.dumps(s)[1:-1])
            },
            key=len,
            reverse=True,
        ):
            value = value.replace(secret, "********")
        return value
    if isinstance(value, dict):
        return {redact(k, secrets): redact(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, secrets) for v in value]
    return value


def private_payload(run):
    encrypted = getattr(run, "private_payload", None)
    if not encrypted:
        return {}
    try:
        return json.loads(
            IntegrationCredentialCipher(get_settings().integration_key).decrypt(encrypted)
        )
    except (ValueError, TypeError) as exc:
        raise ErrForbidden from exc


def protect_run(run, secrets):
    previous = private_payload(run)
    secrets = list(set([*previous.get("secrets", []), *secrets]))
    if not secrets:
        return
    fields = {field: getattr(run, field) for field in FIELDS if hasattr(run, field)}
    # Only executor request inputs are retained; response and diagnostic secrets are scrubbed.
    payload = {
        "secrets": secrets,
        "request_snapshot_json": previous.get(
            "request_snapshot_json", fields.get("request_snapshot_json")
        ),
        "runtime_vars_json": previous.get("runtime_vars_json", fields.get("runtime_vars_json")),
    }
    run.private_payload = IntegrationCredentialCipher(get_settings().integration_key).encrypt(
        json.dumps(payload)
    )
    for field, value in fields.items():
        setattr(run, field, redact(value, secrets))
