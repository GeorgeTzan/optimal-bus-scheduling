"""Bounded literal-only XLSX/UTF-8 CSV parsing, independent of persistence."""

import csv
import hashlib
import io
import re
import zipfile
from dataclasses import replace
from datetime import date, datetime, time
from pathlib import PurePosixPath
from defusedxml import ElementTree as SafeXML
from defusedxml.common import DefusedXmlException
from openpyxl import load_workbook
from openpyxl.utils.cell import get_column_letter
from pydantic import ValidationError, create_model
from app.domain.imports.contracts import (
    SCHEMA_VERSION,
    ImportLimits,
    ImportRejected,
    ImportIssue,
    ParsedRow,
    ParsedWorkbook,
)
from app.domain.imports.template_schema import SHEETS, title
from app.domain.imports.contracts import reject_import as reject
from app.domain.imports.xlsx_safety import inspect_package as _archive
from app.domain.imports.cell_values import (
    CellValueError,
    parse_cell_value as _value,
    serialize_source_value,
)
from app.domain.resources.schemas import DriverCreate, VehicleCreate, StationCreate, Code
from app.domain.timetables.calendar import CalendarRule
from app.domain.timetables.operational_schemas import TransferCreate

TransferFileFields = create_model(
    "TransferFileFields",
    **{
        key: (TransferCreate.model_fields[key].rebuild_annotation(), default)
        for key, default in (("minutes", ...), ("source_note", None))
    },
)


ConnectionFileFields = create_model("ConnectionFileFields", incoming_ref=(Code, ...), outgoing_ref=(Code, ...))


def _issue(code, sheet, row, column, cell, locale):
    label = column.label(locale)
    messages = {
        "required": (f"Enter {label}.", f"Συμπληρώστε το πεδίο «{label}»."),
        "formula": (
            "Paste the calculated value instead of a formula.",
            "Επικολλήστε την υπολογισμένη τιμή αντί για τύπο.",
        ),
        "text_reference_required": (
            "Use text for this reference, including any leading zeroes.",
            "Χρησιμοποιήστε κείμενο για τον κωδικό, διατηρώντας τα αρχικά μηδενικά.",
        ),
        "ambiguous_date": (
            "This date is ambiguous. Use year-month-day, for example 2026-06-01.",
            "Η ημερομηνία είναι αμφίσημη. Χρησιμοποιήστε έτος-μήνα-ημέρα, π.χ. 2026-06-01.",
        ),
        "invalid_date": (
            "Use year-month-day, for example 2026-06-01.",
            "Χρησιμοποιήστε έτος-μήνα-ημέρα, π.χ. 2026-06-01.",
        ),
        "invalid_time": (
            "Use a local time such as 08:30, without seconds.",
            "Χρησιμοποιήστε τοπική ώρα όπως 08:30, χωρίς δευτερόλεπτα.",
        ),
        "invalid_boolean": ("Choose Yes or No.", "Επιλέξτε Ναι ή Όχι."),
        "invalid_arrival_day": (
            "Choose Same day, Next day or Two days later.",
            "Επιλέξτε Ίδια ημέρα, Επόμενη ημέρα ή Μετά από δύο ημέρες.",
        ),
        "invalid_weekdays": (
            "List days such as Mon Tue Wed, once each.",
            "Συμπληρώστε ημέρες όπως Δευ Τρι Τετ, μία φορά καθεμία.",
        ),
        "invalid_number": (
            "Enter a plain number using the template language’s decimal separator.",
            "Συμπληρώστε έναν απλό αριθμό με το δεκαδικό διαχωριστικό της γλώσσας του προτύπου.",
        ),
    }
    en, el = messages.get(code, (f"Check {label}.", f"Ελέγξτε το πεδίο «{label}»."))
    return ImportIssue(
        code, el if locale == "el" else en, sheet, row, label, column.key, cell
    )


def _domain_issues(entity, values):
    if entity in ("drivers", "vehicles", "stations"):
        model = {
            "drivers": DriverCreate,
            "vehicles": VehicleCreate,
            "stations": StationCreate,
        }[entity]
        model.model_validate(
            {key: value for key, value in values.items() if key in model.model_fields}
        )
    if entity == "timetable":
        CalendarRule.model_validate(
            {
                key: value
                for key, value in values.items()
                if key in CalendarRule.model_fields
            }
        )
        if len(values.get("trip_code", "")) > 64 or any(
            len(values.get(key, "")) > 160 for key in ("origin", "destination")
        ):
            raise CellValueError("invalid_value")
        if values.get("distance_km", 0) < 0 or values.get("distance_km", 0) > 10000:
            raise CellValueError("invalid_number")
    if entity == "connections":
        ConnectionFileFields.model_validate(values)
    if entity == "transfers":
        TransferFileFields.model_validate(values)


def parse_upload(content, filename, entity, locale, *, limits=None):
    limits = limits or ImportLimits()
    if entity not in (*SHEETS, "all") or locale not in ("en", "el"):
        raise ValueError("Choose a supported template and language")
    if not isinstance(content, bytes):
        raise TypeError("Upload content must be bytes")
    if len(content) > limits.max_upload_bytes:
        reject(
            "upload_limit",
            "The file is too large. Split it into smaller files.",
            "Το αρχείο είναι πολύ μεγάλο. Χωρίστε το σε μικρότερα αρχεία.",
            locale,
        )
    filename = PurePosixPath(filename.replace("\\", "/")).name
    suffix = PurePosixPath(filename).suffix.casefold()
    if suffix not in (".xlsx", ".csv"):
        reject(
            "unsupported_format",
            "Upload an XLSX workbook or UTF-8 CSV template.",
            "Εισαγάγετε βιβλίο XLSX ή πρότυπο CSV σε UTF-8.",
            locale,
        )
    if not content:
        reject(
            "empty_file",
            "This file is empty. Use a populated template.",
            "Το αρχείο είναι κενό. Συμπληρώστε ένα πρότυπο.",
            locale,
        )
    sheets = []
    book = None
    source_locale = locale
    if suffix == ".csv":
        if entity == "all":
            reject(
                "unsupported_format",
                "Choose the record type for this CSV file.",
                "Επιλέξτε το είδος εγγραφών του αρχείου CSV.",
                locale,
            )
        try:
            text = content.decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError:
            reject(
                "invalid_encoding",
                "Save the CSV as UTF-8 and upload it again.",
                "Αποθηκεύστε το CSV σε UTF-8 και εισαγάγετέ το ξανά.",
                locale,
            )
        if "\x00" in text or text.startswith("PK\x03\x04"):
            reject(
                "invalid_content",
                "This is not a text CSV file.",
                "Το αρχείο δεν είναι CSV κειμένου.",
                locale,
            )
        candidates = []
        for language in ("en", "el"):
            try:
                first = next(
                    csv.reader(
                        io.StringIO(text, newline=""),
                        delimiter=";" if language == "el" else ",",
                        strict=True,
                    ),
                    [],
                )
            except csv.Error:
                continue
            expected = {column.label(language) for column in SHEETS[entity][2]}
            if any(label.strip() in expected for label in first):
                candidates.append(language)
        if len(candidates) > 1:
            reject(
                "template_language",
                "Use a single supplied CSV language and layout.",
                "Χρησιμοποιήστε μία γλώσσα και διάταξη προτύπου CSV.",
                locale,
            )
        if candidates:
            source_locale = candidates[0]
        try:
            rows = []
            cells = 0
            for index, row in enumerate(
                csv.reader(
                    io.StringIO(text, newline=""),
                    delimiter=";" if source_locale == "el" else ",",
                    strict=True,
                ),
                1,
            ):
                if len(row) > limits.max_columns:
                    reject(
                        "cell_limit",
                        "There are too many columns. Use the supplied template.",
                        "Υπάρχουν υπερβολικά πολλές στήλες. Χρησιμοποιήστε το παρεχόμενο πρότυπο.",
                        locale,
                    )
                cells += len(row)
                if cells > limits.max_cells:
                    reject(
                        "cell_limit",
                        "There are too many cells. Split the file.",
                        "Υπάρχουν υπερβολικά πολλά κελιά. Χωρίστε το αρχείο.",
                        locale,
                    )
                if index > limits.max_rows + 1:
                    reject(
                        "row_limit",
                        "There are too many rows. Split the file.",
                        "Υπάρχουν υπερβολικά πολλές γραμμές. Χωρίστε το αρχείο.",
                        locale,
                    )
                rows.append([(value, "csv") for value in row])
            sheets = [(title(entity, source_locale), entity, enumerate(rows, 1))]
        except csv.Error:
            reject(
                "invalid_content",
                "The CSV could not be read. Save a fresh UTF-8 copy.",
                "Το CSV δεν διαβάζεται. Αποθηκεύστε νέο αντίγραφο UTF-8.",
                locale,
            )
    else:
        _archive(content, limits, locale)
        try:
            book = load_workbook(
                io.BytesIO(content), read_only=True, data_only=False, keep_links=False
            )
            if len(book.worksheets) > limits.max_sheets:
                reject(
                    "sheet_limit",
                    "There are too many sheets. Use a supplied template.",
                    "Υπάρχουν υπερβολικά πολλά φύλλα. Χρησιμοποιήστε το παρεχόμενο πρότυπο.",
                    locale,
                )
            instructions = next(
                (s for s in book if s.title in ("Instructions", "Οδηγίες")), None
            )
            if instructions is None or instructions.cell(2, 2).value != SCHEMA_VERSION:
                reject(
                    "template_version",
                    "Download the current template and paste your values into it.",
                    "Κατεβάστε το τρέχον πρότυπο και επικολλήστε τις τιμές σας.",
                    locale,
                )
            source_locale = instructions.cell(4, 2).value
            if source_locale not in ("en", "el"):
                reject(
                    "template_language",
                    "Download a current template with a supported language.",
                    "Κατεβάστε τρέχον πρότυπο σε υποστηριζόμενη γλώσσα.",
                    locale,
                )
            for sheet in book:
                if sheet is instructions:
                    continue
                key = next(
                    (
                        key
                        for key, definition in SHEETS.items()
                        if sheet.title in definition[:2]
                    ),
                    None,
                )
                sheet.reset_dimensions()
                sheets.append(
                    (
                        sheet.title,
                        key,
                        (
                            (index, [(cell.value, cell.data_type) for cell in cells])
                            for index, cells in enumerate(sheet.iter_rows(), 1)
                        ),
                    )
                )
            return _parse_sheets(
                sheets, filename, "xlsx", locale, content, limits, source_locale
            )
        except ImportRejected:
            raise
        except (
            ValueError,
            KeyError,
            TypeError,
            IndexError,
            zipfile.BadZipFile,
            SafeXML.ParseError,
            DefusedXmlException,
        ):
            reject(
                "invalid_container",
                "This workbook could not be read. Paste values into a fresh template.",
                "Το βιβλίο δεν διαβάζεται. Επικολλήστε τιμές σε νέο πρότυπο.",
                locale,
            )
        finally:
            if book:
                book.close()
    return _parse_sheets(
        sheets, filename, "csv", locale, content, limits, source_locale
    )


def _parse_sheets(
    sheets, filename, file_format, locale, content, limits, source_locale
):
    result = []
    issues = []
    issue_count = 0
    seen = {}

    def collect(new):
        nonlocal issue_count
        issue_count += len(new)
        issues.extend(new[: max(0, limits.max_issues - len(issues))])

    for sheet, entity, source in sheets:
        header = None
        columns = {}
        specs = SHEETS[entity][2] if entity else ()
        for number, cells in source:
            if len(cells) > limits.max_columns:
                reject(
                    "cell_limit",
                    "There are too many columns. Use the supplied template.",
                    "Υπάρχουν υπερβολικά πολλές στήλες. Χρησιμοποιήστε το παρεχόμενο πρότυπο.",
                    locale,
                )
            if any(
                isinstance(value, str) and len(value) > limits.max_cell_chars
                for value, _ in cells
            ):
                reject(
                    "text_limit",
                    "A cell contains too much text. Shorten it.",
                    "Ένα κελί περιέχει υπερβολικά μεγάλο κείμενο. Συντομεύστε το.",
                    locale,
                )
            if not any(value is not None and str(value).strip() for value, _ in cells):
                continue
            if entity is None:
                reject(
                    "unsupported_sheet",
                    "An unrecognized sheet contains data. Use only the supplied sheets.",
                    "Ένα μη αναγνωρισμένο φύλλο περιέχει δεδομένα. Χρησιμοποιήστε μόνο τα παρεχόμενα φύλλα.",
                    locale,
                )
            if header is None:
                if number != 1:
                    reject(
                        "invalid_header",
                        "Keep the column headings on the first row.",
                        "Διατηρήστε τις επικεφαλίδες στην πρώτη γραμμή.",
                        locale,
                    )
                header = cells
                for index, (label, _) in enumerate(header):
                    label = str(label or "").strip()
                    if not label:
                        continue
                    spec = next((s for s in specs if label in (s.en, s.el)), None)
                    if spec is None or spec.key in columns:
                        collect(
                            [
                                ImportIssue(
                                    (
                                        "unknown_column"
                                        if spec is None
                                        else "duplicate_column"
                                    ),
                                    (
                                        "Use the supplied column headings."
                                        if locale == "en"
                                        else "Χρησιμοποιήστε τις επικεφαλίδες του προτύπου."
                                    ),
                                    sheet,
                                    1,
                                    label,
                                    None,
                                    f"{get_column_letter(index+1)}1",
                                )
                            ]
                        )
                        continue
                    columns[spec.key] = (replace(spec, en=label, el=label), index)
                for spec in specs:
                    if spec.required and spec.key not in columns:
                        collect([_issue("required", sheet, 1, spec, None, locale)])
                specs = tuple(columns.get(spec.key, (spec, 0))[0] for spec in specs)
                continue
            if len(result) >= limits.max_rows:
                reject(
                    "row_limit",
                    "There are too many rows. Split the file.",
                    "Υπάρχουν υπερβολικά πολλές γραμμές. Χωρίστε το αρχείο.",
                    locale,
                )
            raw = {}
            values = {}
            errors = []
            labels = {}
            positions = {}
            cell_types = {}
            mapped_indexes = {index for _, index in columns.values()}
            unmapped = []
            for index, (value, source_type) in enumerate(cells):
                if (
                    index not in mapped_indexes
                    and value is not None
                    and str(value).strip()
                ):
                    position = f"{get_column_letter(index+1)}{number}"
                    label = str(header[index][0] or "") if index < len(header) else ""
                    unmapped.append(
                        {
                            "column": label,
                            "cell": position,
                            "value": serialize_source_value(value),
                            "data_type": source_type,
                        }
                    )
                    errors.append(
                        ImportIssue(
                            "unknown_column",
                            (
                                "Move this value into a supplied template column."
                                if locale == "en"
                                else "Μεταφέρετε αυτή την τιμή σε στήλη του παρεχόμενου προτύπου."
                            ),
                            sheet,
                            number,
                            label,
                            None,
                            position,
                        )
                    )
            if unmapped:
                raw["_unmapped_columns"] = unmapped
            for spec in specs:
                entry = columns.get(spec.key)
                if not entry:
                    if spec.required:
                        errors.append(
                            _issue("required", sheet, number, spec, None, locale)
                        )
                    continue
                _, index = entry
                value, cell_type = cells[index] if index < len(cells) else (None, "n")
                raw[spec.key] = serialize_source_value(value)
                cell_types[spec.key] = cell_type
                label = spec.label(locale)
                position = f"{get_column_letter(index+1)}{number}"
                labels[spec.key] = label
                positions[spec.key] = position
                escaped = False
                if file_format == "csv" and isinstance(value, str):
                    if (
                        value.startswith("''")
                        or value.startswith("'")
                        and value[1:].lstrip().startswith(("=", "+", "-", "@"))
                    ):
                        value = value[1:]
                        escaped = True
                dangerous = isinstance(value, str) and value.lstrip().startswith(
                    ("=", "+", "-", "@")
                )
                phone = (
                    spec.kind == "phone"
                    and isinstance(value, str)
                    and bool(re.fullmatch(r"\+?[\d ()\-.]+", value))
                )
                numeric = (
                    spec.kind in ("integer", "decimal")
                    and isinstance(value, str)
                    and bool(re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?", value))
                )
                if (
                    cell_type == "f"
                    or file_format == "csv"
                    and dangerous
                    and not (escaped or phone or numeric)
                ):
                    errors.append(
                        _issue("formula", sheet, number, spec, position, locale)
                    )
                    continue
                if cell_type == "e":
                    errors.append(
                        _issue("invalid_value", sheet, number, spec, position, locale)
                    )
                    continue
                try:
                    parsed = _value(value, spec.kind, source_locale)
                    if parsed is None:
                        if spec.required:
                            errors.append(
                                _issue(
                                    "required", sheet, number, spec, position, locale
                                )
                            )
                    else:
                        values[spec.key] = parsed
                except CellValueError as error:
                    errors.append(
                        _issue(error.code, sheet, number, spec, position, locale)
                    )
            if not errors:
                try:
                    _domain_issues(entity, values)
                except ValidationError as error:
                    for detail in error.errors(
                        include_context=False, include_url=False
                    ):
                        field = (
                            detail["loc"][0]
                            if detail["loc"]
                            else (
                                "valid_until"
                                if entity == "timetable"
                                else (
                                    "registration_plate"
                                    if entity == "vehicles"
                                    else specs[0].key
                                )
                            )
                        )
                        spec = next((s for s in specs if s.key == field), specs[0])
                        errors.append(
                            _issue(
                                "invalid_value",
                                sheet,
                                number,
                                spec,
                                positions.get(spec.key),
                                locale,
                            )
                        )
                except CellValueError as error:
                    spec = next(
                        (s for s in specs if s.key in ("minutes", "distance_km")),
                        specs[0],
                    )
                    errors.append(
                        _issue(
                            error.code,
                            sheet,
                            number,
                            spec,
                            positions.get(spec.key),
                            locale,
                        )
                    )
            if entity == "vehicles" and "registration_plate" in values:
                values["registration_plate"] = values["registration_plate"].upper()
            identities = [
                (key, values[key])
                for key in ("code", "trip_code", "registration_plate")
                if values.get(key)
            ]
            for key, value in identities:
                identity = (entity, key, value)
                if identity in seen:
                    spec = next(s for s in specs if s.key == key)
                    errors.append(
                        _issue(
                            "duplicate_reference",
                            sheet,
                            number,
                            spec,
                            positions.get(key),
                            locale,
                        )
                    )
                else:
                    seen[identity] = (sheet, number)
            collect(errors)
            result.append(
                ParsedRow(
                    entity,
                    sheet,
                    number,
                    raw,
                    values,
                    labels,
                    positions,
                    tuple(errors if issue_count <= limits.max_issues else errors[:1]),
                    cell_types=cell_types,
                )
            )
    if issue_count > limits.max_issues:
        issues[-1] = ImportIssue(
            "more_errors",
            (
                "More cells need correction. Fix the highlighted rows and validate again."
                if locale == "en"
                else "Χρειάζονται διόρθωση περισσότερα κελιά. Διορθώστε τις επισημασμένες γραμμές και ελέγξτε ξανά."
            ),
            "",
        )
    return ParsedWorkbook(
        SCHEMA_VERSION,
        filename[:200],
        file_format,
        locale,
        hashlib.sha256(content).hexdigest(),
        tuple(result),
        tuple(issues),
        source_locale,
    )
