"""Read a messy process inventory. Every data row is parsed or listed. None are dropped."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import pandas as pd
from openpyxl import load_workbook

from src.units import parse_error_rate, parse_minutes, parse_volume

ALIASES = {
    "process": ["process", "process name", "name", "workflow", "task"],
    "team": ["team", "team / dept", "team/dept", "department", "dept"],
    "volume": ["volume (monthly)", "monthly volume", "monthly_volume", "volume", "vol"],
    "minutes": ["time per item", "minutes per item", "handling time", "minutes", "mins", "time"],
    "error": ["error %", "error rate", "error_rate", "errors", "error"],
    "sources": ["data sources", "source systems", "systems", "sources"],
    "notes": ["notes / comments", "free text", "comments", "description", "notes"],
}


class InventoryError(Exception):
    pass


@dataclass
class ParsedRow:
    source_row: int
    process: str
    team: str
    monthly_volume: object
    minutes_per_item: object
    error_rate: object
    error_missing: bool
    sources: list[str]
    sources_raw: str
    notes: str
    raw: dict


@dataclass
class ExceptionRow:
    source_row: int
    reasons: list[str]
    raw: dict = field(default_factory=dict)


@dataclass
class Inventory:
    parsed: list[ParsedRow]
    exceptions: list[ExceptionRow]
    rows_seen: int
    header_row: int
    sheet: str

    @property
    def accounted(self) -> int:
        return len(self.parsed) + len(self.exceptions)


def _norm_header(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _collapse(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _map_header(cells: list[str]) -> dict[str, int] | None:
    found: dict[str, int] = {}
    for index, cell in enumerate(cells):
        label = _norm_header(cell)
        if not label:
            continue
        for field_name, aliases in ALIASES.items():
            if field_name in found:
                continue
            if label in aliases:
                found[field_name] = index
    needed = {"process", "volume", "minutes"}
    if not needed <= set(found):
        return None
    return found


def _matrix_from_csv(path) -> tuple[list[list[str]], str]:
    raw = path.read_bytes()
    text = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise InventoryError(f"could not read {path}")
    sample = text[:4000]
    sep = ";" if sample.count(";") > sample.count(",") else ","
    frame = pd.read_csv(
        io.StringIO(text),
        header=None,
        dtype=str,
        keep_default_na=False,
        sep=sep,
        engine="python",
        skip_blank_lines=False,
    )
    matrix = frame.fillna("").astype(str).values.tolist()
    return matrix, "csv"


def _matrix_from_xlsx(path) -> tuple[list[list[str]], str]:
    book = load_workbook(path, data_only=True)
    best = None
    for sheet in book.worksheets:
        matrix = []
        for row in sheet.iter_rows(values_only=True):
            matrix.append(["" if cell is None else str(cell) for cell in row])
        header_at = _find_header(matrix)
        if header_at is None:
            continue
        data_rows = max(0, len(matrix) - header_at - 1)
        if best is None or data_rows > best[0]:
            best = (data_rows, matrix, sheet.title, header_at)
    if best is None:
        raise InventoryError(f"no header row found in {path}")
    return best[1], best[2]


def _find_header(matrix: list[list[str]]) -> int | None:
    best_at = None
    best_score = 0
    for index, row in enumerate(matrix[:8]):
        mapped = _map_header([str(cell) for cell in row])
        if not mapped:
            continue
        if len(mapped) > best_score:
            best_score = len(mapped)
            best_at = index
    return best_at


def _cell(row: list[str], mapped: dict[str, int], name: str) -> str:
    index = mapped.get(name)
    if index is None or index >= len(row):
        return ""
    return str(row[index] or "")


def load_inventory(path) -> Inventory:
    path = path if hasattr(path, "suffix") else path
    suffix = str(path).lower()
    if suffix.endswith(".csv"):
        matrix, sheet = _matrix_from_csv(path)
    elif suffix.endswith(".xlsx"):
        matrix, sheet = _matrix_from_xlsx(path)
    else:
        raise InventoryError(f"unsupported inventory file: {path}")
    header_at = _find_header(matrix)
    if header_at is None:
        raise InventoryError(f"no header row found in {path}")
    mapped = _map_header([str(cell) for cell in matrix[header_at]])
    assert mapped is not None
    parsed: list[ParsedRow] = []
    exceptions: list[ExceptionRow] = []
    seen: dict[tuple[str, str], int] = {}
    data = matrix[header_at + 1 :]
    for offset, row in enumerate(data):
        source_row = header_at + 2 + offset  # 1-based spreadsheet row
        cells = [str(cell) if cell is not None else "" for cell in row]
        raw = {
            "process": _cell(cells, mapped, "process"),
            "team": _cell(cells, mapped, "team"),
            "volume": _cell(cells, mapped, "volume"),
            "minutes": _cell(cells, mapped, "minutes"),
            "error": _cell(cells, mapped, "error"),
            "sources": _cell(cells, mapped, "sources"),
            "notes": _cell(cells, mapped, "notes"),
        }
        if all(not str(cell).strip() for cell in cells):
            exceptions.append(ExceptionRow(source_row, ["blank_row"], raw))
            continue
        process = _collapse(raw["process"])
        team = _collapse(raw["team"])
        if not process:
            exceptions.append(ExceptionRow(source_row, ["missing_process"], raw))
            continue
        reasons: list[str] = []
        volume, volume_err = parse_volume(raw["volume"])
        minutes, minutes_err = parse_minutes(raw["minutes"])
        error_rate, error_err = parse_error_rate(raw["error"])
        if volume_err:
            reasons.append("bad_volume" if volume_err == "missing" else volume_err)
        if minutes_err:
            reasons.append("bad_minutes" if minutes_err == "missing" else minutes_err)
        if error_err and error_err != "missing":
            reasons.append(error_err)
        if reasons:
            exceptions.append(ExceptionRow(source_row, reasons, raw))
            continue
        key = (process.lower(), team.lower())
        if key in seen:
            exceptions.append(ExceptionRow(source_row, ["duplicate"], raw))
            continue
        seen[key] = source_row
        sources = [part.strip() for part in raw["sources"].split(",") if part.strip()]
        parsed.append(
            ParsedRow(
                source_row=source_row,
                process=process,
                team=team,
                monthly_volume=volume,
                minutes_per_item=minutes,
                error_rate=error_rate,
                error_missing=error_err == "missing",
                sources=sources,
                sources_raw=raw["sources"].strip(),
                notes=raw["notes"].strip(),
                raw=raw,
            )
        )
    inventory = Inventory(parsed, exceptions, len(data), header_at + 1, sheet)
    if inventory.accounted != inventory.rows_seen:
        raise InventoryError(
            f"row accounting failed: {inventory.accounted} accounted, {inventory.rows_seen} seen"
        )
    return inventory
