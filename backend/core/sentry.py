"""Privacy-minimal error diagnostics for a platform holding staff records."""

import sentry_sdk
from config import settings


def sanitize_event(event, hint):
    # Allowlists also protect new integrations: SQL parameters, upload cells,
    # URL tokens, cookies, breadcrumbs and stack locals are never forwarded.
    clean = {
        key: event[key]
        for key in ("event_id", "timestamp", "level", "platform")
        if key in event
    }
    values = []
    for error in event.get("exception", {}).get("values", []):
        value = {"type": error.get("type", "Error")}
        frames = error.get("stacktrace", {}).get("frames", [])
        if frames:
            value["stacktrace"] = {
                "frames": [
                    {
                        key: frame[key]
                        for key in (
                            "filename",
                            "function",
                            "lineno",
                            "module",
                            "in_app",
                        )
                        if key in frame
                    }
                    for frame in frames
                ]
            }
        values.append(value)
    if values:
        clean["exception"] = {"values": values}
    return clean


def drop_transaction(event, hint):
    return None


def init_sentry():
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            send_default_pii=False,
            include_local_variables=False,
            max_request_body_size="never",
            traces_sample_rate=0,
            profiles_sample_rate=0,
            before_send=sanitize_event,
            before_send_transaction=drop_transaction,
        )
