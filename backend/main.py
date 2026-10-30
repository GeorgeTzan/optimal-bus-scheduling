import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from core.sentry import init_sentry
from config import settings
from api import auth, trips, drivers, solver as solver_api
from app.api import optimization, events, scheduling, identity, resources, timetables, imports, operations, schedule_changes, office, driver
from app.domain.identity.reference_tools import require_reference_tools
from dat_parser import get_full_data
from db.database import engine, Base
from db.models import User
import app.domain.workforce.models
import app.domain.fleet.models
import app.domain.timetables.models
import app.domain.jobs.models
import app.domain.scheduling.models
import app.domain.incidents.models

init_sentry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from db.migrations import assert_schema_current
    with engine.connect() as connection:
        assert_schema_current(connection)
        from db.tenant_schema import assert_runtime_role
        assert_runtime_role(connection)
    yield


app = FastAPI(
    title="Optimal Scheduling System API",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
)

# CORS configuration with explicit origins (no wildcard with credentials in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# Global unhandled exception handler to prevent traceback disclosure
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Log internally, return sanitized response to client
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal Server Error"},
    )


app.include_router(auth.router)
app.include_router(trips.router, dependencies=[Depends(require_reference_tools)])
app.include_router(drivers.router, dependencies=[Depends(require_reference_tools)])
app.include_router(solver_api.router, dependencies=[Depends(require_reference_tools)])
app.include_router(optimization.router)
app.include_router(events.router)
app.include_router(scheduling.router)
app.include_router(identity.router)
app.include_router(resources.router)
app.include_router(timetables.router)
app.include_router(imports.router)
app.include_router(operations.router)
app.include_router(schedule_changes.router)
app.include_router(office.router)
app.include_router(driver.router)


@app.get("/")
async def root():
    return {"message": "Optimal Scheduling System API", "version": "2.0.0"}


@app.get("/data")
async def get_data(current_user: User = Depends(require_reference_tools)):
    data = get_full_data()
    return data
