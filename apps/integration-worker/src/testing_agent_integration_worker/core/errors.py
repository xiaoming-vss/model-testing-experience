import traceback


class ControlPlaneError(Exception):
    def __init__(self, status: int = 0):
        super().__init__(f"Control-plane request failed ({status or 'transport'})")
        self.status = status


class LeaseLost(Exception):
    pass


class PreflightError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class WriteUncertain(Exception):
    pass


def safe_traceback(exc: BaseException) -> str:
    """Frame locations only; exception messages and source text are excluded."""
    frames = traceback.StackSummary.extract(
        traceback.walk_tb(exc.__traceback__),
        lookup_lines=False,
    )
    return "\n".join(
        f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}' for frame in frames
    )
