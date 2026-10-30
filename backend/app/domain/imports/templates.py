"""Safe localized templates; sample people/services appear only in Instructions."""

import csv
import io
from datetime import date, datetime, time
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from app.domain.imports.contracts import SCHEMA_VERSION, ImportLimits
from app.domain.imports.template_schema import SHEETS, WEEKDAYS, ARRIVAL_DAYS, title


def export_value(value, column, locale):
    if value is None:
        return ""
    if isinstance(value, bool):
        return (
            ("Ναι" if value else "Όχι")
            if locale == "el"
            else ("Yes" if value else "No")
        )
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if column.kind == "weekdays" and isinstance(value, (list, tuple)):
        return " ".join(WEEKDAYS[locale][day] for day in value)
    if column.kind == "types" and isinstance(value, (list, tuple)):
        return " | ".join(value)
    if column.kind == "arrival_day" and type(value) is int and 0 <= value <= 2:
        return ARRIVAL_DAYS[locale][value]
    return value


def escape_csv(value):
    text = str(value)
    if (
        text.startswith("'")
        or text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@"))
        or text.startswith(("\t", "\r", "\n"))
    ):
        return "'" + text
    return text


def generate_template(
    entity, locale, populated_records=None, *, file_format="xlsx", limits=None
):
    limits = limits or ImportLimits()
    if locale not in ("en", "el") or entity not in (*SHEETS, "all"):
        raise ValueError("Choose a supported template and language")
    entities = tuple(SHEETS) if entity == "all" else (entity,)

    def records(key):
        if populated_records is None:
            return []
        return (
            populated_records.get(key, [])
            if isinstance(populated_records, dict)
            else populated_records
        )

    if file_format == "csv":
        if entity == "all":
            raise ValueError("Download CSV one entity at a time")
        output = io.StringIO(newline="")
        writer = csv.writer(output, delimiter=";" if locale == "el" else ",")
        columns = SHEETS[entity][2]
        writer.writerow([column.label(locale) for column in columns])
        for row in records(entity):
            writer.writerow(
                [
                    escape_csv(export_value(row.get(column.key), column, locale))
                    for column in columns
                ]
            )
        return output.getvalue().encode("utf-8-sig")
    if file_format != "xlsx":
        raise ValueError("Choose XLSX or CSV")
    book = Workbook()
    instructions = book.active
    instructions.title = "Οδηγίες" if locale == "el" else "Instructions"
    lines = [
        (
            "KTEL Operations",
            (
                "Τα στοιχεία σας, ένα βήμα τη φορά."
                if locale == "el"
                else "Your records, one step at a time."
            ),
        ),
        ("Έκδοση προτύπου" if locale == "el" else "Template version", SCHEMA_VERSION),
        ("Πρότυπο" if locale == "el" else "Template", entity),
        ("Γλώσσα" if locale == "el" else "Language", locale),
        ("Χρώματα στηλών" if locale == "el" else "Column colours",
         "Πράσινο: υποχρεωτικό. Μπλε: προαιρετικό." if locale == "el" else "Teal: required. Navy: optional."),
        (
            "Ξεκινήστε εδώ" if locale == "el" else "Start here",
            (
                "Συμπληρώστε μόνο τα φύλλα που χρειάζεστε. Τα κενά φύλλα αγνοούνται."
                if locale == "el"
                else "Complete only the sheets you need. Empty sheets are ignored."
            ),
        ),
        (
            "Κωδικοί" if locale == "el" else "References",
            (
                "Χρησιμοποιήστε κείμενο για κωδικούς όπως 00001. Μην αφαιρείτε τα αρχικά μηδενικά."
                if locale == "el"
                else "Keep references such as 00001 as text, including leading zeroes."
            ),
        ),
        (
            "Ημερομηνίες" if locale == "el" else "Dates",
            (
                "2026-06-01 — έτος-μήνας-ημέρα."
                if locale == "el"
                else "2026-06-01 — year-month-day."
            ),
        ),
        (
            "Ώρες" if locale == "el" else "Times",
            (
                "08:30 — επιλέξτε ρητά την ημέρα άφιξης."
                if locale == "el"
                else "08:30 — explicitly choose the arrival day."
            ),
        ),
        (
            "Ημέρες λειτουργίας" if locale == "el" else "Operating days",
            " ".join(WEEKDAYS[locale][:5]),
        ),
        (
            "Κατηγορίες" if locale == "el" else "Categories",
            (
                "02 | 03 — χρησιμοποιήστε τις πραγματικές κατηγορίες του στόλου."
                if locale == "el"
                else "02 | 03 — use the actual categories in your fleet."
            ),
        ),
        (
            "Παράδειγμα οδηγού" if locale == "el" else "Driver example",
            (
                "00001 · Νίκος · Δήμου — παράδειγμα μόνο, δεν εισάγεται."
                if locale == "el"
                else "00001 · Nikos · Dimou — example only, never imported."
            ),
        ),
        (
            "Τύποι κελιών" if locale == "el" else "Cell values",
            (
                "Επικολλήστε τιμές, χωρίς τύπους, μακροεντολές ή εξωτερικούς συνδέσμους."
                if locale == "el"
                else "Paste values, without formulas, macros or external links."
            ),
        ),
        (
            "Αποθήκευση" if locale == "el" else "Saving",
            (
                "Η προεπισκόπηση δεν αλλάζει εγγραφές. Ελέγξτε πριν αποθηκεύσετε."
                if locale == "el"
                else "Preview changes no live records. Review before saving."
            ),
        ),
        (
            "Ζεύγη" if locale == "el" else "Pairings",
            (
                "Τα εισαγόμενα ζεύγη χρειάζονται επιβεβαίωση ανά ημέρα."
                if locale == "el"
                else "Imported pairings need confirmation for their service day."
            ),
        ),
    ]
    lines.append(
        (
            "Όρια αρχείου" if locale == "el" else "Upload limits",
            (
                f"Μέχρι {limits.max_rows} εγγραφές, μέγιστο {limits.max_upload_bytes/1024**2:g} MB."
                if locale == "el"
                else f"Up to {limits.max_rows} rows; maximum {limits.max_upload_bytes/1024**2:g} MB."
            ),
        )
    )
    if "vehicles" in entities:
        lines.append(
            (
                "Στοιχεία οχήματος" if locale == "el" else "Vehicle identity",
                (
                    "Συμπληρώστε πινακίδα ή κωδικό οχήματος και την πραγματική κατηγορία του στόλου."
                    if locale == "el"
                    else "Enter a registration or vehicle reference, and its actual fleet category."
                ),
            )
        )
    if "transfers" in entities:
        lines.append(
            (
                "Χρόνοι μετακίνησης" if locale == "el" else "Travel times",
                (
                    "Επιβεβαιωμένα λεπτά χωρίς επιβάτες, ανά κατεύθυνση. Μην υπολογίζετε από το επιβατικό δρομολόγιο."
                    if locale == "el"
                    else "Confirmed minutes without passengers, per direction. Do not infer them from passenger services."
                ),
            )
        )
    for key in entities:
        required = ", ".join(
            column.label(locale) for column in SHEETS[key][2] if column.required
        )
        lines.append(
            (
                title(key, locale),
                ("Απαιτούνται: " if locale == "el" else "Required: ") + required,
            )
        )
    for row in lines:
        instructions.append(row)
    instructions.column_dimensions["A"].width = 28
    instructions.column_dimensions["B"].width = 100
    for row in instructions:
        for cell in row:
            cell.data_type = "s"
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        instructions.row_dimensions[row[0].row].height = 32
    for key in entities:
        sheet = book.create_sheet(title(key, locale))
        columns = SHEETS[key][2]
        sheet.append([column.label(locale) for column in columns])
        sheet.freeze_panes = "A2"
        sheet.sheet_properties.tabColor = "0D9488"
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(columns))}1"
        for index, column in enumerate(columns, 1):
            letter = get_column_letter(index)
            sheet.column_dimensions[letter].width = max(
                20, min(36, len(column.label(locale)) + 4)
            )
            if column.kind in (
                "reference",
                "text",
                "phone",
                "types",
                "weekdays",
                "clock",
                "date",
            ):
                sheet.column_dimensions[letter].number_format = "@"
            options = (
                ARRIVAL_DAYS[locale]
                if column.kind == "arrival_day"
                else (
                    (("Ναι", "Όχι") if locale == "el" else ("Yes", "No"))
                    if column.kind == "boolean"
                    else None
                )
            )
            if options:
                validation = DataValidation(
                    type="list",
                    formula1='"' + ",".join(options) + '"',
                    allow_blank=not column.required,
                )
                validation.errorTitle = (
                    "Ελέγξτε την επιλογή" if locale == "el" else "Check your selection"
                )
                validation.error = (
                    "Επιλέξτε μια τιμή από τη λίστα."
                    if locale == "el"
                    else "Choose a value from the list."
                )
                validation.showErrorMessage = True
                sheet.add_data_validation(validation)
                validation.add(f"{letter}2:{letter}{limits.max_rows+1}")
        for row_index, data in enumerate(records(key), 2):
            sheet.append(
                [
                    export_value(data.get(column.key), column, locale)
                    for column in columns
                ]
            )
            for column_index in range(1, len(columns) + 1):
                cell = sheet.cell(row_index, column_index)
                if isinstance(cell.value, str):
                    cell.data_type = "s"
                    cell.number_format = "@"
    for sheet in book:
        sheet.row_dimensions[1].height = 28
        for cell in sheet[1]:
            cell.font = Font(color="FFFFFF", bold=True)
            cell.fill = PatternFill("solid", fgColor="10273F")
    for key in entities:
        sheet = book[title(key, locale)]
        for index, column in enumerate(SHEETS[key][2], 1):
            if column.required:
                sheet.cell(1, index).fill = PatternFill("solid", fgColor="087F7A")
    output = io.BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()
