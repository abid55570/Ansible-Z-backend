import json

from app.ir.targets import compile_target
from app.ir.targets.cdk import compile_cdk

CDK_IR = {
    "version": 1, "provider": "aws", "region": "ap-south-1", "name": "cdk",
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
        {"id": "db", "type": "rds", "props": {}, "inputs": {"subnets": "pub"}},
        {"id": "ddb", "type": "dynamodb", "props": {}},
        {"id": "q", "type": "sqs", "props": {}},
        {"id": "topic", "type": "sns", "props": {}},
        {"id": "cw", "type": "cloudwatch", "props": {}},
        {"id": "wafnode", "type": "waf", "props": {}},  # unmapped
    ],
}


def test_compile_cdk_app():
    files = compile_cdk(CDK_IR)
    assert {"lib/stack.ts", "bin/app.ts", "cdk.json", "package.json", "tsconfig.json", "README.md"} <= set(files)
    stack = files["lib/stack.ts"]
    assert 'import * as ec2 from "aws-cdk-lib/aws-ec2"' in stack
    assert 'new ec2.CfnVPC(this, "vpc"' in stack
    assert "vpcId: vpc.ref" in stack                          # ref via .ref
    assert "mapPublicIpOnLaunch: true" in stack
    assert "imageId: defaultAmi" in stack and 'imageId: "ami-1"' in stack
    assert "allocationId: nat_eip.attrAllocationId" in stack  # eip attribute ref
    assert "sg.attrGroupId" in stack                          # sg id attribute
    assert "assumeRolePolicyDocument:" in stack
    assert "new rds.CfnDBSubnetGroup(" in stack and "dbSubnetGroupName: db_subnets.ref" in stack
    assert "subnets: [pub.ref, priv.ref]" in stack
    assert 'key: "Name"' in stack                             # CDK L1 tag format [{key, value}]
    assert "const defaultAmi" in stack and "const dbPassword" in stack
    assert "waf" in files["README.md"]
    assert "new NeviriStack(app," in files["bin/app.ts"]
    assert "aws-cdk-lib" in json.loads(files["package.json"])["dependencies"]


def test_cdk_minimal_program_imports_only_used_services():
    files = compile_cdk({"region": "r", "name": "n", "nodes": [{"id": "q", "type": "sqs", "props": {}}]})
    stack = files["lib/stack.ts"]
    assert 'import * as sqs from "aws-cdk-lib/aws-sqs"' in stack
    assert "aws-cdk-lib/aws-ec2" not in stack          # unused service not imported
    assert "const defaultAmi" not in stack and "const dbPassword" not in stack
    assert "Not yet mapped" not in files["README.md"]


def test_compile_target_dispatches_cdk():
    assert "lib/stack.ts" in compile_target(CDK_IR, "cdk")
