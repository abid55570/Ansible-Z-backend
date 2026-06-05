"""Export AWS service icons for the interactive designer canvas.

Copies the icon PNG for each IR block type from the ``diagrams`` package into
``frontend/public/aws-icons/<block_type>.png`` so the React-Flow canvas (the
editable designer) can render real AWS icons — the same artwork used by the
static template diagrams, for visual consistency.

Build-time only (icons are committed). Run:  python scripts/export_icons.py
"""

import importlib
import shutil
from pathlib import Path

import diagrams

ICONS_BASE = Path(diagrams.__file__).resolve().parent.parent / "resources"
OUT_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "aws-icons"

# IR block type -> (diagrams module, class) for its icon.
ICON_MAP: dict[str, tuple[str, str]] = {
    "vpc": ("diagrams.aws.network", "VPC"),
    "subnet": ("diagrams.aws.network", "PublicSubnet"),
    "security_group": ("diagrams.aws.network", "Nacl"),
    "ec2_instance": ("diagrams.aws.compute", "EC2"),
    "alb": ("diagrams.aws.network", "ElbApplicationLoadBalancer"),
    "rds": ("diagrams.aws.database", "RDS"),
    "igw": ("diagrams.aws.network", "InternetGateway"),
    "nat_gateway": ("diagrams.aws.network", "NATGateway"),
    "route_table": ("diagrams.aws.network", "RouteTable"),
    "s3_bucket": ("diagrams.aws.storage", "S3"),
    "s3_website": ("diagrams.aws.storage", "S3"),
    "target_group": ("diagrams.aws.network", "ELB"),
    "launch_template": ("diagrams.aws.compute", "AutoScaling"),
    "lambda": ("diagrams.aws.compute", "Lambda"),
    "dynamodb": ("diagrams.aws.database", "Dynamodb"),
    "kms_key": ("diagrams.aws.security", "KMS"),
    "iam_role": ("diagrams.aws.security", "IAMRole"),
    "eks_cluster": ("diagrams.aws.compute", "EKS"),
    "eks_nodegroup": ("diagrams.aws.compute", "EC2"),
    "transit_gateway": ("diagrams.aws.network", "TransitGateway"),
    "vpn_gateway": ("diagrams.aws.network", "DirectConnect"),
    "cloudtrail": ("diagrams.aws.management", "Cloudtrail"),
    "api_gateway": ("diagrams.aws.network", "APIGateway"),
    "eventbridge": ("diagrams.aws.integration", "Eventbridge"),
    "vpc_endpoint": ("diagrams.aws.network", "Endpoint"),
    "ecs_cluster": ("diagrams.aws.compute", "ECS"),
    "ecs_service": ("diagrams.aws.compute", "ECS"),
}


def _icon_path(mod: str, cls: str) -> Path:
    c = getattr(importlib.import_module(mod), cls)
    return ICONS_BASE / c._provider / c._type / c._icon


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for block_type, (mod, cls) in ICON_MAP.items():
        src = _icon_path(mod, cls)
        if not src.is_file():
            print(f"  MISSING icon for {block_type}: {src}")
            continue
        shutil.copyfile(src, OUT_DIR / f"{block_type}.png")
        n += 1
    print(f"Exported {n} icons -> {OUT_DIR}")


if __name__ == "__main__":
    main()
