import yaml

from app.ir.targets import compile_target
from app.ir.targets.kubernetes import _readme, compile_kubernetes

K_IR = {
    "version": 1, "provider": "aws", "region": "ap-south-1", "name": "stack",
    "nodes": [
        {"id": "vpc", "type": "vpc", "props": {"cidr": "10.0.0.0/16"}},
        {"id": "pub", "type": "subnet", "props": {"cidr": "10.0.1.0/24"}, "inputs": {"vpc": "vpc"}},
        {"id": "ecs", "type": "ecs_cluster", "props": {}},
        {"id": "svc", "type": "ecs_service", "props": {"image": "myapp:1.2", "container_port": 8080, "desired_count": 3}, "inputs": {"cluster": "ecs", "subnets": ["pub"]}},
        {"id": "pg", "type": "rds", "props": {"engine": "postgres", "username": "app"}, "inputs": {"subnets": ["pub"]}},
        {"id": "my", "type": "rds", "props": {"engine": "mysql"}, "inputs": {"subnets": ["pub"]}},
        {"id": "logs", "type": "s3_bucket", "props": {}},  # not a K8s object -> unmapped
    ],
}


def _docs(text):
    return [d for d in yaml.safe_load_all(text) if d]


def test_compile_kubernetes_container_subset():
    files = compile_kubernetes(K_IR)
    docs = _docs(files["manifests.yaml"])
    kinds = {(d["kind"], d["metadata"]["name"]) for d in docs}
    assert ("Deployment", "svc") in kinds and ("Service", "svc") in kinds
    svc_dep = next(d for d in docs if d["kind"] == "Deployment" and d["metadata"]["name"] == "svc")
    assert svc_dep["spec"]["replicas"] == 3
    container = svc_dep["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == "myapp:1.2" and "env" not in container  # ecs service has no env block
    pg = next(d for d in docs if d["kind"] == "Deployment" and d["metadata"]["name"] == "pg")
    assert any(e["name"] == "POSTGRES_DB" for e in pg["spec"]["template"]["spec"]["containers"][0]["env"])
    my = next(d for d in docs if d["kind"] == "Deployment" and d["metadata"]["name"] == "my")
    assert any(e["name"] == "MYSQL_DATABASE" for e in my["spec"]["template"]["spec"]["containers"][0]["env"])
    assert "s3_bucket" in files["README.md"]  # s3 (a non-K8s object) surfaced as unmapped


def test_kubernetes_empty_and_readme_no_unmapped():
    empty = compile_kubernetes({"region": "r", "name": "n", "nodes": [{"id": "vpc", "type": "vpc", "props": {"cidr": "10.0.0.0/16"}}]})
    assert "No container workloads" in empty["manifests.yaml"]
    assert "Provisioned elsewhere" in empty["README.md"]
    # a fully-mapped design is impossible (services need infra inputs), so cover the no-unmapped branch directly
    assert "Provisioned elsewhere" not in _readme({"name": "n", "region": "r"}, [])


def test_compile_target_dispatches_kubernetes():
    assert "manifests.yaml" in compile_target(K_IR, "kubernetes")
