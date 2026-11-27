"""Output collection for command-line tests; no collected cases."""


class LinePrinter:
    """``print`` stand-in that keeps each line it is given."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, value: str) -> None:
        self.lines.append(value)
