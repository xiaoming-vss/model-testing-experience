"""Worker-specific exception types."""

from __future__ import annotations


class PerfWorkerError(Exception):
    """Base error for expected worker failures."""


class ConfigError(PerfWorkerError):
    """The worker configuration is missing or invalid."""


class SpecError(PerfWorkerError):
    """The run specification is missing or invalid."""


class CompileError(PerfWorkerError):
    """The run specification cannot be compiled into an execution plan."""


class ExecutionError(PerfWorkerError):
    """k6 or the worker could not execute the plan."""


class ControlPlaneError(PerfWorkerError):
    """The control plane rejected or failed a worker protocol request."""

    def __init__(self, message: str, status_code: int = 0) -> None:
        super().__init__(message)
        self.status_code = status_code


class LeaseLostError(ControlPlaneError):
    """The control plane no longer grants this worker the execution lease."""


class DataFileError(PerfWorkerError):
    """A frozen data file could not be downloaded or verified."""
