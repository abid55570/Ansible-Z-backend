"""Smoke test the configured database (reads .env). Creates tables, inserts, reads, cleans up.

Usage:
    .venv/Scripts/python scripts/smoke_db.py
"""

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.models import User

settings = get_settings()
print("DB host:", settings.database_url.split("@")[-1])  # never print the password

print("1. init_db (create tables if missing) ...")
init_db()

print("2. insert + read + delete a test user ...")
session = SessionLocal()
try:
    session.query(User).filter_by(google_sub="db-smoke").delete()
    session.commit()

    user = User(google_sub="db-smoke", email="dbsmoke@x.com", name="DB Smoke")
    session.add(user)
    session.commit()
    print(f"   inserted user id={user.id}")

    fetched = session.query(User).filter_by(google_sub="db-smoke").first()
    assert fetched is not None and fetched.email == "dbsmoke@x.com"

    session.delete(fetched)
    session.commit()
finally:
    session.close()

print("DB SMOKE OK — connected, schema created, round-trip verified")
