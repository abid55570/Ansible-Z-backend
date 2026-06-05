def test_list_templates(client):
    response = client.get("/templates")
    assert response.status_code == 200
    data = response.json()
    slugs = {t["slug"] for t in data}
    assert "web-3tier" in slugs
    assert len(data) >= 11

    web = next(t for t in data if t["slug"] == "web-3tier")
    assert web["ready"] is True
    # all templates are now generatable
    assert all(t["ready"] for t in data)

    # starter-tier templates are flagged; enterprise is the default
    tier = {t["slug"]: t["tier"] for t in data}
    assert tier["single-vm-app"] == "starter"
    assert tier["web-3tier"] == "enterprise"


def test_template_detail(client):
    response = client.get("/templates/web-3tier")
    assert response.status_code == 200
    body = response.json()
    assert "project_name" in body["variables"]
    assert body["roles"]
    # ready templates ship a single-view diagram
    assert body["diagram"]["nodes"] and body["diagram"]["edges"]


def test_every_template_has_a_diagram(client):
    for summary in client.get("/templates").json():
        detail = client.get(f"/templates/{summary['slug']}").json()
        assert detail["diagram"] and detail["diagram"]["nodes"], f"{summary['slug']} has no diagram"


def test_template_detail_unknown(client):
    assert client.get("/templates/does-not-exist").status_code == 404


def test_template_diagram_image(client):
    res = client.get("/templates/web-3tier/diagram.png")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic


def test_template_diagram_image_unknown(client):
    assert client.get("/templates/does-not-exist/diagram.png").status_code == 404
