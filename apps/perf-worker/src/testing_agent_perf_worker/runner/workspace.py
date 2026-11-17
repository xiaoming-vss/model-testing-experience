"""Per-run workspace management."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from ..core.errors import ExecutionError
from ..core.io import mkdir_secure, write_secure_text

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class Workspace:
    root: Path
    plan_path: Path
    script_path: Path
    log_path: Path
    summary_path: Path
    result_path: Path
    data_dir: Path
    inputs_dir: Path

    @classmethod
    def create(cls, workspace_root: Path, run_id: str) -> Workspace:
        mkdir_secure(workspace_root)
        root = workspace_root / _safe_name(run_id)
        if root.exists():
            raise ExecutionError(f"运行工作目录已存在: {root}")
        mkdir_secure(root)
        inputs_dir = root / "inputs"
        mkdir_secure(inputs_dir)
        return cls(
            root=root,
            plan_path=root / "plan.json",
            script_path=root / "main.js",
            log_path=root / "k6.log",
            summary_path=root / "summary.json",
            result_path=root / "result.json",
            data_dir=root / "data",
            inputs_dir=inputs_dir,
        )

    def write_result(self, text: str) -> None:
        write_secure_text(self.result_path, text, overwrite=True)

    def read_log_tail(self, max_bytes: int = 8192) -> str:
        try:
            data = self.log_path.read_bytes()
        except OSError:
            return ""
        return data[-max_bytes:].decode("utf-8", errors="replace")

    def secure_summary(self) -> None:
        """k6 writes summary.json itself; tighten it to the workspace policy."""

        try:
            self.summary_path.chmod(0o600)
        except FileNotFoundError:
            return

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def _safe_name(run_id: str) -> str:
    name = _SAFE_NAME_RE.sub("_", run_id).strip("._")
    return name[:120] or "run"
