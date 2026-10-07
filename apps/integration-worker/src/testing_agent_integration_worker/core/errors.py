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
