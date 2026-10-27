"""Tests must not export fixtures, credentials or expected failures to an external error reporter."""
import os

# This is test-process configuration only; preserve the application's deployment settings.
os.environ['SENTRY_DSN']=''
