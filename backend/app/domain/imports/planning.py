"""Read-only canonical import planning. No resource is created during preview."""

import hashlib
import json
from datetime import date, datetime
from fastapi import HTTPException
from app.domain.imports.catalog import (
    Catalog,
    MODELS,
    PREFIXES,
    normalized_name,
    ref_existing,
    ref_row,
    ref_station,
    ref_key,
)
from app.domain.imports.issues import row_issue
from app.domain.imports.template_schema import SHEETS
from app.domain.resources.service import FIELDS

BASIC = ("stations", "drivers", "vehicles", "timetable")
RELATIONS = {
    "drivers": {"home_station": "home_station_id"},
    "vehicles": {"home_station": "home_station_id"},
    "timetable": {
        "origin": "origin_station_id",
        "destination": "destination_station_id",
    },
}


def json_ready(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_ready(item) for item in value]
    return value


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(
            json_ready(value),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


class ImportPlanner:
    def __init__(self, db, batch, rows):
        self.db = db
        self.batch = batch
        self.rows = rows
        self.catalog = Catalog(db, batch.tenant_id)
        self.by_id = {row.id: row for row in rows}
        self.previous = {row.id: row.plan or {} for row in rows}
        self.used = {kind: set(self.catalog.codes[kind]) for kind in PREFIXES}
        for (kind, key), alias in self.catalog.aliases.items():
            if kind in self.used and key.startswith("code:"):
                self.used[kind].add(key.removeprefix("code:"))
        self.unreferenced_names = {}
        for row in rows:
            if (
                row.entity == "drivers"
                and not row.values.get("code")
                and not row.issues
            ):
                name = normalized_name(
                    row.values.get("first_name", "")
                    + " "
                    + row.values.get("last_name", "")
                )
                self.unreferenced_names[name] = self.unreferenced_names.get(name, 0) + 1
        for row in rows:
            if row.entity in self.used and row.values.get("code"):
                self.used[row.entity].add(row.values["code"])
        self.station_bindings = []
        self.station_binding_names = set()
        self.new_stations = {}
        self.aliases = []
        self.index = {}
        self.next_code = {kind: len(self.catalog.codes[kind]) + 1 for kind in PREFIXES}
        self.previous_stations = {
            item["name"]: item for item in batch.station_plan or []
        }
        self.previous_new = {
            item["key"]: item for item in batch.station_plan or [] if item.get("key")
        }
        self.plan_by_target = {}

    def error(self, row, code, en, el, field=None):
        row.plan["issues"].append(row_issue(row, code, en, el, field))

    def allocate(self, kind, wanted=None):
        if wanted and wanted not in self.used[kind]:
            value = wanted
        else:
            number = self.next_code[kind]
            while (value := f"{PREFIXES[kind]}{number:05d}") in self.used[kind]:
                number += 1
            self.next_code[kind] = number + 1
        self.used[kind].add(value)
        self.catalog.code(kind, value)
        self.catalog.alias(kind, "code:" + value)
        return value

    def choose_target(self, row):
        kind = row.entity
        values = row.values
        code = values.get("trip_code" if kind == "timetable" else "code")
        found = {}
        if code:
            for target in (
                self.catalog.alias(kind, "code:" + code),
                self.catalog.code(kind, code),
            ):
                if target:
                    found[target.id] = target
        if kind == "vehicles" and values.get("registration_plate"):
            plate = values["registration_plate"].upper()
            for target in (
                self.catalog.alias(kind, "registration:" + plate),
                self.catalog.plate(plate),
            ):
                if target:
                    found[target.id] = target
        if len(found) > 1:
            self.error(
                row,
                "identity_conflict",
                "These references identify different records. Correct the reference before saving.",
                "Οι κωδικοί αντιστοιχούν σε διαφορετικές εγγραφές. Διορθώστε τον κωδικό πριν την αποθήκευση.",
                "code",
            )
            return None
        target = next(iter(found.values()), None)
        resolution = row.resolution or {}
        if resolution.get("mode") == "new":
            if target:
                self.error(
                    row,
                    "reference_exists",
                    "This reference already belongs to a saved record. Choose that record or a different reference.",
                    "Ο κωδικός ανήκει ήδη σε αποθηκευμένη εγγραφή. Επιλέξτε την ή χρησιμοποιήστε διαφορετικό κωδικό.",
                    "code",
                )
            return None
        if resolution.get("mode") == "existing":
            chosen = self.catalog.record(kind, resolution["target_id"])
            if chosen is None:
                self.error(
                    row,
                    "unknown_reference",
                    "Choose a record from your organization.",
                    "Επιλέξτε εγγραφή του οργανισμού σας.",
                )
                return None
            if target and target.id != chosen.id:
                self.error(
                    row,
                    "identity_conflict",
                    "This reference belongs to another record. Correct it before matching.",
                    "Ο κωδικός ανήκει σε άλλη εγγραφή. Διορθώστε τον πριν την αντιστοίχιση.",
                    "code",
                )
                return None
            if chosen.version != resolution.get("target_version"):
                self.error(
                    row,
                    "match_changed",
                    "The selected record changed. Review and select it again.",
                    "Η επιλεγμένη εγγραφή άλλαξε. Ελέγξτε την και επιλέξτε την ξανά.",
                )
                return None
            return chosen
        if target:
            return target
        if kind == "drivers":
            duplicate_name = (
                not code
                and self.unreferenced_names.get(
                    normalized_name(
                        values.get("first_name", "") + " " + values.get("last_name", "")
                    ),
                    0,
                )
                > 1
            )
            candidates = self.catalog.named_drivers(values)
            first_import = not self.catalog.records["drivers"] or self.previous[
                row.id
            ].get("new_initial_register", False)
            if duplicate_name or candidates or not code and not first_import:
                row.plan["candidates"] = [
                    self.catalog.candidate(kind, value) for value in candidates[:10]
                ]
                row.plan["action"] = "resolve"
                self.error(
                    row,
                    "person_needs_match",
                    "Confirm this is a new person, or match a saved driver. Names alone do not identify a person.",
                    "Επιβεβαιώστε ότι είναι νέος οδηγός ή αντιστοιχίστε αποθηκευμένο οδηγό. Το όνομα μόνο δεν αρκεί.",
                )
                return None
            if not code and first_import:
                row.plan["new_initial_register"] = True
        return None

    def identify(self, row):
        row.plan = {
            "action": "invalid" if row.issues else "new",
            "issues": list(row.issues),
            "target": None,
            "candidates": [],
            "payload": {},
            "relations": {},
            "before": {},
            "changed_fields": [],
            "aliases": [],
        }
        if row.issues:
            return
        if row.entity in PREFIXES and not row.values.get("code"):
            row.planned_reference = self.allocate(row.entity, row.planned_reference)
        target = self.choose_target(row)
        if row.plan["issues"]:
            return
        kind = row.entity
        before = self.catalog.view(kind, target) if target else {}
        if target:
            self.catalog.record(kind, target.id)
            row.plan["target"] = self.catalog.candidate(kind, target)
            previous = self.plan_by_target.get((kind, target.id))
            if previous:
                for duplicate in (previous, row):
                    self.error(
                        duplicate,
                        "duplicate_target",
                        "Two rows identify the same saved record. Keep one version or correct the references.",
                        "Δύο γραμμές αντιστοιχούν στην ίδια εγγραφή. Διατηρήστε μία εκδοχή ή διορθώστε τους κωδικούς.",
                        "trip_code" if kind == "timetable" else "code",
                    )
            else:
                self.plan_by_target[(kind, target.id)] = row
        fields = (
            set(FIELDS[kind]) - {"id", "version", "home_station_id"}
            if kind in FIELDS
            else {
                "trip_code",
                "departure_time",
                "arrival_time",
                "arrival_day_offset",
                "operating_weekdays",
                "valid_from",
                "valid_until",
                "allowed_bus_types",
                "distance_km",
                "is_active",
            }
        )
        payload = {key: value for key, value in row.values.items() if key in fields}
        code_field = "trip_code" if kind == "timetable" else "code"
        source_code = row.values.get(code_field)
        if target:
            # A source alias identifies a record; it never silently renames its canonical reference.
            payload.pop(code_field, None)
        else:
            if kind != "timetable":
                reference = source_code or row.planned_reference
                row.planned_reference = reference
                payload["code"] = reference
            elif source_code:
                row.planned_reference = source_code
        row.plan["payload"] = payload
        row.plan["before"] = json_ready(before)
        row.plan["ref"] = (
            ref_existing(kind, target.id) if target else ref_row(kind, row.id)
        )
        if source_code:
            row.plan["aliases"].append("code:" + source_code)
        canonical_reference = (
            (target.trip_code if kind == "timetable" else target.code)
            if target
            else payload.get(code_field)
        )
        if canonical_reference:
            row.plan["aliases"].append("code:" + canonical_reference)
            mapped = self.catalog.alias(kind, "code:" + canonical_reference)
            if mapped and (target is None or mapped.id != target.id):
                self.error(
                    row,
                    "identity_conflict",
                    "The canonical reference has another historical match. Review its reference before importing.",
                    "Ο κωδικός έχει άλλη ιστορική αντιστοίχιση. Ελέγξτε τον πριν την εισαγωγή.",
                    "code",
                )
        if kind == "vehicles" and row.values.get("registration_plate"):
            row.plan["aliases"].append(
                "registration:" + row.values["registration_plate"].upper()
            )

    def add_index(self, kind, value, ref):
        if value:
            self.index.setdefault((kind, value), {})[ref_key(ref)] = ref

    def build_indexes(self):
        for row in self.rows:
            if row.entity not in BASIC:
                continue
            ref = row.plan.get("ref") or ref_row(row.entity, row.id)
            code = row.values.get("trip_code" if row.entity == "timetable" else "code")
            self.add_index(row.entity, code, ref)
            if row.entity == "vehicles":
                self.add_index(
                    "vehicles", row.values.get("registration_plate", "").upper(), ref
                )
            if row.entity == "stations":
                for key in ("name_el", "name_en"):
                    if row.values.get(key):
                        self.add_index(
                            "station_name", normalized_name(row.values[key]), ref
                        )

    def indexed(self, kind, value):
        return list(self.index.get((kind, value), {}).values())

    def record_ref(self, row, kind, value, field):
        found = {ref_key(ref): ref for ref in self.indexed(kind, value)}
        targets=[self.catalog.alias(kind, "code:"+value), self.catalog.code(kind,value)]
        if kind == "vehicles":
            targets.extend([self.catalog.alias(kind,"registration:"+value.upper()),self.catalog.plate(value)])
        for target in targets:
            if target:
                ref=ref_existing(kind,target.id)
                found[ref_key(ref)]=ref
        if len(found)>1:
            self.error(row,"identity_conflict","This reference identifies different records. Correct the saved reference before importing.","Ο κωδικός αντιστοιχεί σε διαφορετικές εγγραφές. Διορθώστε τον πριν την εισαγωγή.",field)
            return None
        if len(found) != 1:
            self.error(
                row,
                "unknown_reference",
                "Choose a saved reference, or include the related record in this workbook.",
                "Επιλέξτε αποθηκευμένο κωδικό ή προσθέστε τη σχετική εγγραφή στο βιβλίο.",
                field,
            )
            return None
        return next(iter(found.values()))

    def station_ref(self, row, name, field):
        choice = (self.batch.station_resolutions or {}).get(name)
        found = {ref_key(ref): ref for ref in self.indexed("stations", name)}
        found.update(
            {
                ref_key(ref): ref
                for ref in self.indexed("station_name", normalized_name(name))
            }
        )
        existing = self.catalog.stations_named(name)
        for target in existing:
            found[ref_key(ref_existing("stations", target.id))] = ref_existing(
                "stations", target.id
            )
        for key in ("code:" + name, "name:" + normalized_name(name)):
            target = self.catalog.alias("stations", key)
            if target:
                found[ref_key(ref_existing("stations", target.id))] = ref_existing(
                    "stations", target.id
                )
        if choice and choice["mode"] == "existing":
            target = self.catalog.record("stations", choice["target_id"])
            if not target or target.version != choice["target_version"]:
                self.error(
                    row,
                    "station_match_changed",
                    "The selected station changed. Review it again.",
                    "Ο επιλεγμένος σταθμός άλλαξε. Ελέγξτε τον ξανά.",
                    field,
                )
                return None
            selected = ref_existing("stations", target.id)
        elif choice and choice["mode"] == "new":
            selected = None
        elif len(found) > 1:
            self.error(
                row,
                "station_needs_match",
                "More than one station matches. Choose a station or use its reference.",
                "Αντιστοιχούν περισσότεροι σταθμοί. Επιλέξτε έναν ή χρησιμοποιήστε τον κωδικό του.",
                field,
            )
            return None
        elif found:
            selected = next(iter(found.values()))
            old = self.previous_stations.get(name, {}).get("ref")
            if old and old.get("id") and old != selected:
                self.error(
                    row,
                    "station_needs_match",
                    "This station match changed. Review it before saving.",
                    "Η αντιστοίχιση σταθμού άλλαξε. Ελέγξτε την πριν την αποθήκευση.",
                    field,
                )
                return None
        else:
            old = self.previous_stations.get(name, {}).get("ref")
            if old and old.get("id"):
                self.catalog.record("stations", old["id"])
                self.error(
                    row,
                    "station_needs_match",
                    "A previously matched station changed its name. Choose the intended station.",
                    "Ένας αντιστοιχισμένος σταθμός άλλαξε όνομα. Επιλέξτε τον σωστό σταθμό.",
                    field,
                )
                return None
            selected = None
        if selected is None:
            new_name = (choice or {}).get("new_name") or name
            key = hashlib.sha256(normalized_name(new_name).encode()).hexdigest()
            if key not in self.new_stations:
                old = self.previous_new.get(key, {})
                self.new_stations[key] = {
                    "key": key,
                    "name": name,
                    "name_el": new_name,
                    "code": self.allocate("stations", old.get("code")),
                    "ref": ref_station(key),
                    "source_names": [],
                }
                self.aliases.append(
                    {
                        "entity": "stations",
                        "key": "code:" + self.new_stations[key]["code"],
                        "ref": ref_station(key),
                    }
                )
            self.new_stations[key]["source_names"].append(name)
            selected = ref_station(key)
        if name not in self.station_binding_names:
            self.station_bindings.append({"name": name, "ref": selected})
            self.station_binding_names.add(name)
        target_code = (
            self.catalog.records["stations"][selected["id"]].code
            if selected.get("id")
            else (
                self.by_id[selected["row_id"]].values.get("code")
                if selected.get("row_id")
                else None
            )
        )
        key = "code:" + name if name == target_code else "name:" + normalized_name(name)
        self.aliases.append({"entity": "stations", "key": key, "ref": selected})
        return selected

    def active(self, ref):
        if "station_key" in ref:
            return True
        related = (
            self.by_id.get(ref.get("row_id"))
            if "row_id" in ref
            else self.plan_by_target.get((ref["kind"], ref.get("id")))
        )
        if related:
            if related.plan["issues"]:
                return False
            return related.values.get(
                "is_active",
                (
                    True
                    if "row_id" in ref
                    else bool(self.catalog.records[ref["kind"]][ref["id"]].is_active)
                ),
            )
        target = self.catalog.record(ref["kind"], ref["id"])
        return bool(target and target.is_active)

    def fill_relations(self, row):
        if row.plan["issues"]:
            return
        for field, column in RELATIONS.get(row.entity, {}).items():
            name = row.values.get(field)
            if not name:
                continue
            ref = self.station_ref(row, name, field)
            if ref:
                row.plan["relations"][column] = ref
                if not self.active(ref):
                    self.error(
                        row,
                        "inactive_reference",
                        "Choose an active station or correct the related row first.",
                        "Επιλέξτε ενεργό σταθμό ή διορθώστε πρώτα τη σχετική γραμμή.",
                        field,
                    )

    def finish_basic(self, row):
        if row.plan["issues"]:
            if row.plan["action"] != "resolve":
                row.plan["action"] = "invalid"
            return
        before = row.plan["before"]
        payload = row.plan["payload"]
        changed = [
            key
            for key, value in payload.items()
            if json_ready(before.get(key)) != json_ready(value)
        ]
        for column, ref in row.plan["relations"].items():
            if (
                ref.get("id") != before.get(column)
                or "row_id" in ref
                or "station_key" in ref
            ):
                changed.append(column)
        row.plan["changed_fields"] = changed
        row.plan["action"] = (
            "new"
            if row.plan["target"] is None
            else "update" if changed else "unchanged"
        )
        for key in row.plan["aliases"]:
            self.aliases.append(
                {"entity": row.entity, "key": key, "ref": row.plan["ref"]}
            )

    def dated_relations(self, row):
        if row.plan["issues"]:
            return
        if row.entity == "pairings":
            fields = (
                ("driver_ref", "driver_id", "drivers"),
                ("vehicle_ref", "vehicle_id", "vehicles"),
                ("home_station", "home_station_id", "stations"),
            )
        else:
            fields = (
                ("origin", "origin_station_id", "stations"),
                ("destination", "destination_station_id", "stations"),
            )
        for field, column, kind in fields:
            value = row.values[field]
            ref = (
                self.station_ref(row, value, field)
                if kind == "stations"
                else self.record_ref(row, kind, value, field)
            )
            if ref:
                row.plan["relations"][column] = ref
                if not self.active(ref):
                    self.error(
                        row,
                        "inactive_reference",
                        "Choose an active related record, or correct its row first.",
                        "Επιλέξτε ενεργή σχετική εγγραφή ή διορθώστε πρώτα τη γραμμή της.",
                        field,
                    )

    def pending_changes(self, ref, fields):
        related = (
            self.by_id.get(ref.get("row_id"))
            if ref.get("row_id")
            else self.plan_by_target.get((ref["kind"], ref.get("id")))
        )
        return bool(
            related and set(related.plan.get("changed_fields", [])).intersection(fields)
        )

    def finish_pairing(self, row):
        if row.plan["issues"]:
            return
        relations = row.plan["relations"]
        selected = row.values["service_date"]
        driver = relations["driver_id"]
        vehicle = relations["vehicle_id"]
        home = relations["home_station_id"]
        current, busy = self.catalog.pairing(
            selected, driver.get("id"), vehicle.get("id")
        )
        if busy and (current is None or busy.id != current.id):
            self.error(
                row,
                "vehicle_already_paired",
                "This vehicle is already paired on this date. Review the service day first.",
                "Το όχημα έχει ήδη ζεύγος σε αυτή την ημερομηνία. Ελέγξτε πρώτα την ημέρα υπηρεσίας.",
                "vehicle_ref",
            )
            return
        before = (
            {
                "service_date": selected,
                "driver_id": current.driver_id,
                "vehicle_id": current.vehicle_id,
                "home_station_id": current.home_station_id,
            }
            if current
            else {}
        )
        changed = [
            key
            for key, ref in relations.items()
            if "id" not in ref or ref["id"] != before.get(key)
        ]
        row.plan.update(
            payload={"service_date": selected},
            before=before,
            changed_fields=changed,
            target=(
                {
                    "id": current.id,
                    "version": current.version,
                    "reference": selected,
                    "label": selected,
                }
                if current
                else None
            ),
            ref=(
                ref_existing("pairings", current.id)
                if current
                else ref_row("pairings", row.id)
            ),
            action="new" if current is None else "update" if changed else "unchanged",
            needs_confirmation=current is None
            or not current.is_confirmed
            or bool(changed),
        )
        if current:
            from app.domain.timetables.operations import pairing_fingerprint

            row.plan[
                "needs_confirmation"
            ] |= current.confirmed_source_hash != pairing_fingerprint(
                self.catalog.records["drivers"][current.driver_id],
                self.catalog.records["vehicles"][current.vehicle_id],
                self.catalog.records["stations"][current.home_station_id],
            )
        row.plan["needs_confirmation"] |= any(
            self.pending_changes(
                ref,
                {
                    "is_active",
                    "home_station_id",
                    "bus_type",
                    "is_depot",
                    "latitude",
                    "longitude",
                },
            )
            for ref in (driver, vehicle, home)
        )

    def finish_transfer(self, row):
        if row.plan["issues"]:
            return
        relations = row.plan["relations"]
        origin = relations["origin_station_id"]
        destination = relations["destination_station_id"]
        if origin == destination:
            self.error(
                row,
                "same_station",
                "Choose two different stations.",
                "Επιλέξτε δύο διαφορετικούς σταθμούς.",
                "destination",
            )
            return
        current = (
            self.catalog.transfer(origin["id"], destination["id"])
            if origin.get("id") and destination.get("id")
            else None
        )
        payload = {
            key: value
            for key, value in row.values.items()
            if key in ("minutes", "source_note")
        }
        before = (
            {"minutes": current.minutes, "source_note": current.source_note}
            if current
            else {}
        )
        changed = [key for key, value in payload.items() if value != before.get(key)]
        review = any(
            self.pending_changes(
                ref, {"is_depot", "latitude", "longitude", "is_active"}
            )
            for ref in (origin, destination)
        )
        if current:
            from app.domain.timetables.operations import (
                station_facts,
                fingerprint as source_fingerprint,
            )

            review |= current.confirmed_source_hash != source_fingerprint(
                [
                    station_facts(self.catalog.records["stations"][origin["id"]]),
                    station_facts(self.catalog.records["stations"][destination["id"]]),
                ]
            )
        row.plan.update(
            payload=payload,
            before=before,
            changed_fields=changed,
            target=(
                {
                    "id": current.id,
                    "version": current.version,
                    "reference": row.values["origin"]
                    + " → "
                    + row.values["destination"],
                    "label": row.values["origin"] + " → " + row.values["destination"],
                }
                if current
                else None
            ),
            ref=(
                ref_existing("transfers", current.id)
                if current
                else ref_row("transfers", row.id)
            ),
            action=(
                "new"
                if current is None
                else "update" if changed or review else "unchanged"
            ),
        )

    def build(self):
        for row in self.rows:
            if row.entity in BASIC:
                self.identify(row)
            else:
                row.plan = {
                    "action": "invalid",
                    "target": None,
                    "issues": list(row.issues),
                    "payload": {},
                    "relations": {},
                    "candidates": [],
                }
        self.build_indexes()
        for row in self.rows:
            if row.entity in BASIC:
                self.fill_relations(row)
        for row in self.rows:
            if row.entity in BASIC:
                self.finish_basic(row)
        from app.domain.imports.connection_planning import plan_connections
        plan_connections(self)
        self.catalog.load_dated_relationships(
            {
                row.values["service_date"]
                for row in self.rows
                if row.entity == "pairings" and not row.plan["issues"]
            }
        )
        transfer_pairs = set()
        for row in self.rows:
            if row.entity in ('pairings','transfers'):
                self.dated_relations(row)
            if row.entity == "transfers" and not row.plan["issues"]:
                refs = row.plan["relations"]
                a = refs.get("origin_station_id", {})
                b = refs.get("destination_station_id", {})
                if a.get("id") and b.get("id"):
                    transfer_pairs.add((a["id"], b["id"]))
        self.catalog.load_transfers(transfer_pairs)
        for row in self.rows:
            if row.entity == "pairings":
                self.finish_pairing(row)
            elif row.entity == "transfers":
                self.finish_transfer(row)
            if row.plan["issues"] and row.plan["action"] != "resolve":
                row.plan["action"] = "invalid"
        source_rows = {
            kind: [row for row in self.rows if row.entity == kind] for kind in SHEETS
        }
        summary = {
            "new": sum(row.plan["action"] == "new" for row in self.rows)
            + len(self.new_stations),
            "updated": sum(row.plan["action"] == "update" for row in self.rows),
            "unchanged": sum(row.plan["action"] == "unchanged" for row in self.rows),
            "invalid": sum(row.plan["action"] == "invalid" for row in self.rows),
            "needs_match": sum(row.plan["action"] == "resolve" for row in self.rows),
            "new_stations": len(self.new_stations),
            "pairings_need_confirmation": sum(
                bool(row.plan.get("needs_confirmation")) for row in self.rows
            ),
            "will_archive": sum(
                row.plan.get("payload", {}).get("is_active") is False
                and row.plan["action"] == "update"
                for row in self.rows
            ),
            "by_entity": {
                kind: {
                    "new": sum(row.plan["action"] == "new" for row in members),
                    "updated": sum(row.plan["action"] == "update" for row in members),
                    "unchanged": sum(
                        row.plan["action"] == "unchanged" for row in members
                    ),
                }
                for kind, members in source_rows.items()
                if members
            },
        }
        if self.new_stations:
            summary["by_entity"].setdefault(
                "stations", {"new": 0, "updated": 0, "unchanged": 0}
            )["new"] += len(self.new_stations)
        bindings = [
            {**self.new_stations.get(item["ref"].get("station_key"), {}), **item}
            for item in self.station_bindings
        ]
        return (
            summary,
            self.catalog.observed,
            bindings,
            list(
                {
                    (item["entity"], item["key"], ref_key(item["ref"])): item
                    for item in self.aliases
                }.values()
            ),
        )
