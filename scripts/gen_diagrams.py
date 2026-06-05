"""Generate publication-quality architecture diagrams for every template.

Reads each template's existing ``diagram`` metadata (nodes + edges) and renders a
clustered, AWS-icon PNG via mingrammer ``diagrams`` + Graphviz. VPC/subnet nodes
become zone boxes (Clusters); everything else becomes an icon placed inside its
zone. Structural edges (vpc/subnet attachment) drive the nesting; the rest are
drawn as connections.

Pre-generated and committed to ``app/templates/<slug>/diagram.png`` so the API
serves them with no runtime Graphviz dependency.

Build-time deps (only needed to (re)generate, not to run the app):
    pip install diagrams
    Graphviz `dot` on PATH  (winget install Graphviz.Graphviz  /  apt install graphviz)

Run:  python scripts/gen_diagrams.py
"""

import importlib
import os
import shutil
from pathlib import Path

# Make Graphviz's `dot` reachable (winget installs here on Windows).
if not shutil.which("dot"):
    for _p in (r"C:\Program Files\Graphviz\bin", r"C:\Program Files (x86)\Graphviz\bin"):
        if Path(_p, "dot.exe").exists():
            os.environ["PATH"] = _p + os.pathsep + os.environ["PATH"]
            break

from diagrams import Cluster, Diagram, Edge  # noqa: E402

from app.services.generator import TEMPLATES_DIR, list_templates, load_manifest  # noqa: E402

# node type -> (diagrams module, class). Unknown types fall back to General.
TYPE_MAP: dict[str, tuple[str, str]] = {
    "ec2_instance": ("diagrams.aws.compute", "EC2"),
    "bastion": ("diagrams.aws.compute", "EC2"),
    "launch_template": ("diagrams.aws.compute", "AutoScaling"),
    "asg": ("diagrams.aws.compute", "AutoScaling"),
    "alb": ("diagrams.aws.network", "ElbApplicationLoadBalancer"),
    "target_group": ("diagrams.aws.network", "ELB"),
    "rds": ("diagrams.aws.database", "RDS"),
    "dynamodb": ("diagrams.aws.database", "Dynamodb"),
    "igw": ("diagrams.aws.network", "InternetGateway"),
    "nat_gateway": ("diagrams.aws.network", "NATGateway"),
    "route_table": ("diagrams.aws.network", "RouteTable"),
    "s3_bucket": ("diagrams.aws.storage", "S3"),
    "s3_website": ("diagrams.aws.storage", "S3"),
    "lambda": ("diagrams.aws.compute", "Lambda"),
    "kms_key": ("diagrams.aws.security", "KMS"),
    "iam_role": ("diagrams.aws.security", "IAMRole"),
    "eks_cluster": ("diagrams.aws.compute", "EKS"),
    "eks_nodegroup": ("diagrams.aws.compute", "EC2"),
    "ecs_service": ("diagrams.aws.compute", "ECS"),
    "ecs_cluster": ("diagrams.aws.compute", "ECS"),
    "transit_gateway": ("diagrams.aws.network", "TransitGateway"),
    "vpn_gateway": ("diagrams.aws.network", "DirectConnect"),
    "dx_gateway": ("diagrams.aws.network", "DirectConnect"),
    "vpc_endpoint": ("diagrams.aws.network", "Endpoint"),
    "privatelink": ("diagrams.aws.network", "Privatelink"),
    "cloudfront": ("diagrams.aws.network", "CloudFront"),
    "api_gateway": ("diagrams.aws.network", "APIGateway"),
    "cloudtrail": ("diagrams.aws.management", "Cloudtrail"),
    "cloudwatch": ("diagrams.aws.management", "Cloudwatch"),
    "logging": ("diagrams.aws.management", "Cloudwatch"),
    "flow_logs": ("diagrams.aws.management", "Cloudwatch"),
    "eventbridge": ("diagrams.aws.integration", "Eventbridge"),
    "sqs": ("diagrams.aws.integration", "SQS"),
    "sns": ("diagrams.aws.integration", "SNS"),
    "glue_crawler": ("diagrams.aws.analytics", "GlueCrawlers"),
    "glue_job": ("diagrams.aws.analytics", "Glue"),
    "athena": ("diagrams.aws.analytics", "Athena"),
    "security_group": ("diagrams.aws.network", "Nacl"),
    "waf": ("diagrams.aws.security", "WAF"),
    "secrets": ("diagrams.aws.security", "SecretsManager"),
    "vault_tokenize": ("diagrams.aws.security", "SecretsManager"),
    "mtls": ("diagrams.aws.security", "Shield"),
    "firewall": ("diagrams.aws.security", "Shield"),
    "datacenter": ("diagrams.onprem.compute", "Server"),
    "idp": ("diagrams.onprem.client", "Users"),
    "user": ("diagrams.onprem.client", "Users"),
    "developer": ("diagrams.onprem.client", "Users"),
}
FALLBACK = ("diagrams.aws.general", "General")
STRUCTURAL_PORTS = {"vpc", "subnet", "subnets"}

_cache: dict[tuple[str, str], type] = {}


def _cls(ntype: str):
    mod, name = TYPE_MAP.get(ntype, FALLBACK)
    key = (mod, name)
    if key not in _cache:
        _cache[key] = getattr(importlib.import_module(mod), name)
    return _cache[key]


def _render(slug: str, manifest: dict) -> bool:
    diagram = manifest.get("diagram")
    if not diagram or not diagram.get("nodes"):
        return False
    nodes = diagram["nodes"]
    edges = diagram.get("edges", [])
    types = {n["id"]: n["type"] for n in nodes}
    label = {n["id"]: (n.get("label") or n["id"]) for n in nodes}

    vpc_ids = [n["id"] for n in nodes if n["type"] == "vpc"]
    subnet_ids = [n["id"] for n in nodes if n["type"] == "subnet"]

    vpc_of_subnet: dict[str, str] = {}
    for e in edges:
        if e.get("port") == "vpc" and types.get(e["to"]) == "subnet":
            vpc_of_subnet[e["to"]] = e["from"]

    # Where each non-zone node lives: a subnet id, a vpc id, or None (top level).
    container: dict[str, str] = {}
    for e in edges:
        port, frm, to = e.get("port"), e["from"], e["to"]
        if types.get(to) in ("vpc", "subnet"):
            continue
        if port in ("subnet", "subnets"):
            container.setdefault(to, frm)  # nest in the (first) referenced subnet
        elif port == "vpc":
            container.setdefault(to, frm)  # attach at the VPC level

    # Pull traffic-connected resources (e.g. an ECS service wired only to the ALB)
    # into the VPC of a neighbour, so they don't float outside the boundary.
    never_nest = {"datacenter", "user", "developer", "idp", "transit_gateway", "dx_gateway"}
    adj: dict[str, list[str]] = {}
    for e in edges:
        adj.setdefault(e["from"], []).append(e["to"])
        adj.setdefault(e["to"], []).append(e["from"])

    for n in nodes:
        nid = n["id"]
        if types[nid] in ("vpc", "subnet") or nid in container or types[nid] in never_nest:
            continue
        nbs = adj.get(nid, [])
        # Inherit a neighbour's zone — prefer one that lives in a subnet so the
        # node nests beside it rather than floating at the VPC edge.
        chosen = next((nb for nb in nbs if container.get(nb) in subnet_ids), None) or next(
            (nb for nb in nbs if nb in container), None
        )
        if chosen:
            container[nid] = container[chosen]

    out = TEMPLATES_DIR / slug / "diagram"
    graph_attr = {"fontsize": "22", "bgcolor": "white", "pad": "0.6", "splines": "ortho",
                  "nodesep": "0.7", "ranksep": "1.1", "fontname": "Sans-Serif"}
    node_attr = {"fontsize": "13", "fontname": "Sans-Serif"}

    with Diagram(manifest.get("name", slug), filename=str(out), outformat="png", show=False,
                 direction="LR", graph_attr=graph_attr, node_attr=node_attr):
        objs: dict[str, object] = {}

        def make(nid: str):
            objs[nid] = _cls(types[nid])(label[nid])

        for vpc in vpc_ids:
            with Cluster(label[vpc]):
                for nid in [n["id"] for n in nodes if container.get(n["id"]) == vpc]:
                    make(nid)
                for sub in [s for s in subnet_ids if vpc_of_subnet.get(s) == vpc]:
                    members = [n["id"] for n in nodes if container.get(n["id"]) == sub]
                    if not members:
                        continue  # skip empty subnet zones (keeps the picture clean)
                    with Cluster(label[sub]):
                        for nid in members:
                            make(nid)

        for n in nodes:  # everything not already placed and not itself a zone
            if types[n["id"]] in ("vpc", "subnet") or n["id"] in objs:
                continue
            make(n["id"])

        for e in edges:
            if e.get("port") in STRUCTURAL_PORTS:
                continue
            a, b = objs.get(e["from"]), objs.get(e["to"])
            if a is not None and b is not None:
                a >> Edge(color="#4b5563") >> b

    return True


def main() -> None:
    rendered = 0
    for summary in list_templates():
        slug = summary["slug"]
        if _render(slug, load_manifest(slug)):
            rendered += 1
            print(f"  rendered {slug}/diagram.png")
    print(f"\nDone: {rendered} diagrams")


if __name__ == "__main__":
    main()
