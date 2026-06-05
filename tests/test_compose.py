import yaml

from app.ir.targets import compile_target
from app.ir.targets.compose import compile_compose

C_IR = {
    "version": 1, "provider": "aws", "region": "ap-south-1", "name": "stack",
    "nodes": [
        {"id": "vpc", "type": "vpc", "props": {"cidr": "10.0.0.0/16"}},
        {"id": "pub", "type": "subnet", "props": {"cidr": "10.0.1.0/24"}, "inputs": {"vpc": "vpc"}},
        {"id": "ecs", "type": "ecs_cluster", "props": {}},
        {"id": "svc", "type": "ecs_service", "props": {"image": "myapp:1.2", "container_port": 8080, "desired_count": 3}, "inputs": {"cluster": "ecs", "subnets": ["pub"]}},
        {"id": "pg", "type": "rds", "props": {"engine": "postgres", "username": "app"}, "inputs": {"subnets": ["pub"]}},
        {"id": "my", "type": "rds", "props": {"engine": "mysql"}, "inputs": {"subnets": ["pub"]}},
        {"id": "logs", "type": "s3_bucket", "props": {}},
        {"id": "igw", "type": "igw", "props": {}, "inputs": {"vpc": "vpc"}},  # infra -> unmapped
    ],
}


def test_compile_compose_container_subset():
    files = compile_compose(C_IR)
    assert {"compose.yaml", ".env", "README.md"} <= set(files)
    doc = yaml.safe_load(files["compose.yaml"])
    svcs = doc["services"]
    assert svcs["svc"]["image"] == "myapp:1.2"
    assert svcs["svc"]["ports"] == ["8080:8080"]
    assert svcs["svc"]["deploy"]["replicas"] == 3
    assert svcs["pg"]["image"] == "postgres:16"
    assert svcs["pg"]["environment"]["POSTGRES_DB"] == "pg"
    assert svcs["my"]["image"] == "mysql:8"
    assert "MYSQL_ROOT_PASSWORD" in svcs["my"]["environment"]
    assert svcs["logs"]["image"] == "minio/minio"
    assert "pg-data" in doc["volumes"]
    assert "igw" in files["README.md"]  # infra surfaced as provisioned-elsewhere


def test_compose_single_replica_empty_and_no_unmapped():
    # single replica -> no deploy block
    ir1 = {"region": "r", "name": "n", "nodes": [
        {"id": "vpc", "type": "vpc", "props": {"cidr": "10.0.0.0/16"}},
        {"id": "pub", "type": "subnet", "props": {"cidr": "10.0.1.0/24"}, "inputs": {"vpc": "vpc"}},
        {"id": "ecs", "type": "ecs_cluster", "props": {}},
        {"id": "s", "type": "ecs_service", "props": {"desired_count": 1}, "inputs": {"cluster": "ecs", "subnets": ["pub"]}},
    ]}
    assert "deploy" not in yaml.safe_load(compile_compose(ir1)["compose.yaml"])["services"]["s"]

    # no container blocks -> empty compose + provisioned-elsewhere note
    empty = compile_compose({"region": "r", "name": "n", "nodes": [{"id": "vpc", "type": "vpc", "props": {"cidr": "10.0.0.0/16"}}]})
    assert "No container workloads" in empty["compose.yaml"]
    assert "vpc" in empty["README.md"]

    # only mapped blocks -> no provisioned-elsewhere section
    s3only = compile_compose({"region": "r", "name": "n", "nodes": [{"id": "b", "type": "s3_bucket", "props": {}}]})
    assert "Provisioned elsewhere" not in s3only["README.md"]


def test_compile_target_dispatches_compose():
    assert "compose.yaml" in compile_target(C_IR, "compose")
