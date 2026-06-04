"""Smoke test the configured object storage (reads .env).

Usage:
    .venv/Scripts/python scripts/smoke_swift.py
"""

from app.config import get_settings
from app.services import storage

settings = get_settings()
print(f"provider={settings.storage_provider} region={settings.os_region} container={settings.swift_container}")

key = "ansible-z-smoke.txt"
payload = b"hello from ansible-z smoke"

print("1. ensure_bucket / container ...")
storage.ensure_bucket()

print("2. put_object ...")
storage.put_object(key, payload, content_type="text/plain")

print("3. get_object ...")
fetched = storage.get_object(key)
assert fetched == payload, f"round-trip mismatch: {fetched!r}"

print(f"SMOKE OK — {len(fetched)} bytes round-tripped through {settings.storage_provider}")
