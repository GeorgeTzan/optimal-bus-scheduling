"""Explicit local reference tooling; never a source for normal customer operations."""

from fastapi import Depends, HTTPException
from api.deps import get_current_user
from config import settings


def reference_tools_available():
    return settings.ENVIRONMENT != "production" and settings.REFERENCE_TOOLS_ENABLED


def ensure_reference_tools_enabled():
    if not reference_tools_available():
        raise HTTPException(404, "Reference tools are disabled.")


def assert_reference_operator(user):
    if getattr(user, "role", None) != "admin":
        raise HTTPException(
            403, "Reference tools require an organization administrator."
        )


def require_reference_tools(
    _enabled=Depends(ensure_reference_tools_enabled), user=Depends(get_current_user)
):
    assert_reference_operator(user)
    return user


def assert_snapshot_writable(source_data, user):
    if source_data.get("source") == "operational":
        return
    if not reference_tools_available():
        raise HTTPException(
            409,
            {
                "code": "archive_read_only",
                "message": "This reference archive is read-only. Create a draft from your own service day.",
            },
        )
    assert_reference_operator(user)
