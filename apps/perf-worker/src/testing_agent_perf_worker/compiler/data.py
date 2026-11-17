"""Dataset loading and conversion.

CSV is parsed in Python so the fixed k6 template only consumes JSON. Runtime
data files are written with owner-only permissions and are never part of the
uploaded script/spec artifact.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..contracts.spec import DataSpec, DataStrategy, ExhaustedPolicy
from ..core.errors import CompileError
from ..core.io import write_secure_text

MAX_DATA_ROWS = 200_000


@dataclass(frozen=True)
class Dataset:
    name: str
    rows: list[dict[str, str]]
    columns: tuple[str, ...]
    strategy: DataStrategy
    on_exhausted: ExhaustedPolicy


def load_datasets(specs: list[DataSpec], base_dir: Path, max_file_mb: int) -> list[Dataset]:
    datasets: list[Dataset] = []
    for spec in specs:
        if spec.rows is not None:
            rows = _normalize_rows(spec.rows, spec.name)
            columns = tuple(rows[0].keys())
        else:
            source_path = _resolve_source(base_dir, spec.source)
            format_name = spec.format or source_path.suffix.lower().lstrip(".")
            if format_name == "csv":
                rows, columns = _read_csv(source_path, max_file_mb, spec.name)
            elif format_name == "json":
                rows, columns = _read_json(source_path, max_file_mb, spec.name)
            else:
                raise CompileError(f"数据 {spec.name} 的格式无法识别: {source_path.name}")

        if not rows:
            raise CompileError(f"数据 {spec.name} 没有数据行")
        if len(rows) > MAX_DATA_ROWS:
            raise CompileError(f"数据 {spec.name} 超过 {MAX_DATA_ROWS} 行上限")

        datasets.append(
            Dataset(
                name=spec.name,
                rows=rows,
                columns=columns,
                strategy=spec.strategy,
                on_exhausted=spec.on_exhausted,
            )
        )
    return datasets


def write_datasets(datasets: list[Dataset], data_dir: Path) -> None:
    for dataset in datasets:
        content = json.dumps(dataset.rows, ensure_ascii=False, separators=(",", ":"))
        write_secure_text(data_dir / f"{dataset.name}.json", content)


def _resolve_source(base_dir: Path, source: str) -> Path:
    source_path = Path(source)
    if source_path.is_absolute():
        raise CompileError("数据文件必须位于运行规格目录内")
    resolved_base = base_dir.resolve()
    resolved = (resolved_base / source_path).resolve()
    if not resolved.is_relative_to(resolved_base):
        raise CompileError("数据文件必须位于运行规格目录内")
    if not resolved.is_file():
        raise CompileError(f"数据文件不存在: {source}")
    return resolved


def _read_csv(
    path: Path, max_file_mb: int, name: str
) -> tuple[list[dict[str, str]], tuple[str, ...]]:
    _check_size(path, max_file_mb, name)
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fieldnames = reader.fieldnames or []
            if not fieldnames:
                raise CompileError(f"CSV 数据 {name} 缺少表头")
            if len(fieldnames) != len(set(fieldnames)):
                raise CompileError(f"CSV 数据 {name} 存在重复表头")
            rows: list[dict[str, str]] = []
            for raw_row in reader:
                if None in raw_row:
                    raise CompileError(f"CSV 数据 {name} 的某行字段数超过表头")
                row: dict[str, str] = {}
                for column in fieldnames:
                    value = raw_row.get(column)
                    row[column] = "" if value is None else value
                rows.append(row)
                if len(rows) > MAX_DATA_ROWS:
                    raise CompileError(f"数据 {name} 超过 {MAX_DATA_ROWS} 行上限")
    except (OSError, UnicodeError) as exc:
        raise CompileError(f"无法读取 CSV 数据 {name}: {path}") from exc
    except csv.Error as exc:
        raise CompileError(f"CSV 数据 {name} 解析失败: {exc}") from None
    return rows, tuple(fieldnames)


def _read_json(
    path: Path, max_file_mb: int, name: str
) -> tuple[list[dict[str, str]], tuple[str, ...]]:
    _check_size(path, max_file_mb, name)
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise CompileError(f"无法读取 JSON 数据 {name}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CompileError(f"JSON 数据 {name} 解析失败: {exc}") from None
    if not isinstance(raw, list):
        raise CompileError(f"JSON 数据 {name} 顶层必须是数组")
    rows = _normalize_rows(raw, name)
    return rows, tuple(rows[0].keys())


def _normalize_rows(rows: list[Any], name: str) -> list[dict[str, str]]:
    if not rows:
        raise CompileError(f"数据 {name} 没有数据行")
    normalized: list[dict[str, str]] = []
    columns: list[str] | None = None
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise CompileError(f"数据 {name} 第 {index} 行不是对象")
        row_columns = list(row.keys())
        if columns is None:
            columns = row_columns
        elif set(row_columns) != set(columns):
            raise CompileError(f"数据 {name} 第 {index} 行的字段与首行不一致")
        normalized_row: dict[str, str] = {}
        for column in columns:
            value = row[column]
            if isinstance(value, bool):
                normalized_row[str(column)] = "true" if value else "false"
            elif isinstance(value, (int, float)):
                normalized_row[str(column)] = str(value)
            elif isinstance(value, str):
                normalized_row[str(column)] = value
            else:
                raise CompileError(f"数据 {name} 第 {index} 行的 {column} 必须是标量字符串或数字")
        normalized.append(normalized_row)
        if len(normalized) > MAX_DATA_ROWS:
            raise CompileError(f"数据 {name} 超过 {MAX_DATA_ROWS} 行上限")
    return normalized


def _check_size(path: Path, max_file_mb: int, name: str) -> None:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise CompileError(f"无法读取数据文件 {name}: {path}") from exc
    if size > max_file_mb * 1024 * 1024:
        raise CompileError(f"数据 {name} 超过 {max_file_mb} MiB 上限")
