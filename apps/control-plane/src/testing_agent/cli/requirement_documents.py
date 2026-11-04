"""python -m testing_agent.cli.requirement_documents migrate-text [--apply]."""

import argparse
import asyncio
import json

from testing_agent.core.config import get_settings
from testing_agent.db.session import AsyncSessionLocal
from testing_agent.services.requirement_document_migration import migrate_text_requirements
from testing_agent.services.stored_file import StoredFileService


async def run(apply: bool) -> int:
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        files = StoredFileService(session, settings.s3)
        results = await migrate_text_requirements(files, apply=apply)
        for result in results:
            print(json.dumps(result, ensure_ascii=False))
        return 1 if any(result["status"] == "failed" for result in results) else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["migrate-text"])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="执行转换并写入对象存储/数据库；默认只输出计划",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.apply)))


if __name__ == "__main__":
    main()
