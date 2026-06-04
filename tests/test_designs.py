def test_list_blocks(client):
    response = client.get("/designs/blocks")
    assert response.status_code == 200
    body = response.json()
    assert "vpc" in body and "ec2_instance" in body and "alb" in body
    assert "output" in body["vpc"]


def test_validate_design_valid(auth_client):
    ir = {"region": "ap-south-1", "name": "n", "nodes": [{"id": "v", "type": "vpc", "props": {"cidr": "10.0.0.0/16"}}]}
    response = auth_client.post("/designs/validate", json=ir)
    assert response.status_code == 200
    assert response.json() == {"valid": True, "errors": []}


def test_validate_design_invalid(auth_client):
    response = auth_client.post("/designs/validate", json={"region": "r", "name": "n", "nodes": []})
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["errors"]


def test_validate_design_requires_auth(client):
    response = client.post("/designs/validate", json={"region": "r", "name": "n", "nodes": []})
    assert response.status_code == 401
