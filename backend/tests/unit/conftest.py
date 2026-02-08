"""Minimal conftest for unit tests - no database, no app dependencies."""

import os

# Set required env vars before any app imports
os.environ.setdefault("SECRET_KEY", "testsecretkey_for_unit_tests_only_1234567890")
os.environ.setdefault("FERNET_KEY", "dGVzdGZlcm5ldGtleTEyMzQ1Njc4OTAxMjM0NTY3OA==")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
