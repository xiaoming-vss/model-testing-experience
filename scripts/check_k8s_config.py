#!/usr/bin/env python3
"""Check key Helm values against config/platform.toml without third-party deps.

The default run compares the in-repo chart defaults with the committed
platform example (template check). Deployment checks pass real values:

    python3 scripts/check_k8s_config.py \
        --platform-config config/platform.toml \
        --values-dir .runtime/k8s

Key fields are listed in docs/deployment-k8s.md. Secrets are never printed;
output only names the field and whether it is empty, a placeholder or differs.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import runpy
import sys
import tomllib
from typing import Any
from urllib.parse import parse_qsl, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLATFORM_CONFIG = ROOT / "config" / "platform.example.toml"
CHART_VALUES = ROOT / "deploy" / "helm" / "charts"
SERVICES = ("control-plane", "ai-worker", "api-ui-worker", "integration-worker")
PLACEHOLDERS = {
    "",
    "GENERATE",
    "CHANGE-ME",
    "CHANGE_ME",
    "CHANGEME",
    "PLACEHOLDER",
}
# The control plane refuses to start with these; the rules are read from its source so the
# check cannot accept a password the service rejects (this script runs on a bare Python 3.11).
_SECRET_RULES = runpy.run_path(
    str(ROOT / "apps/control-plane/src/testing_agent/core/secrets.py")
)
password_is_insecure = _SECRET_RULES["password_is_insecure"]
MIN_PASSWORD_LENGTH = _SECRET_RULES["MIN_PASSWORD_LENGTH"]
ALLOWED_AGENT_BACKENDS = {"nanobot", "pi"}


class ConfigError(ValueError):
    """A values or platform file cannot be read."""


# ---------------------------------------------------------------------------
# Minimal YAML subset loader
#
# Helm values in this repository use mappings, block sequences, flow empty
# collections and scalar values. Keeping this loader local avoids adding a
# PyYAML dependency to a repository whose root scripts are stdlib-only. It is
# intentionally not a general YAML implementation; unsupported constructs fail
# with a file and line number instead of being misread.
# ---------------------------------------------------------------------------


def _strip_comment(raw: str) -> str:
    quote: str | None = None
    index = 0
    while index < len(raw):
        char = raw[index]
        if quote == '"':
            if char == "\\":
                index += 2
                continue
            if char == '"':
                quote = None
        elif quote == "'":
            if char == "'" and index + 1 < len(raw) and raw[index + 1] == "'":
                index += 2
                continue
            if char == "'":
                quote = None
        elif char in {'"', "'"}:
            quote = char
        elif char == "#" and (index == 0 or raw[index - 1].isspace()):
            return raw[:index].rstrip()
        index += 1
    return raw.rstrip()


def _split_mapping(text: str) -> tuple[str, str] | None:
    """Split ``key: value`` at a colon outside quotes and flow collections."""
    quote: str | None = None
    depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if quote == '"':
            if char == "\\":
                index += 2
                continue
            if char == '"':
                quote = None
        elif quote == "'":
            if char == "'" and index + 1 < len(text) and text[index + 1] == "'":
                index += 2
                continue
            if char == "'":
                quote = None
        elif char in {'"', "'"}:
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif (
            char == ":"
            and depth == 0
            and (index + 1 == len(text) or text[index + 1].isspace())
        ):
            return text[:index].strip(), text[index + 1 :].strip()
        index += 1
    return None


def _split_flow(text: str) -> list[str]:
    parts: list[str] = []
    quote: str | None = None
    depth = 0
    start = 0
    index = 0
    while index < len(text):
        char = text[index]
        if quote == '"':
            if char == "\\":
                index += 2
                continue
            if char == '"':
                quote = None
        elif quote == "'":
            if char == "'" and index + 1 < len(text) and text[index + 1] == "'":
                index += 2
                continue
            if char == "'":
                quote = None
        elif char in {'"', "'"}:
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
        index += 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+)(?:[eE][+-]?\d+)?$")


def _parse_scalar(text: str) -> Any:
    text = text.strip()
    if text == "":
        return None
    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        try:
            import json

            return json.loads(text)
        except ValueError as exc:
            raise ConfigError(f"invalid quoted scalar {text!r}") from exc
    if text.startswith("'") and text.endswith("'") and len(text) >= 2:
        return text[1:-1].replace("''", "'")
    if text == "[]":
        return []
    if text == "{}":
        return {}
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        return [_parse_scalar(part) for part in _split_flow(inner)] if inner else []
    if text.startswith("{") and text.endswith("}"):
        inner = text[1:-1].strip()
        result: dict[str, Any] = {}
        if inner:
            for part in _split_flow(inner):
                pair = _split_mapping(part)
                if pair is None:
                    raise ConfigError(f"invalid flow mapping entry {part!r}")
                key, value = pair
                result[str(_parse_scalar(key))] = _parse_scalar(value)
        return result
    lowered = text.lower()
    if lowered in {"null", "~"}:
        return None
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if _INT_RE.match(text):
        return int(text)
    if _FLOAT_RE.match(text):
        return float(text)
    return text


def _parse_block(
    lines: list[tuple[int, str, int]], index: int, indent: int, source: Path
) -> tuple[Any, int]:
    if index >= len(lines):
        return None, index
    content = lines[index][1]
    if content == "-" or content.startswith("- "):
        return _parse_sequence(lines, index, indent, source)
    return _parse_mapping(lines, index, indent, source)


def _parse_mapping(
    lines: list[tuple[int, str, int]], index: int, indent: int, source: Path
) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        current_indent, content, lineno = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            raise ConfigError(f"{source}:{lineno}: unexpected indentation")
        if content == "-" or content.startswith("- "):
            raise ConfigError(f"{source}:{lineno}: sequence item in mapping")
        pair = _split_mapping(content)
        if pair is None:
            raise ConfigError(f"{source}:{lineno}: expected 'key: value'")
        key, rest = pair
        key_value = _parse_scalar(key)
        if not isinstance(key_value, str) or not key_value:
            raise ConfigError(f"{source}:{lineno}: unsupported mapping key {key!r}")
        index += 1
        if rest == "":
            if index < len(lines) and lines[index][0] > indent:
                value, index = _parse_block(
                    lines, index, lines[index][0], source
                )
            elif index < len(lines) and lines[index][0] == indent and (
                lines[index][1] == "-" or lines[index][1].startswith("- ")
            ):
                # YAML allows a block sequence at the same indentation as its key.
                value, index = _parse_sequence(lines, index, indent, source)
            else:
                value = None
        elif rest.startswith(("|", ">")):
            block, index = _parse_block_scalar(lines, index, indent)
            value = block
        else:
            value = _parse_scalar(rest)
        result[key_value] = value
    return result, index


def _parse_block_scalar(
    lines: list[tuple[int, str, int]], index: int, parent_indent: int
) -> tuple[str, int]:
    parts: list[str] = []
    while index < len(lines) and lines[index][0] > parent_indent:
        parts.append(lines[index][1])
        index += 1
    return "\n".join(parts) + ("\n" if parts else ""), index


def _parse_sequence(
    lines: list[tuple[int, str, int]], index: int, indent: int, source: Path
) -> tuple[list[Any], int]:
    items: list[Any] = []
    while index < len(lines):
        current_indent, content, lineno = lines[index]
        if current_indent != indent or not (
            content == "-" or content.startswith("- ")
        ):
            break
        rest = content[1:].strip()
        index += 1
        if rest == "":
            if index < len(lines) and lines[index][0] > indent:
                item, index = _parse_block(lines, index, lines[index][0], source)
            else:
                item = None
        else:
            pair = _split_mapping(rest)
            if pair is None:
                item = _parse_scalar(rest)
            else:
                key, value_text = pair
                item = {}
                if value_text == "":
                    if index < len(lines) and lines[index][0] > indent:
                        value, index = _parse_block(
                            lines, index, lines[index][0], source
                        )
                    else:
                        value = None
                elif value_text.startswith(("|", ">")):
                    value, index = _parse_block_scalar(lines, index, indent)
                else:
                    value = _parse_scalar(value_text)
                item[str(_parse_scalar(key))] = value
                if index < len(lines) and lines[index][0] > indent:
                    more, index = _parse_block(
                        lines, index, lines[index][0], source
                    )
                    if not isinstance(more, dict):
                        raise ConfigError(
                            f"{source}:{lineno}: sequence mapping expected"
                        )
                    item.update(more)
        items.append(item)
    return items, index


def load_yaml(path: Path) -> Any:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    lines: list[tuple[int, str, int]] = []
    for lineno, raw_line in enumerate(raw.splitlines(), start=1):
        leading = raw_line[: len(raw_line) - len(raw_line.lstrip())]
        if "\t" in leading:
            raise ConfigError(f"{path}:{lineno}: tab indentation is not supported")
        stripped = _strip_comment(raw_line)
        if not stripped.strip() or stripped.strip() in {"---", "..."}:
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        lines.append((indent, stripped[indent:], lineno))
    if not lines:
        return {}
    value, index = _parse_block(lines, 0, lines[0][0], path)
    if index != len(lines):
        raise ConfigError(f"{path}:{lines[index][2]}: trailing content")
    return value


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            merged[key] = deep_merge(base.get(key), value)
        return merged
    return override


def lookup(data: Any, dotted: str, default: Any = None) -> Any:
    current = data
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def _state(value: Any) -> str:
    if value is None:
        return "missing"
    if isinstance(value, str):
        if not value.strip():
            return "empty"
        if value.strip().upper() in PLACEHOLDERS:
            return "placeholder"
    return "set"


def _configured(value: Any) -> bool:
    return _state(value) == "set"


def _normalize_bool(value: Any) -> bool:
    return bool(value) if value is not None else False


def _normalize_dsn(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    raw = value.strip()
    for prefix in ("mysql://", "mysql+pymysql://"):
        if raw.startswith(prefix):
            raw = "mysql+asyncmy://" + raw[len(prefix) :]
    parts = urlsplit(raw)
    if not parts.scheme:
        return raw
    query = tuple(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return (
        parts.scheme,
        parts.username,
        parts.password,
        parts.hostname,
        parts.port,
        parts.path,
        query,
    )


@dataclass
class Target:
    service: str
    path: str
    value: Any

    @property
    def label(self) -> str:
        return f"{self.service} {self.path}"


class Checker:
    def __init__(
        self,
        platform: dict[str, Any],
        values: dict[str, dict[str, Any]],
        *,
        strict: bool,
    ) -> None:
        self.platform = platform
        self.values = values
        self.strict = strict
        self.failures: list[str] = []
        self.warnings: list[str] = []

    def _targets(
        self, pairs: list[tuple[str, str]], normalize=None
    ) -> list[Target]:
        result = []
        for service, path in pairs:
            value = lookup(self.values.get(service, {}), path)
            if normalize is not None:
                value = normalize(value)
            result.append(Target(service, path, value))
        return result

    def _fail(self, message: str) -> None:
        self.failures.append(message)

    def _warn(self, message: str) -> None:
        self.warnings.append(message)

    def _mismatch(
        self, label: str, platform_path: str, target: Target, reason: str
    ) -> None:
        if self.strict:
            self._fail(f"{label}: {target.label} {reason} {platform_path}")
        else:
            self._warn(
                f"{label}: {target.label} {reason} {platform_path} (template mode)"
            )

    def compare_series(
        self,
        label: str,
        platform_path: str,
        pairs: list[tuple[str, str]],
        *,
        normalize=None,
        display_values: bool = False,
    ) -> None:
        platform_value = lookup(self.platform, platform_path)
        targets = self._targets(pairs, normalize)
        if _configured(platform_value):
            expected = normalize(platform_value) if normalize else platform_value
            for target in targets:
                if not _configured(target.value):
                    self._mismatch(
                        label,
                        platform_path,
                        target,
                        f"is {_state(target.value)} while the platform value is set;",
                    )
                elif target.value != expected:
                    if display_values:
                        self._fail(
                            f"{label}: {target.label}={target.value!r} differs from "
                            f"{platform_path}={platform_value!r}"
                        )
                    else:
                        self._fail(
                            f"{label}: {target.label} differs from {platform_path}"
                        )
            return

        configured_targets = [item for item in targets if _configured(item.value)]
        if not configured_targets:
            return
        if self.strict:
            names = ", ".join(item.label for item in configured_targets)
            self._fail(
                f"{label}: {names} is set but {platform_path} is "
                f"{_state(platform_value)}; configure the platform source first"
            )
        values = {item.value for item in configured_targets}
        if len(values) > 1:
            names = ", ".join(item.label for item in configured_targets)
            self._fail(
                f"{label}: {names} disagree while {platform_path} is unconfigured"
            )
            return
        empty_targets = [item for item in targets if not _configured(item.value)]
        if self.strict and empty_targets:
            names = ", ".join(item.label for item in empty_targets)
            self._fail(
                f"{label}: {names} is {_state(empty_targets[0].value)} while "
                f"{configured_targets[0].label} is set; {platform_path} is unconfigured"
            )

    def check_worker_tokens(self) -> None:
        self.compare_series(
            "Worker token",
            "shared.worker_token",
            [
                ("control-plane", "config.security.worker.key"),
                ("ai-worker", "config.platform.worker_token"),
                ("api-ui-worker", "config.control_plane.worker_token"),
            ],
        )
        self.compare_series(
            "Integration worker token",
            "shared.integration_worker_token",
            [
                ("control-plane", "config.security.integration_worker.key"),
                ("integration-worker", "config.control_plane.worker_token"),
            ],
        )
        self.compare_series(
            "JWT key",
            "shared.jwt_key",
            [("control-plane", "config.security.jwt.key")],
        )
        self.compare_series(
            "Integration key",
            "shared.integration_key",
            [("control-plane", "config.security.integration.key")],
        )

    def check_super_admin(self) -> None:
        for field in ("username", "email"):
            self.compare_series(
                f"Super admin {field}",
                f"control_plane.security.super_admin.{field}",
                [("control-plane", f"config.security.super_admin.{field}")],
            )
        platform_password = lookup(
            self.platform, "control_plane.security.super_admin.initial_password"
        )
        values_password = lookup(
            self.values.get("control-plane", {}),
            "config.security.super_admin.initial_password",
        )
        for name, value in (
            ("platform", platform_password),
            ("control-plane values", values_password),
        ):
            # The service refuses to seed an admin without it: an empty value is not "unset".
            problem = self._password_problem(value)
            if problem is not None:
                message = f"Super admin initial_password: {name} {problem}"
                if self.strict:
                    self._fail(message)
                else:
                    self._warn(f"{message} (template mode)")

    @staticmethod
    def _password_problem(value: Any) -> str | None:
        if value is None:
            return "is missing"
        if not isinstance(value, str):
            return "is not a string"
        if not value.strip():
            return "is empty"
        if value.strip().upper() in PLACEHOLDERS:
            return "uses a placeholder value"
        if password_is_insecure(value):
            return (
                f"is a committed example value or shorter than {MIN_PASSWORD_LENGTH} characters"
            )
        return None

    def check_integration_execution(self) -> None:
        platform_enabled = _normalize_bool(
            lookup(self.platform, "control_plane.integration_execution.enabled")
        )
        values_enabled = _normalize_bool(
            lookup(
                self.values.get("control-plane", {}),
                "config.integration_execution.enabled",
            )
        )
        if platform_enabled != values_enabled:
            self._fail(
                "Integration execution: control-plane "
                f"config.integration_execution.enabled={values_enabled!r} differs from "
                f"control_plane.integration_execution.enabled={platform_enabled!r}"
            )
            return
        if platform_enabled:
            self.compare_series(
                "Integration runtime generation",
                "shared.integration_runtime_generation",
                [
                    (
                        "control-plane",
                        "config.integration_execution.runtime_generation",
                    )
                ],
            )

    def check_database(self) -> None:
        platform_url = lookup(self.platform, "database.url")
        target = self._targets([("control-plane", "config.data.db.user.dsn")])[0]
        if _configured(platform_url):
            if not _configured(target.value):
                self._mismatch(
                    "Database",
                    "database.url",
                    target,
                    f"is {_state(target.value)} while the platform DSN is set;",
                )
            elif _normalize_dsn(target.value) != _normalize_dsn(platform_url):
                self._fail(
                    "Database: control-plane config.data.db.user.dsn differs from "
                    "database.url (scheme normalized, credentials not printed)"
                )
            return
        if self.strict and not _configured(target.value):
            self._fail(
                "Database: control-plane config.data.db.user.dsn is "
                f"{_state(target.value)}; K8s requires an external MySQL DSN"
            )

    def check_redis(self) -> None:
        platform_url = lookup(self.platform, "redis.url")
        pairs = [
            ("control-plane", "config.test_run_notifications.redis_url"),
            ("api-ui-worker", "config.notifications.redis_url"),
        ]
        if _configured(platform_url):
            self.compare_series("Redis", "redis.url", pairs)
            return
        targets = self._targets(pairs)
        configured = [item for item in targets if _configured(item.value)]
        if len(configured) == 2 and configured[0].value != configured[1].value:
            self._fail(
                "Redis: control-plane config.test_run_notifications.redis_url differs "
                "from api-ui-worker config.notifications.redis_url while redis.url is "
                "unconfigured"
            )

    def check_s3(self) -> None:
        platform_s3 = lookup(self.platform, "control_plane.storage.s3", {}) or {}
        values_s3 = (
            lookup(self.values.get("control-plane", {}), "config.storage.s3", {})
            or {}
        )
        platform_enabled = _normalize_bool(platform_s3.get("enabled"))
        values_enabled = _normalize_bool(values_s3.get("enabled"))
        if platform_enabled != values_enabled:
            self._fail(
                "S3: control-plane config.storage.s3.enabled="
                f"{values_enabled!r} differs from "
                f"control_plane.storage.s3.enabled={platform_enabled!r}"
            )
            return
        if not platform_enabled:
            return
        for field in (
            "endpoint",
            "region",
            "bucket",
            "access_key",
            "secret_key",
            "prefix",
        ):
            self.compare_series(
                f"S3 {field}",
                f"control_plane.storage.s3.{field}",
                [("control-plane", f"config.storage.s3.{field}")],
            )

    def check_agent_backend(self) -> None:
        platform_backend = lookup(self.platform, "ai_worker.agent.backend")
        target = self._targets([("ai-worker", "config.agent.backend")])[0]
        if platform_backend not in ALLOWED_AGENT_BACKENDS:
            self._fail(
                "AI backend: ai_worker.agent.backend is "
                f"{_state(platform_backend)} or unsupported; expected one of "
                f"{sorted(ALLOWED_AGENT_BACKENDS)}"
            )
        if target.value not in ALLOWED_AGENT_BACKENDS:
            self._fail(
                "AI backend: ai-worker config.agent.backend is "
                f"{_state(target.value)} or unsupported; expected one of "
                f"{sorted(ALLOWED_AGENT_BACKENDS)}"
            )
            return
        if target.value != platform_backend:
            self._fail(
                "AI backend: ai-worker config.agent.backend="
                f"{target.value!r} differs from ai_worker.agent.backend="
                f"{platform_backend!r}"
            )

    def run(self) -> None:
        self.check_worker_tokens()
        self.check_super_admin()
        self.check_integration_execution()
        self.check_database()
        self.check_redis()
        self.check_s3()
        self.check_agent_backend()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def load_platform(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            return tomllib.load(stream)
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc


def load_values(values_dir: Path | None) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for service in SERVICES:
        path = CHART_VALUES / service / "values.yaml"
        defaults = load_yaml(path)
        if not isinstance(defaults, dict):
            raise ConfigError(f"{path}: top-level mapping expected")
        if values_dir is not None:
            override_path = values_dir / f"{service}-values.yaml"
            if override_path.exists():
                override = load_yaml(override_path)
                if not isinstance(override, dict):
                    raise ConfigError(f"{override_path}: top-level mapping expected")
                defaults = deep_merge(defaults, override)
        values[service] = defaults
    return values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Check key Helm values against config/platform.toml. "
            "Secrets are compared but never printed."
        )
    )
    parser.add_argument(
        "--platform-config",
        type=Path,
        default=DEFAULT_PLATFORM_CONFIG,
        help=(
            "platform TOML to read (default: config/platform.example.toml; "
            "use config/platform.toml for a real deployment)"
        ),
    )
    parser.add_argument(
        "--values-dir",
        type=Path,
        default=None,
        help=(
            "directory with <service>-values.yaml overrides; enables strict mode. "
            "Each file is merged over the chart defaults."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        platform = load_platform(args.platform_config)
        if args.values_dir is not None:
            if not args.values_dir.is_dir():
                raise ConfigError(f"values directory not found: {args.values_dir}")
            override_files = list(args.values_dir.glob("*-values.yaml"))
            if not override_files:
                raise ConfigError(
                    f"no *-values.yaml files in values directory: {args.values_dir}"
                )
        values = load_values(args.values_dir)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    checker = Checker(platform, values, strict=args.values_dir is not None)
    checker.run()

    source = (
        f"{args.values_dir} merged over chart defaults"
        if args.values_dir is not None
        else "chart defaults"
    )
    print(f"K8s config check: platform={args.platform_config}, values={source}")
    for warning in checker.warnings:
        print(f"WARN {warning}")
    for failure in checker.failures:
        print(f"FAIL {failure}")
    print(
        f"{len(checker.failures)} failure(s), {len(checker.warnings)} warning(s)"
    )
    return 1 if checker.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
