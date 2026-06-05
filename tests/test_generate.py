from app.config import get_settings

WEB3_CONFIG = {
    "project_name": "acme-web",
    "aws_region": "ap-south-1",
    "vpc_cidr": "10.20.0.0/16",
    "office_ip": "203.0.113.10/32",
}


CUSTOM_IR = {
    "version": 1,
    "provider": "aws",
    "region": "ap-south-1",
    "name": "my-design",
    "nodes": [
        {"id": "vpc1", "type": "vpc", "props": {"cidr": "10.0.0.0/16"}},
        {"id": "pub1", "type": "subnet", "props": {"cidr": "10.0.1.0/24", "public": True}, "inputs": {"vpc": "vpc1"}},
        {"id": "sg1", "type": "security_group", "props": {"ingress": [{"port": 80}]}, "inputs": {"vpc": "vpc1"}},
        {"id": "web", "type": "ec2_instance", "props": {}, "inputs": {"subnet": "pub1", "security_group": "sg1"}},
    ],
}


def _make_project(auth_client, slug="web-3tier", config=None):
    response = auth_client.post(
        "/projects",
        json={"name": "p", "template_slug": slug, "config": config or WEB3_CONFIG},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_generate_and_download(auth_client, fake_storage):
    project_id = _make_project(auth_client)

    generated = auth_client.post(f"/projects/{project_id}/generate", json={"env": "uat"})
    assert generated.status_code == 200, generated.text
    assert generated.json()["lint_status"] == "passed"

    downloaded = auth_client.get(f"/projects/{project_id}/download", params={"env": "uat"})
    assert downloaded.status_code == 200
    assert downloaded.content[:2] == b"PK"  # zip magic number


def test_generate_template_not_ready(auth_client, fake_storage, monkeypatch):
    # All catalogue templates are generatable now, so simulate a not-yet-ready one.
    monkeypatch.setattr("app.routers.projects.template_is_ready", lambda slug: False)
    project_id = _make_project(auth_client)
    assert auth_client.post(f"/projects/{project_id}/generate", json={"env": "uat"}).status_code == 409


def test_generate_missing_required_var(auth_client, fake_storage):
    project_id = _make_project(
        auth_client,
        config={"project_name": "x", "aws_region": "ap-south-1", "vpc_cidr": "10.0.0.0/16"},
    )
    # office_ip is required for uat -> 400
    assert auth_client.post(f"/projects/{project_id}/generate", json={"env": "uat"}).status_code == 400


def test_generate_lint_failure(auth_client, fake_storage, monkeypatch):
    monkeypatch.setattr(
        "app.services.linter.lint_files",
        lambda files: {"status": "failed", "errors": [{"file": "x.yml", "error": "broken"}]},
    )
    project_id = _make_project(auth_client)
    assert auth_client.post(f"/projects/{project_id}/generate", json={"env": "uat"}).status_code == 422


def test_download_without_generation(auth_client):
    project_id = _make_project(auth_client)
    assert auth_client.get(f"/projects/{project_id}/download", params={"env": "uat"}).status_code == 404


def test_generate_deep_lint_pass(auth_client, fake_storage, monkeypatch):
    monkeypatch.setattr(get_settings(), "deep_lint", True)
    monkeypatch.setattr(
        "app.services.ansible_check.syntax_check",
        lambda files, playbook="site.yml": {"status": "passed"},
    )
    project_id = _make_project(auth_client)
    assert auth_client.post(f"/projects/{project_id}/generate", json={"env": "uat"}).status_code == 200


def test_generate_deep_lint_failure(auth_client, fake_storage, monkeypatch):
    monkeypatch.setattr(get_settings(), "deep_lint", True)
    monkeypatch.setattr(
        "app.services.ansible_check.syntax_check",
        lambda files, playbook="site.yml": {"status": "failed", "output": "boom"},
    )
    project_id = _make_project(auth_client)
    assert auth_client.post(f"/projects/{project_id}/generate", json={"env": "uat"}).status_code == 422


def test_generate_custom_design(auth_client, fake_storage):
    project_id = _make_project(auth_client, slug="__custom__", config=CUSTOM_IR)
    generated = auth_client.post(f"/projects/{project_id}/generate", json={"env": "uat"})
    assert generated.status_code == 200, generated.text

    downloaded = auth_client.get(f"/projects/{project_id}/download", params={"env": "uat"})
    assert downloaded.status_code == 200
    assert downloaded.content[:2] == b"PK"


def test_generate_custom_design_invalid(auth_client, fake_storage):
    project_id = _make_project(auth_client, slug="__custom__", config={"region": "r", "name": "n", "nodes": []})
    assert auth_client.post(f"/projects/{project_id}/generate", json={"env": "uat"}).status_code == 400


def test_generate_custom_terraform(auth_client, fake_storage):
    project_id = _make_project(auth_client, slug="__custom__", config=CUSTOM_IR)
    generated = auth_client.post(f"/projects/{project_id}/generate", json={"env": "uat", "target": "terraform"})
    assert generated.status_code == 200, generated.text
    assert generated.json()["lint_status"] == "skipped"  # ansible lint/syntax-check skipped for TF
    downloaded = auth_client.get(f"/projects/{project_id}/download", params={"env": "uat"})
    assert downloaded.status_code == 200 and downloaded.content[:2] == b"PK"


def test_generate_template_rejects_non_ansible_target(auth_client, fake_storage):
    project_id = _make_project(auth_client)  # a template (web-3tier)
    response = auth_client.post(f"/projects/{project_id}/generate", json={"env": "uat", "target": "terraform"})
    assert response.status_code == 400


def test_generate_unknown_target(auth_client, fake_storage):
    project_id = _make_project(auth_client, slug="__custom__", config=CUSTOM_IR)
    assert auth_client.post(f"/projects/{project_id}/generate", json={"env": "uat", "target": "nope"}).status_code == 400
