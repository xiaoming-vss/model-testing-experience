"""Resource budgets for user-supplied asset imports."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ImportLimits:
    max_bytes: int = 8 * 1024 * 1024
    max_items: int = 10000
    max_field_chars: int = 262144
    max_depth: int = 32
    max_nodes: int = 200000
    max_concurrent: int = 2

    def __post_init__(self) -> None:
        for name, maximum in (
            ("max_bytes", 64 * 1024 * 1024),
            ("max_items", 100000),
            ("max_field_chars", 4 * 1024 * 1024),
            ("max_depth", 64),
            ("max_nodes", 2000000),
            ("max_concurrent", 16),
        ):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"asset_import.{name} must be between 1 and {maximum}")
