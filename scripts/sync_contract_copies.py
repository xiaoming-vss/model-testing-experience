"""Copy canonical contract files to their independent application copies, or check drift."""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path(__file__).with_name("contract-copies.json")


def expected_bytes(group: dict, target: dict) -> bytes:
    content = (ROOT / group["canonical"]).read_bytes()
    for old, new in target.get("replace", []):
        content = content.replace(old.encode(), new.encode())
    return content


def targets(group: dict):
    for target in group["targets"]:
        yield target if isinstance(target, dict) else {"path": target}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    groups = json.loads(MANIFEST.read_text(encoding="utf-8"))["groups"]
    drift = []
    for group in groups:
        source = ROOT / group["canonical"]
        if not source.is_file():
            raise SystemExit(f"Missing canonical contract: {group['canonical']}")
        for target in targets(group):
            destination = ROOT / target["path"]
            content = expected_bytes(group, target)
            if args.check:
                if not destination.is_file() or destination.read_bytes() != content:
                    drift.append(target["path"])
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
        if not args.check:
            for directory in group.get("ensure_init", []):
                (ROOT / directory / "__init__.py").touch()
    if drift:
        raise SystemExit("Contract drift: " + ", ".join(drift))
    print(f"{len(groups)} contract groups are synchronized.")


if __name__ == "__main__":
    main()
