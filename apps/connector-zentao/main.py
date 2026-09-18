import uvicorn

from app.config import get_settings


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.app_env == "local",
        log_config=None,
    )


if __name__ == "__main__":
    run()
