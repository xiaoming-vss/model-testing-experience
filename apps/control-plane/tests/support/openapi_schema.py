"""Shared cached OpenAPI schema; generation is expensive and read-only."""

from functools import lru_cache

from testing_agent.app import create_app


@lru_cache(maxsize=1)
def openapi_schema() -> dict:
    """Return the OpenAPI document for the default application."""
    return create_app().openapi()
