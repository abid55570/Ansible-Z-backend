"""Manual smoke test against real Docker Postgres + MinIO.

Usage:
    docker compose up -d
    .venv/Scripts/python scripts/smoke_docker.py
"""

import os

# Point at the docker-compose services BEFORE importing app modules (settings are cached).
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://user:password@localhost:5432/ansiblez")
os.environ.setdefault("S3_ENDPOINT", "http://localhost:9000")
os.environ.setdefault("S3_BUCKET", "ansiblez-artifacts")
os.environ.setdefault("S3_ACCESS_KEY", "minioadmin")
os.environ.setdefault("S3_SECRET_KEY", "minioadmin")

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import User  # noqa: E402
from app.services import packager, storage  # noqa: E402
from app.services.generator import render_project  # noqa: E402

print("1. init_db against Postgres ...")
init_db()
session = SessionLocal()
user = User(google_sub="smoke", email="smoke@x.com", name="Smoke")
session.add(user)
session.commit()
print(f"   inserted user id={user.id}")
session.close()

print("2. render web-3tier + zip ...")
files = render_project(
    "web-3tier",
    {
        "project_name": "smoke",
        "aws_region": "ap-south-1",
        "vpc_cidr": "10.20.0.0/16",
        "office_ip": "203.0.113.10/32",
    },
    env="uat",
)
blob = packager.zip_files(files)
print(f"   project files={len(files)} zip bytes={len(blob)}")

print("3. store + fetch from MinIO ...")
storage.ensure_bucket()
storage.put_object("smoke/uat.zip", blob)
fetched = storage.get_object("smoke/uat.zip")
assert fetched == blob, "round-trip mismatch"

print("SMOKE OK — Postgres + MinIO + generator all working")
