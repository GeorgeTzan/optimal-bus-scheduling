"""Tenant-scoped canonical lookup snapshots and narrow optimistic source observations."""

from collections import defaultdict
from datetime import date
import json
import unicodedata
from sqlalchemy import tuple_
from app.domain.workforce.models import WorkforceDriver
from app.domain.fleet.models import Vehicle
from app.domain.timetables.models import (
    Station,
    ServiceTemplate,
    Route,
    DailyPairing,
    StationTransfer,
)
from app.domain.imports.models import ImportIdentity
from app.domain.resources.service import FIELDS
from app.domain.timetables.operations import TEMPLATE_FIELDS, EXCEPTION_FIELDS

MODELS = {
    "drivers": WorkforceDriver,
    "vehicles": Vehicle,
    "stations": Station,
    "timetable": ServiceTemplate,
}
PREFIXES = {"drivers": "D", "vehicles": "V", "stations": "S"}
SOURCE = "ktel-import-v1"


def normalized_name(value):
    return " ".join(
        "".join(
            char
            for char in unicodedata.normalize("NFD", value.casefold())
            if unicodedata.category(char) != "Mn"
        ).split()
    )


def ref_existing(kind, identifier):
    return {"kind": kind, "id": identifier}


def ref_row(kind, row_id):
    return {"kind": kind, "row_id": row_id}


def ref_station(key):
    return {"kind": "stations", "station_key": key}


def ref_key(ref):
    return json.dumps(ref, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class Catalog:
    def __init__(self, db, tenant_id):
        self.db = db
        self.tenant_id = tenant_id
        self.observed = {}
        self.records = {
            kind: {record.id: record for record in self.query(model).all()}
            for kind, model in MODELS.items()
        }
        self.codes = {
            kind: {
                (row.trip_code if kind == "timetable" else row.code): row
                for row in records.values()
            }
            for kind, records in self.records.items()
        }
        route_ids = {row.route_id for row in self.records["timetable"].values()}
        self.routes = (
            {
                row.id: row
                for row in self.query(Route).filter(Route.id.in_(route_ids)).all()
            }
            if route_ids
            else {}
        )
        from app.domain.resources.reference_reservations import remember_reservations
        all_aliases=self.query(ImportIdentity).all()
        remember_reservations(self.db,self.tenant_id,all_aliases)
        self.aliases = {
            (row.entity, row.external_key): row
            for row in all_aliases if row.source==SOURCE
        }
        self.driver_names = defaultdict(list)
        self.driver_licenses = defaultdict(list)
        self.driver_phones = defaultdict(list)
        for row in self.records["drivers"].values():
            self.driver_names[
                normalized_name(row.first_name + " " + row.last_name)
            ].append(row)
            if row.license_number:
                self.driver_licenses[row.license_number].append(row)
            if row.phone:
                self.driver_phones[row.phone].append(row)
        self.station_names = defaultdict(list)
        for row in self.records["stations"].values():
            for name in {
                row.code,
                normalized_name(row.name_el),
                normalized_name(row.name_en or ""),
            }:
                if name:
                    self.station_names[name].append(row)
        self.plates = {
            row.registration_plate.upper(): row
            for row in self.records["vehicles"].values()
            if row.registration_plate
        }
        self._connection_rows = None
        self.pairings = {}
        self.vehicle_pairings = {}
        self.transfers = {}

    def query(self, model):
        return self.db.query(model).filter(model.tenant_id == self.tenant_id)

    def observe(self, category, key, value):
        self.observed[
            json.dumps(
                [category, key],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        ] = value
        return value

    def record(self, kind, identifier):
        row = self.records[kind].get(identifier)
        self.observe("record", [kind, identifier], row.version if row else None)
        return row

    def code(self, kind, code):
        row = self.codes[kind].get(code)
        self.observe("code", [kind, code], [row.id, row.version] if row else None)
        return row

    def alias(self, kind, key):
        row = self.aliases.get((kind, key))
        self.observe("alias", [kind, key], [row.id, row.target_id] if row else None)
        return self.record(kind, row.target_id) if row else None

    def plate(self, value):
        row = self.plates.get(value.upper())
        self.observe("plate", value.upper(), [row.id, row.version] if row else None)
        return row

    def named_drivers(self, values):
        keys = [
            (
                "name",
                normalized_name(
                    values.get("first_name", "") + " " + values.get("last_name", "")
                ),
            )
        ]
        if values.get("license_number"):
            keys.append(("license", values["license_number"]))
        if values.get("phone"):
            keys.append(("phone", values["phone"]))
        found = {}
        for kind, key in keys:
            rows = {
                "name": self.driver_names,
                "license": self.driver_licenses,
                "phone": self.driver_phones,
            }[kind].get(key, [])
            self.observe(
                "driver_" + kind,
                key,
                [[row.id, row.version] for row in sorted(rows, key=lambda row: row.id)],
            )
            found.update({row.id: row for row in rows})
        return list(found.values())

    def stations_named(self, name):
        found = {
            row.id: row
            for key in (name, normalized_name(name))
            for row in self.station_names.get(key, [])
        }
        rows = sorted(found.values(), key=lambda row: row.id)
        self.observe("station_name", name, [[row.id, row.version] for row in rows])
        return rows

    def view(self, kind, row):
        if kind == "timetable":
            route = self.routes[row.route_id]
            self.observe("route", route.id, route.version)
            return {
                **{key: getattr(row, key) for key in TEMPLATE_FIELDS},
                "id": row.id,
                "version": row.version,
                "origin_station_id": route.origin_station_id,
                "destination_station_id": route.destination_station_id,
                "distance_km": route.distance_km,
            }
        return {key: getattr(row, key) for key in FIELDS[kind]}

    def label(self, kind, row):
        if kind == "drivers":
            return (row.first_name + " " + row.last_name).strip()
        if kind == "vehicles":
            return row.registration_plate or row.code
        if kind == "stations":
            return row.name_el
        return row.trip_code

    def candidate(self, kind, row):
        self.record(kind, row.id)
        return {
            "id": row.id,
            "version": row.version,
            "reference": row.trip_code if kind == "timetable" else row.code,
            "label": self.label(kind, row),
            "is_active": row.is_active,
        }

    def load_dated_relationships(self, dates):
        if not dates:
            return
        for row in (
            self.query(DailyPairing)
            .filter(
                DailyPairing.service_date.in_(
                    [date.fromisoformat(value) for value in dates]
                ),
                DailyPairing.is_active.is_(True),
            )
            .all()
        ):
            self.pairings[(row.service_date.isoformat(), row.driver_id)] = row
            self.vehicle_pairings[(row.service_date.isoformat(), row.vehicle_id)] = row

    def pairing(self, selected, driver_id, vehicle_id):
        by_driver = self.pairings.get((selected, driver_id))
        by_vehicle = self.vehicle_pairings.get((selected, vehicle_id))
        for key, row in [("driver", by_driver), ("vehicle", by_vehicle)]:
            self.observe(
                "pairing_" + key,
                [selected, driver_id if key == "driver" else vehicle_id],
                [row.id, row.version] if row else None,
            )
        return by_driver, by_vehicle

    def load_transfers(self, pairs):
        if not pairs:
            return
        for row in (
            self.query(StationTransfer)
            .filter(
                tuple_(
                    StationTransfer.origin_station_id,
                    StationTransfer.destination_station_id,
                ).in_(pairs)
            )
            .all()
        ):
            self.transfers[(row.origin_station_id, row.destination_station_id)] = row

    def transfer(self, origin, destination):
        row = self.transfers.get((origin, destination))
        self.observe(
            "transfer", [origin, destination], [row.id, row.version] if row else None
        )
        return row

    def connection_rows(self):
        from app.domain.timetables.models import ServiceConnection
        if self._connection_rows is None:
            self._connection_rows = self.query(ServiceConnection).order_by(ServiceConnection.id).all()
        self.observe('connection_catalog','all',[[row.id,row.version,row.incoming_template_id,row.outgoing_template_id,row.is_active] for row in self._connection_rows])
        return self._connection_rows

    def matches_snapshot(self, snapshot):
        decoded = [(encoded, *json.loads(encoded)) for encoded in snapshot]
        dates = {
            key[0]
            for _, category, key in decoded
            if category in ("pairing_driver", "pairing_vehicle")
        }
        self.load_dated_relationships(dates)
        self.load_transfers(
            {tuple(key) for _, category, key in decoded if category == "transfer"}
        )
        for encoded, category, key in decoded:
            if category == "connection_catalog":
                self.connection_rows()
            elif category == "record":
                self.record(*key)
            elif category == "code":
                self.code(*key)
            elif category == "alias":
                self.alias(*key)
            elif category == "plate":
                self.plate(key)
            elif category == "station_name":
                self.stations_named(key)
            elif category.startswith("driver_"):
                kind = category.removeprefix("driver_")
                rows = {
                    "name": self.driver_names,
                    "license": self.driver_licenses,
                    "phone": self.driver_phones,
                }[kind].get(key, [])
                self.observe(
                    category,
                    key,
                    [
                        [row.id, row.version]
                        for row in sorted(rows, key=lambda row: row.id)
                    ],
                )
            elif category == "route":
                row = self.routes.get(key)
                self.observe(category, key, row.version if row else None)
            elif category == "transfer":
                self.transfer(*key)
            elif category in ("pairing_driver", "pairing_vehicle"):
                rows = (
                    self.pairings
                    if category == "pairing_driver"
                    else self.vehicle_pairings
                )
                row = rows.get(tuple(key))
                self.observe(category, key, [row.id, row.version] if row else None)
            else:
                return False
            if self.observed.get(encoded) != snapshot[encoded]:
                return False
        return True
