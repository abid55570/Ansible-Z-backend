import os

# Force hermetic settings BEFORE importing the app, so a local .env (real Postgres /
# Swift creds) never leaks into the test run. os.environ overrides .env in pydantic-settings.
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["STORAGE_PROVIDER"] = "s3"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.security import create_access_token  # noqa: E402
from app.db import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import User  # noqa: E402


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = testing_session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    app = create_app()

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


@pytest.fixture
def auth_client(client, db_session):
    user = User(google_sub="g-test", email="t@x.com", name="Tester")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    client.cookies.set("az_session", create_access_token("g-test", {"email": "t@x.com"}))
    return client


@pytest.fixture
def fake_storage(monkeypatch):
    """In-memory stand-in for S3 so generate/download tests need no MinIO."""
    store: dict[str, bytes] = {}
    monkeypatch.setattr("app.services.storage.ensure_bucket", lambda: None)
    monkeypatch.setattr(
        "app.services.storage.put_object",
        lambda key, data, content_type="application/zip": store.__setitem__(key, data),
    )
    monkeypatch.setattr("app.services.storage.get_object", lambda key: store[key])
    return store
