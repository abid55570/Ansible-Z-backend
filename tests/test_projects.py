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


def test_update_project(auth_client):
    created = auth_client.post(
        "/projects",
        json={"name": "Design", "template_slug": "__custom__", "config": {"version": 1, "nodes": []}},
    )
    project_id = created.json()["id"]

    updated = auth_client.put(
        f"/projects/{project_id}",
        json={"name": "Design v2", "config": {"version": 1, "nodes": [{"id": "vpc1"}]}},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Design v2"
    assert updated.json()["config"]["nodes"] == [{"id": "vpc1"}]

    # change is persisted
    fetched = auth_client.get(f"/projects/{project_id}")
    assert fetched.json()["name"] == "Design v2"
    assert fetched.json()["config"]["nodes"] == [{"id": "vpc1"}]


def test_update_requires_auth(client):
    assert client.put("/projects/1", json={"name": "x", "config": {}}).status_code == 401


def test_update_unknown_project(auth_client):
    assert auth_client.put("/projects/99999", json={"name": "x", "config": {}}).status_code == 404
