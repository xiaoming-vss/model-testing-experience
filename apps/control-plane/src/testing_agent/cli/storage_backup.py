"""Coordinated MySQL/S3 backup, verification and isolated restore."""

import argparse
import json
from pathlib import Path

from testing_agent.core.config import load_settings
from testing_agent.services.storage_backup import create_backup, restore_backup, verify_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["backup", "verify", "restore"])
    parser.add_argument("directory", type=Path)
    parser.add_argument(
        "--config", help="Generated service config; credentials never go in a bundle"
    )
    parser.add_argument(
        "--maintenance",
        action="store_true",
        help="Confirm application/worker writers and skill publishers are stopped",
    )
    args = parser.parse_args()
    if args.command != "verify" and not args.maintenance:
        parser.error("backup/restore requires --maintenance; stop writers and publishers first")
    try:
        if args.command == "verify":
            manifest = verify_bundle(args.directory)
            result = {"tables": len(manifest["tables"]), "objects": len(manifest["objects"])}
        else:
            operation = create_backup if args.command == "backup" else restore_backup
            result = operation(load_settings(args.config), args.directory)
    except Exception as exc:
        # Driver exceptions may contain DSNs, SQL values or URLs. Only show the type.
        parser.exit(
            1, f"Storage {args.command} failed ({type(exc).__name__}); target remains offline\n"
        )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
