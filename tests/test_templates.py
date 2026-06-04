def test_list_templates(client):
    response = client.get("/templates")
    assert response.status_code == 200
    data = response.json()
    slugs = {t["slug"] for t in data}
    assert "web-3tier" in slugs
    assert len(data) >= 11

    web = next(t for t in data if t["slug"] == "web-3tier")
    assert web["ready"] is True
    # all 11 templates are now generatable
    assert all(t["ready"] for t in data)


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
