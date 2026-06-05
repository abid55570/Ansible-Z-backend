import json

from app.ir.targets import compile_target
from app.ir.targets.pulumi import Expr, _js, _key, _var, compile_pulumi

PULUMI_IR = {
    "version": 1, "provider": "aws", "region": "ap-south-1", "name": "pulumi",
    "nodes": [
        {"id": "vpc", "type": "vpc", "props": {"cidr": "10.0.0.0/16"}},
        {"id": "pub", "type": "subnet", "props": {"cidr": "10.0.1.0/24", "public": True, "az": "ap-south-1a"}, "inputs": {"vpc": "vpc"}},
        {"id": "priv", "type": "subnet", "props": {"cidr": "10.0.2.0/24"}, "inputs": {"vpc": "vpc"}},
        {"id": "sg", "type": "security_group", "props": {"ssh_cidr": "1.2.3.4/32", "allow_http": True, "allow_https": True}, "inputs": {"vpc": "vpc"}},
        {"id": "sgbare", "type": "security_group", "props": {}, "inputs": {"vpc": "vpc"}},
        {"id": "web", "type": "ec2_instance", "props": {"ami": "ami-1", "public": True}, "inputs": {"subnet": "pub", "security_group": "sg"}},
        {"id": "web2", "type": "ec2_instance", "props": {}, "inputs": {"subnet": "priv", "security_group": "sgbare"}},
        {"id": "igw", "type": "igw", "props": {}, "inputs": {"vpc": "vpc"}},
        {"id": "nat", "type": "nat_gateway", "props": {}, "inputs": {"subnet": "pub"}},
        {"id": "rt", "type": "route_table", "props": {}, "inputs": {"vpc": "vpc", "subnets": ["pub"]}},
        {"id": "logs", "type": "s3_bucket", "props": {"bucket_name": "demo-logs", "versioning": True}},
        {"id": "assets", "type": "s3_bucket", "props": {}},
        {"id": "role", "type": "iam_role", "props": {}},
        {"id": "lb", "type": "alb", "props": {}, "inputs": {"subnets": ["pub", "priv"], "security_group": "sg"}},
        {"id": "tg", "type": "target_group", "props": {}, "inputs": {"vpc": "vpc"}},
        {"id": "db", "type": "rds", "props": {}, "inputs": {"subnets": "pub"}},  # single -> _listify
        {"id": "ddb", "type": "dynamodb", "props": {}},
        {"id": "q", "type": "sqs", "props": {}},
        {"id": "topic", "type": "sns", "props": {}},
        {"id": "cw", "type": "cloudwatch", "props": {}},
        {"id": "wafnode", "type": "waf", "props": {}},  # unmapped in Pulumi
    ],
}


def test_compile_pulumi_program():
    files = compile_pulumi(PULUMI_IR)
    assert {"index.ts", "Pulumi.yaml", "package.json", ".gitignore", "README.md"} <= set(files)
    ts = files["index.ts"]
    assert 'import * as aws from "@pulumi/aws"' in ts
    assert 'new aws.ec2.Vpc("vpc"' in ts
    assert "vpcId: vpc.id" in ts                          # ref
    assert "mapPublicIpOnLaunch: true" in ts              # public subnet
    assert "ami: defaultAmi" in ts                        # ec2 without ami -> const
    assert 'ami: "ami-1"' in ts                           # ec2 with ami
    assert "allocationId: nat_eip.allocationId" in ts     # nat -> eip attr ref
    assert "assumeRolePolicy: JSON.stringify(" in ts      # iam policy
    assert "new aws.rds.SubnetGroup(" in ts and "dbSubnetGroupName: db_subnets.name" in ts
    assert "subnets: [pub.id, priv.id]" in ts             # alb list of refs
    assert "ingress:" in ts                               # sg with rules
    assert "const defaultAmi" in ts and "const dbPassword" in ts
    assert "waf" in files["README.md"]
    assert "@pulumi/aws" in json.loads(files["package.json"])["dependencies"]


def test_pulumi_helpers_and_minimal_program():
    assert _var("web-sg") == "web_sg"
    assert _var("9web") == "_9web"
    assert _js(True) == "true" and _js(7) == "7" and _js(None) == "undefined"
    assert _js(Expr("x.id")) == "x.id"
    assert _key("Name") == "Name" and _key("a-b") == '"a-b"'
    files = compile_pulumi({"region": "r", "name": "n", "nodes": [{"id": "q", "type": "sqs", "props": {}}]})
    assert "const defaultAmi" not in files["index.ts"] and "const dbPassword" not in files["index.ts"]
    assert "Not yet mapped" not in files["README.md"]


def test_compile_target_dispatches_pulumi():
    assert "index.ts" in compile_target(PULUMI_IR, "pulumi")
