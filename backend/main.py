from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from core.sentry import init_sentry
from api import auth, trips, drivers, solver as solver_api
from dat_parser import get_full_data
from db.database import engine, Base
from db import models

init_sentry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    print("Database initialized")
    yield


app = FastAPI(title="Optimal Scheduling System API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(trips.router)
app.include_router(drivers.router)
app.include_router(solver_api.router)


@app.get("/")
async def root():
    return {"message": "Optimal Scheduling System API"}


@app.get("/data")
async def get_data():
    data = get_full_data()
    return data


@app.get("/schedule")
async def get_schedule():
    return {"schedule": []}


@app.get("/sentry-debug")
async def trigger_error():
    division_by_zero = 1 / 0
