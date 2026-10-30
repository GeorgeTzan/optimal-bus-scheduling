"""Explicit literal cell normalization. No inferred clocks, dates or reference identity."""

import math
import re
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from app.domain.imports.template_schema import WEEKDAYS, ARRIVAL_DAYS


class CellValueError(ValueError):
    def __init__(self, code):
        self.code = code


def parse_cell_value(value, kind, locale):
    if value is None or isinstance(value, str) and not value.strip():
        return None
    if type(value) in (int, float):
        try:
            finite = math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            raise CellValueError("invalid_number")
    if isinstance(value, str):
        if any(ord(char) < 32 for char in value):
            raise CellValueError("invalid_value")
        value = value.strip()
    if kind in ("reference", "types", "phone") and not isinstance(value, str):
        raise CellValueError("text_reference_required")
    if kind in ("text", "reference", "phone"):
        return str(value)
    if kind == "date":
        if isinstance(value, datetime):
            if value.time() != time(0) or value.tzinfo is not None:
                raise CellValueError("invalid_date")
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if not isinstance(value, str):
            raise CellValueError("invalid_date")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            try:
                return date.fromisoformat(value).isoformat()
            except ValueError:
                raise CellValueError("invalid_date") from None
        match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", value)
        if match:
            a, b, year = map(int, match.groups())
            if 1 <= a <= 12 and 1 <= b <= 12 and a != b:
                raise CellValueError("ambiguous_date")
            day, month = (a, b) if locale == "el" else (b, a)
            try:
                return date(year, month, day).isoformat()
            except ValueError:
                pass
        raise CellValueError("invalid_date")
    if kind == "clock":
        if isinstance(value, time):
            if value.second or value.microsecond or value.tzinfo is not None:
                raise CellValueError("invalid_time")
            return value.strftime("%H:%M")
        if not isinstance(value, str) or not re.fullmatch(
            r"(?:[01]\d|2[0-3]):[0-5]\d", value
        ):
            raise CellValueError("invalid_time")
        return value
    if kind == "boolean":
        if type(value) is bool:
            return value
        choices = {
            "yes": True,
            "no": False,
            "true": True,
            "false": False,
            "ναι": True,
            "όχι": False,
            "οχι": False,
            "1": True,
            "0": False,
        }
        if str(value).casefold() not in choices:
            raise CellValueError("invalid_boolean")
        return choices[str(value).casefold()]
    if kind == "arrival_day":
        choices = {
            label.casefold(): index
            for labels in ARRIVAL_DAYS.values()
            for index, label in enumerate(labels)
        }
        choices.update({"0": 0, "1": 1, "2": 2})
        if type(value) is bool or str(value).casefold() not in choices:
            raise CellValueError("invalid_arrival_day")
        return choices[str(value).casefold()]
    if kind == "weekdays":
        choices = {
            label.casefold(): index
            for labels in WEEKDAYS.values()
            for index, label in enumerate(labels)
        }
        tokens = re.split(r"[\s,;|]+", str(value))
        if not tokens or any(token.casefold() not in choices for token in tokens):
            raise CellValueError("invalid_weekdays")
        days = [choices[token.casefold()] for token in tokens]
        if len(set(days)) != len(days):
            raise CellValueError("invalid_weekdays")
        return sorted(days)
    if kind == "types":
        values = [item.strip() for item in value.split("|")]
        if len(values) > 64 or any(not item or len(item) > 64 for item in values):
            raise CellValueError("invalid_value")
        return sorted(set(values))
    if kind in ("integer", "decimal"):
        if type(value) is bool:
            raise CellValueError("invalid_number")
        if isinstance(value, (int, float)):
            if not math.isfinite(value):
                raise CellValueError("invalid_number")
            number = Decimal(str(value))
        else:
            text = str(value)
            if "," in text:
                if locale != "el" or "." in text or text.count(",") != 1:
                    raise CellValueError("invalid_number")
                text = text.replace(",", ".")
            if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text):
                raise CellValueError("invalid_number")
            try:
                number = Decimal(text)
            except InvalidOperation:
                raise CellValueError("invalid_number") from None
        if kind == "integer":
            if number != number.to_integral_value():
                raise CellValueError("invalid_number")
            return int(number)
        parsed = float(number)
        if not math.isfinite(parsed):
            raise CellValueError("invalid_number")
        return parsed
    raise CellValueError("invalid_value")


def serialize_source_value(value):
    """Keep malformed and large native cells JSON-safe without losing their source type."""
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if type(value) is int and abs(value) > 2**53 - 1:
        return str(value)
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return str(value)
