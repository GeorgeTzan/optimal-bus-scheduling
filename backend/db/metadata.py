"""Explicit model registry shared by migrations, runtime checks and tests."""
from importlib import import_module
from db.database import Base


def load_domain_metadata():
    for name in (
        'db.models', 'app.domain.identity.models', 'app.domain.workforce.models', 'app.domain.fleet.models',
        'app.domain.timetables.models', 'app.domain.imports.models', 'app.domain.jobs.models',
        'app.domain.scheduling.models', 'app.domain.scheduling.snapshots', 'app.domain.scheduling.change_models',
        'app.domain.incidents.models', 'app.domain.incidents.operations_models', 'app.domain.events.outbox', 'app.domain.office.models', 'app.domain.identity.driver_models',
    ):
        import_module(name)
    return Base.metadata
