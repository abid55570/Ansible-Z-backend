"""Render every ready template (+ Day-2) and a comprehensive custom IR design to disk.

Used by the audit so external tools (ansible-lint) can analyse real project trees.

Usage:
    PYTHONPATH=. python scripts/audit_dump.py /tmp/azaudit
"""

import sys
from pathlib import Path

from app.ir.compiler import compile_ir
from app.services.day2 import day2_files
from app.services.generator import list_templates, load_manifest, render_project, sample_config

# A wide design that exercises most IR blocks (mirrors scripts/check_design.py).
DESIGN_IR = {
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
        {"id": "site1", "type": "s3_website", "props": {}, "inputs": {"bucket": "logs"}},
        {"id": "tg1", "type": "target_group", "props": {}, "inputs": {"vpc": "vpc1"}},
        {"id": "lt1", "type": "launch_template", "props": {}},
        {"id": "fn1", "type": "lambda", "props": {}},
        {"id": "ddb1", "type": "dynamodb", "props": {}},
        {"id": "key1", "type": "kms_key", "props": {}},
        {"id": "role1", "type": "iam_role", "props": {}},
        {"id": "eks1", "type": "eks_cluster", "props": {}, "inputs": {"subnets": ["pub1", "pub2"], "security_group": ["sg1"]}},
        {"id": "ng1", "type": "eks_nodegroup", "props": {}, "inputs": {"subnets": ["pub1", "pub2"]}},
        {"id": "tgw1", "type": "transit_gateway", "props": {}},
        {"id": "vgw1", "type": "vpn_gateway", "props": {}, "inputs": {"vpc": "vpc1"}},
        {"id": "trail1", "type": "cloudtrail", "props": {}},
        {"id": "api1", "type": "api_gateway", "props": {}},
        {"id": "evt1", "type": "eventbridge", "props": {}},
        {"id": "ep1", "type": "vpc_endpoint", "props": {}, "inputs": {"vpc": "vpc1"}},
        {"id": "ecs1", "type": "ecs_cluster", "props": {}},
        {"id": "svc1", "type": "ecs_service", "props": {}, "inputs": {"cluster": "ecs1", "subnets": ["pub1", "pub2"]}},
        {"id": "cf1", "type": "cloudfront", "props": {}},
        {"id": "gc1", "type": "glue_crawler", "props": {}},
        {"id": "gj1", "type": "glue_job", "props": {}},
        {"id": "q1", "type": "sqs", "props": {}},
        {"id": "t1", "type": "sns", "props": {}},
        {"id": "bv1", "type": "backup_vault", "props": {}},
        {"id": "bp1", "type": "backup_plan", "props": {}},
        {"id": "bs1", "type": "backup_selection", "props": {}},
        {"id": "waf1", "type": "waf", "props": {}},
        {"id": "cw1", "type": "cloudwatch", "props": {}},
    ],
}


def write_project(root: Path, files: dict) -> None:
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/azaudit")
    out.mkdir(parents=True, exist_ok=True)
    d2 = day2_files()

    names = []
    for tpl in list_templates():
        if not tpl["ready"]:
            continue
        slug = tpl["slug"]
        manifest = load_manifest(slug)
        files = {**d2, **render_project(slug, sample_config(manifest, "uat"), env="uat")}
        write_project(out / slug, files)
        names.append(slug)

    files = {**d2, **compile_ir(DESIGN_IR)}
    write_project(out / "_custom_design", files)
    names.append("_custom_design")

    print(f"dumped {len(names)} projects to {out}")
    for n in names:
        print(" ", n)


if __name__ == "__main__":
    main()
