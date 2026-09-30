"""python -m testing_agent.cli.storage repair-names [--apply] | cleanup."""

import argparse
import asyncio
import json

from testing_agent.core.config import get_settings
from testing_agent.db.session import AsyncSessionLocal
from testing_agent.services.stored_file import StoredFileService


async def run(command, apply):
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        files = StoredFileService(session, settings.s3)
        if command == "repair-names":
            from testing_agent.services.file_naming import repair_file_names

            results = await repair_file_names(files, apply=apply)
            for result in results:
                print(json.dumps(result))
            if any(result["status"] == "failed" for result in results):
                raise SystemExit(1)
            return
        if command == "cleanup":
            print(json.dumps(await files.cleanup()))
            return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["repair-names", "cleanup"])
    parser.add_argument(
        "--apply", action="store_true", help="Apply filename repair; default is read-only"
    )
    args = parser.parse_args()
    asyncio.run(run(args.command, args.apply))


if __name__ == "__main__":
    main()
