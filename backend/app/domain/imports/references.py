"""Explicit reference checks; tenant catalogs come from the reviewed import transaction."""

from app.domain.imports.contracts import ImportIssue


def validate_references(workbook, catalog):
    issues = []
    for row in workbook.rows:
        keys = {
            "connections": {"incoming_ref": catalog.trip_refs, "outgoing_ref": catalog.trip_refs},
            "pairings": {
                "driver_ref": catalog.driver_refs,
                "vehicle_ref": catalog.vehicle_refs,
                "home_station": catalog.station_refs,
            },
            "drivers": {"home_station": catalog.station_refs},
            "vehicles": {"home_station": catalog.station_refs},
            "timetable": {
                "origin": catalog.station_refs,
                "destination": catalog.station_refs,
            },
            "transfers": {
                "origin": catalog.station_refs,
                "destination": catalog.station_refs,
            },
        }.get(row.entity, {})
        for field, known in keys.items():
            value = row.values.get(field)
            if value and value not in known:
                issues.append(
                    ImportIssue(
                        "unknown_reference",
                        (
                            "Choose a saved record or include it in this workbook."
                            if workbook.locale == "en"
                            else "Επιλέξτε αποθηκευμένη εγγραφή ή προσθέστε την στο βιβλίο."
                        ),
                        row.sheet,
                        row.row,
                        row.columns.get(field),
                        field,
                        row.cells.get(field),
                    )
                )
        if row.entity == "timetable":
            for category in row.values.get("allowed_bus_types", []):
                if category not in catalog.bus_types:
                    field = "allowed_bus_types"
                    issues.append(
                        ImportIssue(
                            "unknown_vehicle_category",
                            (
                                "Use a category from your actual fleet."
                                if workbook.locale == "en"
                                else "Χρησιμοποιήστε κατηγορία από τον πραγματικό στόλο σας."
                            ),
                            row.sheet,
                            row.row,
                            row.columns.get(field),
                            field,
                            row.cells.get(field),
                        )
                    )
    return tuple(issues)
