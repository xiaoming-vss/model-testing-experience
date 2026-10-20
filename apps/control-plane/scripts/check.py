"""Run the control-plane quality gates using the active locked development environment."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
        commands.append(["pytest", *(args.tests or ["tests"]), "-q", "-rs"])
    for command in commands:
        print("Running:", " ".join(command), flush=True)
        result = subprocess.run([sys.executable, "-m", *command], cwd=PROJECT_ROOT, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
