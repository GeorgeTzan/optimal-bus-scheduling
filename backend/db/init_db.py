from db.database import engine, Base
from db.models import KTEL, User, Schedule, Trip, Driver, Solution


def init_db():
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully")


if __name__ == "__main__":
    init_db()
