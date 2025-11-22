from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dat_parser import parse_trips, parse_drivers

app = FastAPI(title="Optimal Scheduling System API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"message": "Optimal Scheduling System API"}


@app.get("/trips")
async def get_trips():
    trips = parse_trips()
    return {"trips": trips}


@app.get("/drivers")
async def get_drivers():
    drivers = parse_drivers()
    return {"drivers": drivers}


@app.get("/schedule")
async def get_schedule():
    return {"schedule": []}
