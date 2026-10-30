"""Bounded, serializable spreadsheet contracts. No database or global batch state."""

from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = "ktel-import-v1"


@dataclass(frozen=True)
class ImportLimits:
    max_upload_bytes: int = 5 * 1024 * 1024
    max_expanded_bytes: int = 25 * 1024 * 1024
    max_members: int = 128
    max_sheets: int = 8
    max_rows: int = 5000
    max_cells: int = 100000
    max_columns: int = 32
    max_cell_chars: int = 512
    max_issues: int = 200
    max_styles: int = 1024

    def __post_init__(self):
        if any(value <= 0 for value in self.__dict__.values()):
            raise ValueError("Import limits must be positive")


class ImportRejected(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ImportIssue:
    code: str
    message: str
    sheet: str
    row: int | None = None
    column: str | None = None
    field: str | None = None
    cell: str | None = None


@dataclass(frozen=True)
class ParsedRow:
    entity: str
    sheet: str
    row: int
    raw: dict[str, Any]
    values: dict[str, Any]
    columns: dict[str, str]
    cells: dict[str, str]
    issues: tuple[ImportIssue, ...] = ()
    cell_types: dict[str, str] = field(default_factory=dict)

    @property
    def is_valid(self):
        return not self.issues


@dataclass(frozen=True)
class ParsedWorkbook:
    schema_version: str
    filename: str
    file_format: str
    locale: str
    checksum: str
    rows: tuple[ParsedRow, ...]
    issues: tuple[ImportIssue, ...]
    source_locale: str = "en"

    @property
    def is_valid(self):
        return not self.issues


@dataclass(frozen=True)
class ReferenceCatalog:
    driver_refs: frozenset[str] = field(default_factory=frozenset)
    vehicle_refs: frozenset[str] = field(default_factory=frozenset)
    station_refs: frozenset[str] = field(default_factory=frozenset)
    bus_types: frozenset[str] = field(default_factory=frozenset)
    trip_refs: frozenset[str] = field(default_factory=frozenset)


def reject_import(code, en, el, locale):
    raise ImportRejected(code, el if locale == "el" else en)
