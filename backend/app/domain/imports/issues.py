"""Human-readable bilingual import issues; source addresses remain the uploaded ones."""

from dataclasses import asdict, replace
from app.domain.imports.parsers import _issue
from app.domain.imports.template_schema import SHEETS


def parser_issue(issue, entity):
    data = asdict(issue)
    spec = (
        next((spec for spec in SHEETS[entity][2] if spec.key == issue.field), None)
        if entity
        else None
    )
    if spec:
        spec = replace(spec, en=issue.column or spec.en, el=issue.column or spec.el)
        data["messages"] = {
            locale: _issue(
                issue.code, issue.sheet, issue.row, spec, issue.cell, locale
            ).message
            for locale in ("en", "el")
        }
    return data


def row_issue(row, code, en, el, field=None):
    return {
        "code": code,
        "message": en,
        "messages": {"en": en, "el": el},
        "sheet": row.sheet,
        "row": row.row_number,
        "column": row.source_columns.get(field),
        "field": field,
        "cell": row.source_cells.get(field),
    }


def issue_view(value, locale):
    return {
        **value,
        "message": value.get("messages", {}).get(locale, value.get("message", "")),
    }
