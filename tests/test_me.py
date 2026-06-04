from app.core.security import create_access_token


def test_me_authenticated(auth_client):
    response = auth_client.get("/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == "t@x.com"


def test_me_no_cookie(client):
    assert client.get("/auth/me").status_code == 401


def test_me_bad_cookie(client):
    client.cookies.set("az_session", "garbage")
    assert client.get("/auth/me").status_code == 401


def test_me_user_not_found(client):
    client.cookies.set("az_session", create_access_token("ghost-sub", {"email": "g@x.com"}))
    assert client.get("/auth/me").status_code == 401
