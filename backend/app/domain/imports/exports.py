"""Commit-time export snapshots: human references, never database identifiers."""

from app.domain.imports.catalog import MODELS, ref_key
from app.domain.imports.template_schema import SHEETS
from app.domain.imports.planning import json_ready
from app.domain.timetables.models import Route


def capture_committed_rows(service, rows, saved):
    records = {
        kind: {item.id: item for item in service.query(model).all()}
        for kind, model in MODELS.items()
    }
    routes = {item.id: item for item in service.query(Route).all()}

    def code(kind, identifier):
        return records[kind][identifier].code if identifier is not None else None

    for row in rows:
        target = saved[ref_key(row.plan["ref"])]
        values = {
            column.key: getattr(target, column.key)
            for column in SHEETS[row.entity][2]
            if hasattr(target, column.key)
        }
        if row.entity in ("drivers", "vehicles", "pairings"):
            values["home_station"] = code("stations", target.home_station_id)
        if row.entity == "timetable":
            route = routes[target.route_id]
            values.update(
                origin=code("stations", route.origin_station_id),
                destination=code("stations", route.destination_station_id),
                distance_km=route.distance_km,
            )
        elif row.entity == "pairings":
            values.update(
                driver_ref=code("drivers", target.driver_id),
                vehicle_ref=code("vehicles", target.vehicle_id),
            )
        elif row.entity == "connections":
            values.update(incoming_ref=records['timetable'][target.incoming_template_id].trip_code,
                          outgoing_ref=records['timetable'][target.outgoing_template_id].trip_code)
        elif row.entity == "transfers":
            values.update(
                origin=code("stations", target.origin_station_id),
                destination=code("stations", target.destination_station_id),
            )
        row.plan = {**row.plan, "after_export": json_ready(values)}
