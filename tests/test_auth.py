from app.core.google import GoogleAuthError


def test_google_login_success(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.auth.verify_google_id_token",
        lambda token: {"sub": "g-1", "email": "u@x.com", "name": "U", "picture": "p"},
    )
    response = client.post("/auth/google", json={"id_token": "fake"})
    assert response.status_code == 200
    assert response.json()["email"] == "u@x.com"
    assert "az_session" in response.cookies


def test_google_login_existing_user_updates(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.auth.verify_google_id_token",
        lambda token: {"sub": "g-2", "email": "e@x.com", "name": "E"},
    )
    client.post("/auth/google", json={"id_token": "x"})  # creates
    response = client.post("/auth/google", json={"id_token": "x"})  # updates existing
    assert response.status_code == 200


def test_google_login_invalid_token(client, monkeypatch):
    def _raise(token):
        raise GoogleAuthError("bad token")

    monkeypatch.setattr("app.routers.auth.verify_google_id_token", _raise)
    assert client.post("/auth/google", json={"id_token": "fake"}).status_code == 401


def test_google_login_missing_email(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.verify_google_id_token", lambda token: {"sub": "g-1"})
    assert client.post("/auth/google", json={"id_token": "fake"}).status_code == 401


def test_logout(client):
    response = client.post("/auth/logout")
    assert response.status_code == 200
    assert response.json()["status"] == "logged_out"
