"""Revalidate durable source cells without reopening a file or trusting a browser plan."""

from collections import OrderedDict
from datetime import date, datetime, time
import re
from openpyxl.utils.cell import coordinate_to_tuple
from app.domain.imports.parsers import _parse_sheets
from app.domain.imports.template_schema import SHEETS


def native_source_value(value, data_type, kind):
    """Restore JSON-safe exceptional/native cells before applying the same parser rules."""
    if not isinstance(value, str):
        return value
    if data_type == "n":
        if re.fullmatch(r"[+-]?\d+", value):
            return int(value)
        try:
            return float(value)
        except ValueError:
            return value
    if data_type == "d":
        try:
            if kind == "clock":
                return time.fromisoformat(value)
            return (
                datetime.fromisoformat(value)
                if "T" in value
                else date.fromisoformat(value)
            )
        except ValueError:
            return value
    return value


def validate_saved_rows(batch, rows, limits):
    groups = OrderedDict()
    for row in rows:
        groups.setdefault((row.sheet, row.entity), []).append(row)
    sources = []
    ordered = []
    for (sheet, entity), members in groups.items():
        columns = {column.key: column for column in SHEETS[entity][2]}
        headings = {}
        fields = {}
        for row in members:
            for field, label in row.source_columns.items():
                coordinate = row.source_cells.get(field)
                if coordinate and field in columns:
                    index = coordinate_to_tuple(coordinate)[1] - 1
                    headings[index] = label
                    fields[field] = index
            for item in row.raw.get("_unmapped_columns", []):
                index = coordinate_to_tuple(item["cell"])[1] - 1
                headings[index] = item.get("column", "")
        for issue in batch.file_issues:
            if (
                issue.get("sheet") == sheet
                and issue.get("row") == 1
                and issue.get("code") in ("unknown_column", "duplicate_column")
                and issue.get("cell")
            ):
                headings[coordinate_to_tuple(issue["cell"])[1] - 1] = issue.get(
                    "column", ""
                )
        for row in members:
            for field in row.raw:
                if field in columns and field not in fields:
                    index = next(
                        index
                        for index in range(limits.max_columns)
                        if index not in headings
                    )
                    headings[index] = columns[field].label(batch.source_locale)
                    fields[field] = index
        width = max(headings, default=-1) + 1
        header = [(headings.get(index, ""), "s") for index in range(width)]
        content = [(1, header)]
        for row in members:
            cells = [(None, "n") for _ in range(width)]
            for field, index in fields.items():
                raw = row.raw.get(field)
                data_type = row.cell_types.get(field, "s")
                cells[index] = (
                    native_source_value(raw, data_type, columns[field].kind),
                    data_type,
                )
            for item in row.raw.get("_unmapped_columns", []):
                index = coordinate_to_tuple(item["cell"])[1] - 1
                if index >= len(cells):
                    cells.extend([(None, "n")] * (index + 1 - len(cells)))
                dtype = item.get("data_type", "s")
                cells[index] = (
                    native_source_value(item["value"], dtype, "text"),
                    dtype,
                )
            content.append((row.row_number, cells))
            ordered.append(row)
        sources.append((sheet, entity, iter(content)))
    result = _parse_sheets(
        sources,
        "staged." + batch.file_format,
        batch.file_format,
        batch.locale,
        b"staged-validation",
        limits,
        batch.source_locale,
    )
    if len(result.rows) != len(ordered):
        raise ValueError("Persisted import row count changed during validation")
    return list(zip(ordered, result.rows)), result.issues
