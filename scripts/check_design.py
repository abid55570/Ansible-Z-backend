"""Compile a sample custom IR design and run ansible-playbook --syntax-check on it."""

from app.ir.compiler import compile_ir
from app.services.ansible_check import ansible_available, syntax_check

IR = {
    "version": 1,
    "provider": "aws",
    "region": "ap-south-1",
    "name": "demo-design",
    "nodes": [
        {"id": "vpc1", "type": "vpc", "props": {"cidr": "10.0.0.0/16"}},
        {"id": "pub1", "type": "subnet", "props": {"cidr": "10.0.1.0/24", "public": True, "az": "ap-south-1a"}, "inputs": {"vpc": "vpc1"}},
        {"id": "pub2", "type": "subnet", "props": {"cidr": "10.0.2.0/24", "public": True, "az": "ap-south-1b"}, "inputs": {"vpc": "vpc1"}},
        {"id": "sg1", "type": "security_group", "props": {"ingress": [{"port": 80}, {"port": 443}]}, "inputs": {"vpc": "vpc1"}},
        {"id": "web", "type": "ec2_instance", "props": {"instance_type": "t3.micro"}, "inputs": {"subnet": "pub1", "security_group": "sg1"}},
        {"id": "alb1", "type": "alb", "props": {}, "inputs": {"subnets": ["pub1", "pub2"], "security_group": "sg1"}},
        {"id": "db1", "type": "rds", "props": {"engine": "postgres"}, "inputs": {"subnets": ["pub1", "pub2"]}},
        {"id": "igw1", "type": "igw", "props": {}, "inputs": {"vpc": "vpc1"}},
        {"id": "nat1", "type": "nat_gateway", "props": {}, "inputs": {"subnet": "pub1"}},
        {"id": "rt1", "type": "route_table", "props": {}, "inputs": {"vpc": "vpc1", "subnets": ["pub1"]}},
        {"id": "logs", "type": "s3_bucket", "props": {"bucket_name": "demo-logs", "versioning": True}},
        {"id": "tg1", "type": "target_group", "props": {}, "inputs": {"vpc": "vpc1"}},
        {"id": "lt1", "type": "launch_template", "props": {}},
        {"id": "fn1", "type": "lambda", "props": {}},
        {"id": "ddb1", "type": "dynamodb", "props": {}},
        {"id": "key1", "type": "kms_key", "props": {}},
        {"id": "role1", "type": "iam_role", "props": {}},
        {"id": "eks1", "type": "eks_cluster", "props": {}, "inputs": {"subnets": ["pub1", "pub2"]}},
        {"id": "ng1", "type": "eks_nodegroup", "props": {}, "inputs": {"subnets": ["pub1", "pub2"]}},
        {"id": "tgw1", "type": "transit_gateway", "props": {}},
        {"id": "vgw1", "type": "vpn_gateway", "props": {}, "inputs": {"vpc": "vpc1"}},
        {"id": "trail1", "type": "cloudtrail", "props": {}},
        {"id": "api1", "type": "api_gateway", "props": {}},
        {"id": "evt1", "type": "eventbridge", "props": {}},
        {"id": "ep1", "type": "vpc_endpoint", "props": {}, "inputs": {"vpc": "vpc1"}},
    ],
}

print("ansible-playbook available:", ansible_available())
files = compile_ir(IR)
print("compiled files:", sorted(files))
report = syntax_check(files)
print("syntax-check:", report["status"])
if report.get("output"):
    print(report["output"])
