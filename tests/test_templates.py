def test_list_templates(client):
    response = client.get("/templates")
    assert response.status_code == 200
    data = response.json()
    slugs = {t["slug"] for t in data}
    assert "web-3tier" in slugs
    assert len(data) >= 11

    web = next(t for t in data if t["slug"] == "web-3tier")
    assert web["ready"] is True
    k8s = next(t for t in data if t["slug"] == "k8s-platform")
    assert k8s["ready"] is False


def test_template_detail(client):
    response = client.get("/templates/web-3tier")
    assert response.status_code == 200
    body = response.json()
    assert "project_name" in body["variables"]
    assert body["roles"]
    # ready templates ship a single-view diagram
    assert body["diagram"]["nodes"] and body["diagram"]["edges"]


def test_stub_template_has_no_diagram(client):
    body = client.get("/templates/k8s-platform").json()
    assert body["diagram"] is None


def test_template_detail_unknown(client):
    assert client.get("/templates/does-not-exist").status_code == 404
