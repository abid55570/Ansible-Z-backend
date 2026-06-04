from fastapi.testclient import TestClient

from app.db import get_db, init_db
from app.main import create_app


def test_get_db_yields_and_closes():
    generator = get_db()
    session = next(generator)
    assert session is not None
    generator.close()


def test_init_db_is_idempotent():
    init_db()
    init_db()


def test_lifespan_triggers_init_db():
    # Using TestClient as a context manager runs the lifespan (init_db).
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
