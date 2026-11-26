"""Run streaming and availability contracts shared by API and UI execution."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

RunKind = Literal["api-case", "api-collection", "ui-case", "ui-suite"]
RunAvailabilityState = Literal["available", "busy", "offline", "unknown"]


class AvailabilityResponse(BaseModel):
    state: RunAvailabilityState

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
