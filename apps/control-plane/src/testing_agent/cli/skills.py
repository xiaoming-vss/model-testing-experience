"""Upload/overwrite system skills: python -m testing_agent.cli.skills SOURCE_DIRECTORY."""

import argparse
import asyncio
import json
from pathlib import Path

from testing_agent.core.config import get_settings
from testing_agent.db.session import AsyncSessionLocal
from testing_agent.services.builtin_skills import sync_builtin_skills
from testing_agent.services.skill_storage import migrate_skill_paths
from testing_agent.services.stored_file import StoredFileService


async def run(source, migrate_paths=False):
    settings = get_settings()
    if not settings.s3.enabled:
        raise SystemExit("S3 文件存储未启用")
    async with AsyncSessionLocal() as session:
        files = StoredFileService(session, settings.s3)
        results = (
            await migrate_skill_paths(files)
            if migrate_paths
            else await sync_builtin_skills(files, source)
        )
        for result in results:
            print(json.dumps(result, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, nargs="?")
    parser.add_argument("--migrate-paths", action="store_true")
    args = parser.parse_args()
    if not args.migrate_paths and args.source is None:
        parser.error("source is required unless --migrate-paths is used")
    asyncio.run(run(args.source, args.migrate_paths))


if __name__ == "__main__":
    main()
