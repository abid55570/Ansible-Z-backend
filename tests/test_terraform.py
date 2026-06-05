import pytest

from app.ir.canonical import to_resources
from app.ir.targets import TargetError, compile_target, list_targets
from app.ir.targets.terraform import compile_terraform

# Exercises every mapped block and both sides of each conditional branch.
TF_IR = {
    "version": 1,
    "provider": "aws",
    "region": "ap-south-1",
    "name": "tf-demo",
    "nodes": [
        {"id": "vpc", "type": "vpc", "props": {"cidr": "10.0.0.0/16"}},
        {"id": "pub", "type": "subnet", "props": {"cidr": "10.0.1.0/24", "public": True, "az": "ap-south-1a"}, "inputs": {"vpc": "vpc"}},
        {"id": "priv", "type": "subnet", "props": {"cidr": "10.0.2.0/24"}, "inputs": {"vpc": "vpc"}},
        {"id": "sg", "type": "security_group", "props": {"ssh_cidr": "1.2.3.4/32", "allow_http": True, "allow_https": True}, "inputs": {"vpc": "vpc"}},
        {"id": "sgbare", "type": "security_group", "props": {}, "inputs": {"vpc": "vpc"}},
        {"id": "web", "type": "ec2_instance", "props": {"instance_type": "t3.small", "ami": "ami-123", "public": True}, "inputs": {"subnet": "pub", "security_group": "sg"}},
        {"id": "web2", "type": "ec2_instance", "props": {}, "inputs": {"subnet": "priv", "security_group": "sgbare"}},
        {"id": "igw", "type": "igw", "props": {}, "inputs": {"vpc": "vpc"}},
        {"id": "nat", "type": "nat_gateway", "props": {}, "inputs": {"subnet": "pub"}},
        {"id": "rt", "type": "route_table", "props": {}, "inputs": {"vpc": "vpc", "subnets": ["pub"]}},
        {"id": "logs", "type": "s3_bucket", "props": {"bucket_name": "demo-logs", "versioning": True}},
        {"id": "assets", "type": "s3_bucket", "props": {"bucket_name": "demo-assets"}},
        {"id": "site", "type": "s3_website", "props": {}, "inputs": {"bucket": "assets"}},
        {"id": "role", "type": "iam_role", "props": {}},
        {"id": "lt", "type": "launch_template", "props": {"ami": "ami-9"}},
        {"id": "lt2", "type": "launch_template", "props": {}},
        {"id": "fn", "type": "lambda", "props": {"role_arn": "arn:aws:iam::0:role/x"}},
        {"id": "fn2", "type": "lambda", "props": {}},
        {"id": "ddb", "type": "dynamodb", "props": {}},
        {"id": "key", "type": "kms_key", "props": {}},
        {"id": "q", "type": "sqs", "props": {}},
        {"id": "t", "type": "sns", "props": {}},
        {"id": "cw", "type": "cloudwatch", "props": {}},
        {"id": "lb", "type": "alb", "props": {}, "inputs": {"subnets": ["pub", "priv"], "security_group": "sg"}},
        {"id": "tg", "type": "target_group", "props": {}, "inputs": {"vpc": "vpc"}},
        {"id": "db", "type": "rds", "props": {}, "inputs": {"subnets": ["pub", "priv"]}},
    ],
}


def test_compile_terraform_emits_provider_variables_and_resources():
    files = compile_terraform(TF_IR)
    assert {"main.tf", "provider.tf", "variables.tf", ".gitignore", "README.md"} <= set(files)
    main = files["main.tf"]
    # resources + Ref / LocalRef / Raw resolution
    assert 'resource "aws_vpc" "vpc" {' in main
    assert "vpc_id = aws_vpc.vpc.id" in main                       # Ref
    assert "allocation_id = aws_eip.nat_eip.id" in main            # LocalRef
    assert "route_table_id = aws_route_table.rt.id" in main        # LocalRef (association)
    assert "assume_role_policy = jsonencode(" in main             # Raw
    assert "ami = var.default_ami" in main                         # Raw var (web2 / lt2 image_id)
    assert 'ami = "ami-123"' in main                               # literal (web)
    assert "subnets = [aws_subnet.pub.id, aws_subnet.priv.id]" in main  # list of Ref
    # nested + repeated blocks
    assert "ingress {" in main and "egress {" in main
    assert "health_check {" in main and "attribute {" in main
    assert "versioning_configuration {" in main
    assert 'name = "alias/key"' in main                            # kms alias
    # scaffold
    assert "region = var.region" in files["provider.tf"]
    assert 'default     = "ap-south-1"' in files["variables.tf"]
    assert "sensitive   = true" in files["variables.tf"]


def test_compile_terraform_tracks_unmapped_blocks():
    ir = {
        "version": 1, "provider": "aws", "region": "r", "name": "n",
        "nodes": [
            {"id": "v", "type": "vpc", "props": {"cidr": "10.0.0.0/16"}},
            {"id": "w", "type": "waf", "props": {}},
        ],
    }
    files = compile_terraform(ir)
    assert "not yet mapped" in files["main.tf"].lower()
    assert "waf" in files["README.md"]
    _, _, unmapped = to_resources(ir)
    assert unmapped == ["waf"]


def test_targets_registry_and_dispatch():
    ids = [t["id"] for t in list_targets()]
    assert "ansible" in ids and "terraform" in ids
    assert "main.tf" in compile_target(TF_IR, "terraform")
    assert "site.yml" in compile_target(TF_IR, "ansible")
    with pytest.raises(TargetError):
        compile_target(TF_IR, "nope")
