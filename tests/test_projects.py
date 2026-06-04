def test_create_requires_auth(client):
    response = client.post("/projects", json={"name": "p", "template_slug": "web-3tier"})
    assert response.status_code == 401


def test_create_unknown_template(auth_client):
    response = auth_client.post("/projects", json={"name": "p", "template_slug": "nope"})
    assert response.status_code == 400


def test_project_crud(auth_client):
    created = auth_client.post(
        "/projects",
        json={"name": "My App", "template_slug": "web-3tier", "config": {"project_name": "x"}},
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    listing = auth_client.get("/projects")
    assert listing.status_code == 200
    assert listing.json()[0]["id"] == project_id

    fetched = auth_client.get(f"/projects/{project_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "My App"

    assert auth_client.get("/projects/99999").status_code == 404
