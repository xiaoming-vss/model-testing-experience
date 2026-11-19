"""Local outbox for task results whose completion callback failed.

The control plane only accepts completion while the attempt still holds a valid
lease. This outbox therefore keeps results only for diagnostics and for retries
inside that lease window; an entry whose lease has expired is never delivered.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from testing_agent_ai_worker.models.execution import TaskResult

DEFAULT_RETENTION_SECONDS = 7 * 24 * 60 * 60
OUTBOX_VERSION = 1


@dataclass(frozen=True, slots=True)
class OutboxEntry:
    path: Path
    result: TaskResult
    lease_expires_at: datetime


@dataclass(frozen=True, slots=True)
class OutboxDrain:
    delivered: int = 0
    failed: int = 0
    expired: int = 0
    discarded: int = 0


class ResultOutbox:
    """Persist failed completion results without exposing their contents."""

    def __init__(
        self,
        directory: str | Path,
        *,
        retention_seconds: float = DEFAULT_RETENTION_SECONDS,
    ) -> None:
        self.directory = Path(directory)
        self.retention_seconds = max(0.0, retention_seconds)

    def save(self, result: TaskResult, *, lease_expires_at: datetime) -> Path:
        """Write one result atomically with owner-only permissions."""

        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = self.directory / self._filename(result)
        payload = {
            "version": OUTBOX_VERSION,
            "leaseExpiresAt": _as_utc(lease_expires_at).isoformat(),
            "result": result.model_dump(mode="json"),
        }
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=".result-",
            suffix=".tmp",
            dir=self.directory,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, target)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return target

    def drain(
        self,
        submit: Callable[[TaskResult], None],
        *,
        now: datetime | None = None,
    ) -> OutboxDrain:
        """Retry deliverable entries and retain expired or failed ones."""

        current = _as_utc(now or datetime.now(UTC))
        entries, discarded = self._read_entries()
        delivered = failed = expired = 0
        for entry in entries:
            if entry.lease_expires_at <= current:
                # The control plane retires attempts after lease expiry; a late
                # completion must not reopen a run or race a new attempt.
                expired += 1
                continue
            try:
                submit(entry.result)
            except Exception:
                failed += 1
                continue
            try:
                entry.path.unlink()
            except OSError:
                failed += 1
                continue
            delivered += 1
        discarded += self._prune(current)
        return OutboxDrain(
            delivered=delivered,
            failed=failed,
            expired=expired,
            discarded=discarded,
        )

    def _read_entries(self) -> tuple[list[OutboxEntry], int]:
        try:
            paths = sorted(self.directory.glob("*.json"))
        except OSError:
            return [], 0
        entries: list[OutboxEntry] = []
        discarded = 0
        for path in paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict) or payload.get("version") != OUTBOX_VERSION:
                    raise ValueError("unsupported outbox entry")
                deadline = _parse_deadline(payload.get("leaseExpiresAt"))
                result = TaskResult.model_validate(payload.get("result"))
            except (OSError, ValueError, TypeError):
                path.unlink(missing_ok=True)
                discarded += 1
                continue
            entries.append(OutboxEntry(path=path, result=result, lease_expires_at=deadline))
        return entries, discarded

    def _prune(self, now: datetime) -> int:
        cutoff = now.timestamp() - self.retention_seconds
        discarded = 0
        paths = [*self.directory.glob("*.json"), *self.directory.glob("*.tmp")]
        for path in paths:
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    discarded += 1
            except OSError:
                continue
        return discarded

    @staticmethod
    def _filename(result: TaskResult) -> str:
        identity = f"{result.task_id}\0{result.attempt_id}".encode()
        digest = hashlib.sha256(identity).hexdigest()[:12]
        task = re.sub(r"[^A-Za-z0-9_.-]+", "_", result.task_id).strip("._-")[:64] or "task"
        return f"{task}.{digest}.json"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_deadline(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("lease expiry is missing")
    return _as_utc(datetime.fromisoformat(value))


__all__ = ["OutboxDrain", "OutboxEntry", "ResultOutbox"]
