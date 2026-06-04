import pytest

from app.ir.compiler import IRError, _topo_sort, compile_ir, validate
from app.services.linter import lint_files

SAMPLE_IR = {
    "version": 1,
    "provider": "aws",
    "region": "ap-south-1",
    "name": "demo",
    "nodes": [
        {"id": "vpc1", "type": "vpc", "props": {"cidr": "10.0.0.0/16"}},
        {"id": "pub1", "type": "subnet", "props": {"cidr": "10.0.1.0/24", "public": True, "az": "ap-south-1a"}, "inputs": {"vpc": "vpc1"}},
        {"id": "pub2", "type": "subnet", "props": {"cidr": "10.0.2.0/24", "public": True, "az": "ap-south-1b"}, "inputs": {"vpc": "vpc1"}},
        {"id": "sg1", "type": "security_group", "props": {"ssh_cidr": "203.0.113.10/32", "allow_http": True, "allow_https": True}, "inputs": {"vpc": "vpc1"}},
        {"id": "web", "type": "ec2_instance", "props": {"instance_type": "t3.micro"}, "inputs": {"subnet": "pub1", "security_group": "sg1"}},
        {"id": "alb1", "type": "alb", "props": {}, "inputs": {"subnets": ["pub1", "pub2"], "security_group": "sg1"}},
        {"id": "db1", "type": "rds", "props": {}, "inputs": {"subnets": ["pub1", "pub2"]}},
    ],
}


def test_compile_valid_ir_produces_valid_yaml():
    files = compile_ir(SAMPLE_IR)
    assert "site.yml" in files and "group_vars/all.yml" in files
    report = lint_files(files)
    assert report["status"] == "passed", report["errors"]


def test_compile_wires_references_and_orders_dependencies():
    site = compile_ir(SAMPLE_IR)["site.yml"]
    assert site.index("Create VPC: vpc1") < site.index("Create subnet: pub1")
    assert "{{ vpc1_result.vpc.id }}" in site
    assert "{{ pub1_result.subnet.id }}" in site
    # rds expands to two tasks
    assert "DB subnet group: db1" in site and "Create RDS: db1" in site


def test_strip_none_omits_unset_optionals():
    ir = {
        "region": "x",
        "name": "n",
        "nodes": [
            {"id": "v", "type": "vpc", "props": {"cidr": "10.0.0.0/16"}},
            {"id": "s", "type": "subnet", "props": {"cidr": "10.0.1.0/24"}, "inputs": {"vpc": "v"}},
        ],
    }
    assert "az:" not in compile_ir(ir)["site.yml"]


def test_topo_sort_detects_cycle():
    with pytest.raises(IRError):
        _topo_sort([{"id": "a", "inputs": {"x": "b"}}, {"id": "b", "inputs": {"x": "a"}}])


@pytest.mark.parametrize(
    "bad_ir",
    [
        [],  # not a dict
        {"name": "n", "nodes": [{"id": "v", "type": "vpc", "props": {"cidr": "x"}}]},  # missing region
        {"region": "r", "name": "n", "nodes": []},  # empty nodes
        {"region": "r", "name": "n", "nodes": [{"type": "vpc", "props": {"cidr": "x"}}]},  # node missing id
        {"region": "r", "name": "n", "nodes": [{"id": "x", "type": "bogus", "props": {}}]},  # unknown type
        {"region": "r", "name": "n", "nodes": [{"id": "v", "type": "vpc", "props": {}}]},  # missing required prop
        {"region": "r", "name": "n", "nodes": [{"id": "s", "type": "subnet", "props": {"cidr": "x"}}]},  # missing input
        {"region": "r", "name": "n", "nodes": [{"id": "s", "type": "subnet", "props": {"cidr": "x"}, "inputs": {"vpc": "ghost"}}]},  # bad ref
        {"region": "r", "name": "n", "nodes": [
            {"id": "v", "type": "vpc", "props": {"cidr": "x"}},
            {"id": "v", "type": "vpc", "props": {"cidr": "y"}},
        ]},  # duplicate ids
        {"region": "r", "name": "n", "nodes": [
            {"id": "v", "type": "vpc", "props": {"cidr": "x"}},
            {"id": "s", "type": "subnet", "props": {"cidr": "y"}, "inputs": {"vpc": "v"}},
            {"id": "bad", "type": "subnet", "props": {"cidr": "z"}, "inputs": {"vpc": "s"}},  # vpc input -> a subnet
        ]},  # type mismatch
    ],
)
def test_validate_rejects_bad_graphs(bad_ir):
    with pytest.raises(IRError):
        validate(bad_ir)


def test_irerror_carries_messages():
    try:
        validate({"region": "r", "name": "n", "nodes": []})
    except IRError as exc:
        assert isinstance(exc.errors, list) and exc.errors


ALL_BLOCKS_IR = {
    "version": 1,
    "provider": "aws",
    "region": "ap-south-1",
    "name": "all-blocks",
    "nodes": [
        {"id": "vpc", "type": "vpc", "props": {"cidr": "10.0.0.0/16"}},
        {"id": "pub", "type": "subnet", "props": {"cidr": "10.0.1.0/24"}, "inputs": {"vpc": "vpc"}},
        {"id": "igw", "type": "igw", "props": {}, "inputs": {"vpc": "vpc"}},
        {"id": "nat", "type": "nat_gateway", "props": {}, "inputs": {"subnet": "pub"}},
        {"id": "rt", "type": "route_table", "props": {}, "inputs": {"vpc": "vpc", "subnets": ["pub"]}},
        {"id": "bucket", "type": "s3_bucket", "props": {"bucket_name": "my-bucket", "versioning": True}},
        {"id": "site", "type": "s3_website", "props": {}, "inputs": {"bucket": "bucket"}},
        {"id": "tg", "type": "target_group", "props": {}, "inputs": {"vpc": "vpc"}},
        {"id": "lt", "type": "launch_template", "props": {}},
        {"id": "fn", "type": "lambda", "props": {}},
        {"id": "ddb", "type": "dynamodb", "props": {}},
        {"id": "key", "type": "kms_key", "props": {}},
        {"id": "role", "type": "iam_role", "props": {}},
        {"id": "eks", "type": "eks_cluster", "props": {}, "inputs": {"subnets": ["pub"]}},
        {"id": "ng", "type": "eks_nodegroup", "props": {}, "inputs": {"subnets": ["pub"]}},
        {"id": "tgw", "type": "transit_gateway", "props": {}},
        {"id": "vgw", "type": "vpn_gateway", "props": {}, "inputs": {"vpc": "vpc"}},
        {"id": "trail", "type": "cloudtrail", "props": {}},
        {"id": "api", "type": "api_gateway", "props": {}},
        {"id": "events", "type": "eventbridge", "props": {}},
        {"id": "ep", "type": "vpc_endpoint", "props": {}, "inputs": {"vpc": "vpc"}},
    ],
}


def test_all_blocks_compile_to_valid_yaml():
    files = compile_ir(ALL_BLOCKS_IR)
    report = lint_files(files)
    assert report["status"] == "passed", report["errors"]
    site = files["site.yml"]
    for marker in ("Internet gateway", "NAT gateway", "Route table", "S3 bucket", "S3 website", "Target group",
                   "Launch template", "Lambda function", "DynamoDB table", "KMS key", "IAM role",
                   "EKS cluster", "EKS node group", "Transit gateway", "VPN gateway", "CloudTrail",
                   "API gateway", "EventBridge rule", "VPC endpoint"):
        assert marker in site
