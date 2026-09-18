from __future__ import annotations

import argparse

import uvicorn

from testing_agent.core.config import load_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="testing-agent Python control plane")
    parser.add_argument("--config", "-c", default="config/local.toml", help="config file path")
    args = parser.parse_args()
    settings = load_settings(args.config)
    uvicorn.run(
        "testing_agent.app:create_app",
        factory=True,
        host=settings.http_host,
        port=settings.http_port,
        reload=settings.env == "local",
    )


if __name__ == "__main__":
    main()
