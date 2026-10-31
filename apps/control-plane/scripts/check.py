"""Run the control-plane quality gates using the active locked development environment."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# These opt-in suites share one live database or bucket, so they must stay serial.
LIVE_TEST_ENVIRONMENTS = ("CONTROL_PLANE_TEST_DATABASE_URL", "CONTROL_PLANE_STORAGE_LIVE")


def pytest_command(tests: list[str] | None) -> list[str]:
    """Parallelize the full suite unless a live resource forces single-process execution."""
    command = ["pytest", *(tests or ["tests"]), "-q", "-rs"]
    if tests is None and not any(os.environ.get(name) for name in LIVE_TEST_ENVIRONMENTS):
        command[1:1] = ["-n", "auto", "--dist", "loadfile"]
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--static-only", action="store_true")
    group.add_argument("--tests", nargs="+", metavar="PATH", help="Run selected tests after checks")
    args = parser.parse_args()
    commands = [
        ["ruff", "check", "src", "tests", "scripts"],
        ["ruff", "format", "--check", "src", "tests", "scripts"],
        ["mypy", "--python-version", "3.12", "--check-untyped-defs", "src/testing_agent"],
    ]
    if not args.static_only:
        commands.append(pytest_command(args.tests))
    for command in commands:
        print("Running:", " ".join(command), flush=True)
        result = subprocess.run([sys.executable, "-m", *command], cwd=PROJECT_ROOT, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
