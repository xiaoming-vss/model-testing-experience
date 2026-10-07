import argparse
import asyncio
import logging
import sys

from pydantic import ValidationError

from testing_agent_integration_worker.app import run_worker
from testing_agent_integration_worker.core.config import load_settings
from testing_agent_integration_worker.core.logging import configure_logging
from testing_agent_integration_worker.worker.lifecycle import healthy


def main() -> None:
    parser = argparse.ArgumentParser(description="Independent integration execution worker")
    parser.add_argument("--config", "-c")
    parser.add_argument("--healthcheck", action="store_true")
    args = parser.parse_args()
    try:
        settings = load_settings(args.config)
    except ValidationError as error:
        fields = [".".join(str(part) for part in item["loc"]) for item in error.errors()]
        print("Invalid integration configuration fields: " + ", ".join(fields), file=sys.stderr)
        raise SystemExit(2) from None
    except (OSError, ValueError):
        print("Cannot read a valid integration configuration file", file=sys.stderr)
        raise SystemExit(2) from None
    if args.healthcheck:
        raise SystemExit(
            0 if healthy(settings.worker.health_file, settings.worker.health_max_age_seconds) else 1
        )
    configure_logging()
    try:
        asyncio.run(run_worker(settings))
    except Exception as error:
        logging.error("Integration Worker stopped (%s)", type(error).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
