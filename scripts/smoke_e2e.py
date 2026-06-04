"""Full end-to-end smoke against the REAL configured Postgres + Swift (reads .env).

Creates a user, project, generates web-3tier (render -> lint -> zip -> Swift), downloads
it back, then cleans up all rows + the Swift artifact.

Usage:
    .venv/Scripts/python scripts/smoke_e2e.py
"""

from fastapi.testclient import TestClient

from app.config import get_settings
from app.core.security import create_access_token
from app.db import SessionLocal, init_db
from app.main import create_app
from app.models import Generation, Project, User
from app.services import swift_storage

CONFIG = {
    "project_name": "e2e",
    "aws_region": "ap-south-1",
    "vpc_cidr": "10.20.0.0/16",
    "office_ip": "203.0.113.10/32",
}

init_db()
client = TestClient(create_app())
session = SessionLocal()

# fresh test user + auth cookie
session.query(User).filter_by(google_sub="e2e").delete()
session.commit()
user = User(google_sub="e2e", email="e2e@x.com", name="E2E")
session.add(user)
session.commit()
client.cookies.set("az_session", create_access_token("e2e", {"email": "e2e@x.com"}))

pid = None
artifact_key = None
try:
    created = client.post("/projects", json={"name": "E2E", "template_slug": "web-3tier", "config": CONFIG})
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    print(f"1. project created id={pid}  (Postgres)")

    generated = client.post(f"/projects/{pid}/generate", json={"env": "uat"})
    assert generated.status_code == 200, generated.text
    artifact_key = generated.json()["artifact_key"]
    print(f"2. generated  lint={generated.json()['lint_status']}  artifact={artifact_key}  (Swift)")

    downloaded = client.get(f"/projects/{pid}/download", params={"env": "uat"})
    assert downloaded.status_code == 200 and downloaded.content[:2] == b"PK", "download failed"
    print(f"3. downloaded zip bytes={len(downloaded.content)}  (from Swift)")
    print("E2E OK — Postgres + Swift + generator working end-to-end")
finally:
    if artifact_key:
        try:
            swift_storage._connection().object_store.delete_object(
                artifact_key, container=get_settings().swift_container
            )
        except Exception as exc:  # noqa: BLE001
            print("cleanup swift warn:", exc)
    if pid is not None:
        session.query(Generation).filter_by(project_id=pid).delete()
        session.query(Project).filter_by(id=pid).delete()
    session.query(User).filter_by(google_sub="e2e").delete()
    session.commit()
    session.close()
    print("cleaned up test rows + artifact")
