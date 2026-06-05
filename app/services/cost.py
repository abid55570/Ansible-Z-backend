"""Rough monthly cost estimate for an IR design — Infracost-style, no external deps.

Curated on-demand US-East-1 baseline prices for the cost-driving resources, scaled by a
small per-region multiplier. Usage-based services (S3, Lambda, on-demand DynamoDB, data
transfer, …) are reported as usage-based rather than guessed. A planning estimate — not a
quote. (A precise mode running Infracost on the generated Terraform comes later.)
"""

HOURS_PER_MONTH = 730

EC2_HOURLY = {
    "t2.micro": 0.0116, "t3.micro": 0.0104, "t3.small": 0.0208, "t3.medium": 0.0416,
    "t3.large": 0.0832, "t3.xlarge": 0.1664, "m5.large": 0.096, "m5.xlarge": 0.192,
    "m6i.large": 0.096, "c5.large": 0.085,
}
RDS_HOURLY = {
    "db.t3.micro": 0.017, "db.t3.small": 0.034, "db.t3.medium": 0.068, "db.t3.large": 0.136,
    "db.m5.large": 0.171, "db.m6g.large": 0.162,
}
REGION_MULTIPLIER = {
    "us-east-1": 1.0, "us-east-2": 1.0, "us-west-1": 1.0, "us-west-2": 1.0, "ap-south-1": 1.0,
    "ap-southeast-1": 1.08, "ap-northeast-1": 1.10, "eu-west-1": 1.06, "eu-central-1": 1.08,
}
DEFAULT_MULTIPLIER = 1.05

_USAGE_BASED = {
    "s3_bucket", "s3_website", "lambda", "dynamodb", "sqs", "sns", "cloudwatch", "api_gateway",
    "glue_crawler", "glue_job", "cloudfront", "backup_vault", "backup_plan", "backup_selection",
    "eventbridge", "cloudtrail",
}


def _multiplier(region: str) -> float:
    return REGION_MULTIPLIER.get(region, DEFAULT_MULTIPLIER)


def _node_cost(node: dict, mult: float) -> tuple[float, str]:
    t = node["type"]
    p = node.get("props", {})
    if t == "ec2_instance":
        itype = p.get("instance_type", "t3.micro")
        return EC2_HOURLY.get(itype, 0.05) * HOURS_PER_MONTH * mult, f"{itype} on-demand"
    if t == "rds":
        cls = p.get("instance_class", "db.t3.micro")
        gb = int(float(p.get("storage", 20)))
        return (RDS_HOURLY.get(cls, 0.07) * HOURS_PER_MONTH + gb * 0.115) * mult, f"{cls} + {gb}GB"
    if t == "eks_nodegroup":
        size = int(p.get("desired_size", 2))
        itype = p.get("instance_type", "t3.medium")
        return EC2_HOURLY.get(itype, 0.0416) * HOURS_PER_MONTH * size * mult, f"{size} x {itype}"
    if t == "ecs_service":
        cpu = float(p.get("cpu", 512)) / 1024.0
        mem = float(p.get("memory", 1024)) / 1024.0
        count = int(p.get("desired_count", 2))
        rate = cpu * 0.04048 + mem * 0.004445
        return rate * HOURS_PER_MONTH * count * mult, f"Fargate {count} x {cpu:g}vCPU/{mem:g}GB"
    if t == "nat_gateway":
        return 0.045 * HOURS_PER_MONTH * mult, "hourly + data processing (usage)"
    if t == "alb":
        return 0.0225 * HOURS_PER_MONTH * mult, "hourly + LCU (usage)"
    if t == "eks_cluster":
        return 0.10 * HOURS_PER_MONTH * mult, "control plane"
    if t in ("transit_gateway", "vpn_gateway"):
        return 0.05 * HOURS_PER_MONTH * mult, "hourly attachment"
    if t == "vpc_endpoint":
        return 0.01 * HOURS_PER_MONTH * mult, "interface endpoint hourly"
    if t == "kms_key":
        return 1.0, "per key"
    if t == "waf":
        return 5.0, "web ACL ($5) + rules (usage)"
    if t in _USAGE_BASED:
        return 0.0, "usage-based"
    return 0.0, "no direct charge"


def estimate(ir: dict) -> dict:
    """Per-resource monthly cost breakdown + total (USD) for a design."""
    region = ir.get("region", "us-east-1")
    mult = _multiplier(region)
    items = []
    for node in ir.get("nodes", []):
        monthly, note = _node_cost(node, mult)
        items.append({"id": node["id"], "type": node["type"], "monthly": round(monthly, 2), "note": note})
    total = round(sum(item["monthly"] for item in items), 2)
    return {
        "currency": "USD",
        "region": region,
        "monthly_total": total,
        "items": items,
        "disclaimer": "Rough on-demand estimate; usage-based services are not included. Not a quote.",
    }
