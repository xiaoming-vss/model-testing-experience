from __future__ import annotations

import argparse
import asyncio
import os
from copy import deepcopy

import uvicorn
from uvicorn.config import LOGGING_CONFIG

from testing_agent.core.config import load_settings
from testing_agent.core.http_diagnostics import LOGGER_NAME
from testing_agent.services.super_admin import seed_super_admin


def main() -> None:
    parser = argparse.ArgumentParser(description="MTX Python control plane")
    parser.add_argument("--config", "-c", default="config/local.toml", help="config file path")
    args = parser.parse_args()
    os.environ["APP_CONF"] = args.config
    settings = load_settings(args.config)
    asyncio.run(seed_super_admin(settings))
    log_config = deepcopy(LOGGING_CONFIG)
    log_config["loggers"][LOGGER_NAME] = {
        "handlers": ["default"],
        "level": "INFO",
        "propagate": False,
    }
    uvicorn.run(
        "testing_agent.app:create_app",
        factory=True,
        host=settings.http_host,
        port=settings.http_port,
        reload=settings.env == "local",
        access_log=False,
        log_config=log_config,
    )


if __name__ == "__main__":
    main()
