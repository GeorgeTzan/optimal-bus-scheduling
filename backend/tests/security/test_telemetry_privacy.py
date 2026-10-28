"""Operational records and credentials must never become telemetry payloads."""

from unittest.mock import patch
from core import sentry


def test_error_telemetry_keeps_only_diagnostic_structure():
    private = "PRIVATE-driver-phone-and-upload-cell"
    event = {
        "event_id": "abc",
        "level": "error",
        "platform": "python",
        "request": {
            "url": "https://app/reset/" + private,
            "data": private,
            "cookies": private,
            "headers": {"Authorization": private},
        },
        "user": {"email": private},
        "extra": {"upload": private},
        "breadcrumbs": {"values": [{"message": private}]},
        "message": private,
        "logentry": {"message": private},
        "exception": {
            "values": [
                {
                    "type": "IntegrityError",
                    "value": private,
                    "stacktrace": {
                        "frames": [
                            {
                                "filename": "service.py",
                                "function": "commit",
                                "lineno": 42,
                                "vars": {"row": private},
                                "pre_context": [private],
                                "context_line": private,
                            }
                        ]
                    },
                }
            ]
        },
    }
    cleaned = sentry.sanitize_event(event, {"exc_info": (None, private, None)})
    assert private not in repr(cleaned)
    exception = cleaned["exception"]["values"][0]
    assert exception["type"] == "IntegrityError"
    assert exception["stacktrace"]["frames"][0] == {
        "filename": "service.py",
        "function": "commit",
        "lineno": 42,
    }
    assert cleaned["event_id"] == "abc"


def test_sdk_disables_personal_context_and_performance_payloads(monkeypatch):
    monkeypatch.setattr(
        sentry.settings, "SENTRY_DSN", "https://public@example.invalid/1"
    )
    with patch.object(sentry.sentry_sdk, "init") as initialize:
        sentry.init_sentry()
    options = initialize.call_args.kwargs
    assert options["send_default_pii"] is False
    assert options["include_local_variables"] is False
    assert options["max_request_body_size"] == "never"
    assert options["traces_sample_rate"] == 0
    assert options["profiles_sample_rate"] == 0
    assert options["before_send"] is sentry.sanitize_event
    assert options["before_send_transaction"]({}, {}) is None
