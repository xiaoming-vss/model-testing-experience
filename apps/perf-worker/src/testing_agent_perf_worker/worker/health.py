"""Atomic health file used by the container healthcheck."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..core.io import write_secure_text


@dataclass(frozen=True)
class HealthFile:
    path: Path
    max_age_seconds: int

    def progress(self, stage: str) -> None:
        payload = {
            "pid": os.getpid(),
            "stage": stage,
            "progressAt": datetime.now(UTC).isoformat(),
        }
        write_secure_text(
            self.path,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            overwrite=True,
        )

    def healthy(self) -> bool:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(raw, dict):
            return False
        pid = raw.get("pid")
        if not isinstance(pid, int) or pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            pass

        progress_at = raw.get("progressAt")
        if not isinstance(progress_at, str):
            return False
        try:
            timestamp = datetime.fromisoformat(progress_at)
        except ValueError:
            return False
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        age = (datetime.now(UTC) - timestamp).total_seconds()
        return 0 <= age <= self.max_age_seconds
