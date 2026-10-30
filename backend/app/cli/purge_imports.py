"""Bounded, tenant-scoped source retention; run using the restricted API role."""

import argparse
from sqlalchemy import text
from db.database import SessionLocal
from app.domain.imports.service import ImportService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", type=int, required=True)
    parser.add_argument("--limit", type=int, choices=range(1, 101), default=100)
    args = parser.parse_args()
    if args.tenant_id < 1:
        parser.error("Choose a positive tenant ID.")
    with SessionLocal() as db:
        role = db.execute(
            text(
                "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user"
            )
        ).scalar_one()
        if role:
            raise RuntimeError("Retention requires a restricted runtime role.")
        count = ImportService(
            db, args.tenant_id, None, {"imports.write"}
        ).purge_expired(limit=args.limit)
        db.commit()
    print(
        f"Purged source payloads from {count} expired batches; saved operational records retained."
    )


if __name__ == "__main__":
    main()
