"""Pulumi target: compile an IR design into a TypeScript Pulumi program (@pulumi/aws).

Per-block builders emit ``const <var> = new aws.<svc>.<Type>("<id>", { ... });`` with
camelCase properties and references resolved as ``<var>.id`` TS expressions. Blocks
without a builder are reported as unmapped.
"""

import json
import re
from dataclasses import dataclass

from app.ir.compiler import _topo_sort, validate
from app.services.projectfmt import normalize_files


@dataclass(frozen=True)
class Expr:
    """A raw TypeScript expression (a reference or identifier), emitted verbatim."""

    code: str


def _var(node_id: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]", "_", node_id)
    return name if name[:1].isalpha() or name[:1] == "_" else "_" + name


def _ref(node_id: str, attr: str = "id") -> Expr:
    return Expr(f"{_var(node_id)}.{attr}")


def _listify(value) -> list:
    return value if isinstance(value, list) else [value]


def _refs(value, attr: str = "id") -> list:
    return [_ref(v, attr) for v in _listify(value)]


def _tags(node_id: str) -> dict:
    return {"Name": node_id, "ManagedBy": "neviri-ansi"}


_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _key(k: str) -> str:
    return k if _IDENT.match(k) else json.dumps(k)


def _js(value, indent: int = 0) -> str:
    pad = "  " * indent
    if isinstance(value, Expr):
        return value.code
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(_js(v, indent) for v in value) + "]"
    if isinstance(value, dict):
        body = "".join(f"{pad}  {_key(k)}: {_js(v, indent + 1)},\n" for k, v in value.items())
        return "{\n" + body + pad + "}"
    return "undefined"


def _decl(nid: str, pulumi_type: str, props: dict) -> str:
    return f'const {_var(nid)} = new {pulumi_type}("{nid}", {_js(props)});'


def _vpc(nid, node, refs, ctx):
    return [_decl(nid, "aws.ec2.Vpc", {
        "cidrBlock": node["props"].get("cidr", "10.0.0.0/16"),
        "enableDnsSupport": True, "enableDnsHostnames": True, "tags": _tags(nid),
    })]


def _subnet(nid, node, refs, ctx):
    p = node["props"]
    props = {"vpcId": _ref(refs["vpc"]), "cidrBlock": p.get("cidr", "10.0.1.0/24"), "tags": _tags(nid)}
    if p.get("az"):
        props["availabilityZone"] = p["az"]
    if p.get("public"):
        props["mapPublicIpOnLaunch"] = True
    return [_decl(nid, "aws.ec2.Subnet", props)]


def _security_group(nid, node, refs, ctx):
    p = node["props"]
    ingress = []
    if p.get("ssh_cidr"):
        ingress.append({"protocol": "tcp", "fromPort": 22, "toPort": 22, "cidrBlocks": [p["ssh_cidr"]]})
    if p.get("allow_http"):
        ingress.append({"protocol": "tcp", "fromPort": 80, "toPort": 80, "cidrBlocks": ["0.0.0.0/0"]})
    if p.get("allow_https"):
        ingress.append({"protocol": "tcp", "fromPort": 443, "toPort": 443, "cidrBlocks": ["0.0.0.0/0"]})
    props = {
        "description": p.get("description", nid),
        "vpcId": _ref(refs["vpc"]),
        "egress": [{"protocol": "-1", "fromPort": 0, "toPort": 0, "cidrBlocks": ["0.0.0.0/0"]}],
        "tags": _tags(nid),
    }
    if ingress:
        props["ingress"] = ingress
    return [_decl(nid, "aws.ec2.SecurityGroup", props)]


def _ec2_instance(nid, node, refs, ctx):
    p = node["props"]
    props = {
        "ami": p["ami"] if p.get("ami") else Expr("defaultAmi"),
        "instanceType": p.get("instance_type", "t3.micro"),
        "subnetId": _ref(refs["subnet"]),
        "vpcSecurityGroupIds": [_ref(refs["security_group"])],
        "tags": _tags(nid),
    }
    if p.get("public"):
        props["associatePublicIpAddress"] = True
    return [_decl(nid, "aws.ec2.Instance", props)]


def _igw(nid, node, refs, ctx):
    return [_decl(nid, "aws.ec2.InternetGateway", {"vpcId": _ref(refs["vpc"]), "tags": _tags(nid)})]


def _nat_gateway(nid, node, refs, ctx):
    eip = f"{nid}_eip"
    return [
        _decl(eip, "aws.ec2.Eip", {"domain": "vpc", "tags": _tags(nid)}),
        _decl(nid, "aws.ec2.NatGateway", {
            "subnetId": _ref(refs["subnet"]),
            "allocationId": _ref(eip, "allocationId"),
            "tags": _tags(nid),
        }),
    ]


def _route_table(nid, node, refs, ctx):
    out = [_decl(nid, "aws.ec2.RouteTable", {"vpcId": _ref(refs["vpc"]), "tags": _tags(nid)})]
    for i, sub in enumerate(_listify(refs["subnets"])):
        out.append(_decl(f"{nid}_assoc{i}", "aws.ec2.RouteTableAssociation", {
            "subnetId": _ref(sub), "routeTableId": _ref(nid),
        }))
    return out


def _s3_bucket(nid, node, refs, ctx):
    props = {"tags": _tags(nid)}
    if node["props"].get("bucket_name"):
        props["bucket"] = node["props"]["bucket_name"]
    if node["props"].get("versioning"):
        props["versioning"] = {"enabled": True}
    return [_decl(nid, "aws.s3.Bucket", props)]


def _iam_role(nid, node, refs, ctx):
    svc = node["props"].get("service", "ec2.amazonaws.com")
    policy = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Principal": {"Service": svc}, "Action": "sts:AssumeRole"},
    ]}
    return [_decl(nid, "aws.iam.Role", {
        "assumeRolePolicy": Expr("JSON.stringify(" + _js(policy) + ")"),
        "tags": _tags(nid),
    })]


def _alb(nid, node, refs, ctx):
    return [_decl(nid, "aws.lb.LoadBalancer", {
        "loadBalancerType": "application",
        "subnets": _refs(refs["subnets"]),
        "securityGroups": [_ref(refs["security_group"])],
        "tags": _tags(nid),
    })]


def _target_group(nid, node, refs, ctx):
    p = node["props"]
    return [_decl(nid, "aws.lb.TargetGroup", {
        "port": p.get("port", 80), "protocol": p.get("protocol", "HTTP"),
        "vpcId": _ref(refs["vpc"]), "targetType": "instance",
        "healthCheck": {"path": p.get("health_check_path", "/")},
        "tags": _tags(nid),
    })]


def _rds(nid, node, refs, ctx):
    p = node["props"]
    group = f"{nid}_subnets"
    return [
        _decl(group, "aws.rds.SubnetGroup", {"subnetIds": _refs(refs["subnets"]), "tags": _tags(nid)}),
        _decl(nid, "aws.rds.Instance", {
            "engine": p.get("engine", "postgres"),
            "instanceClass": p.get("instance_class", "db.t3.micro"),
            "allocatedStorage": p.get("storage", 20),
            "username": p.get("username", "appadmin"),
            "password": Expr("dbPassword"),
            "dbSubnetGroupName": _ref(group, "name"),
            "skipFinalSnapshot": True,
            "publiclyAccessible": False,
            "tags": _tags(nid),
        }),
    ]


def _dynamodb(nid, node, refs, ctx):
    hk = node["props"].get("hash_key", "id")
    return [_decl(nid, "aws.dynamodb.Table", {
        "billingMode": "PAY_PER_REQUEST",
        "hashKey": hk,
        "attributes": [{"name": hk, "type": "S"}],
        "tags": _tags(nid),
    })]


def _sqs(nid, node, refs, ctx):
    return [_decl(nid, "aws.sqs.Queue", {"tags": _tags(nid)})]


def _sns(nid, node, refs, ctx):
    return [_decl(nid, "aws.sns.Topic", {"tags": _tags(nid)})]


def _cloudwatch(nid, node, refs, ctx):
    return [_decl(nid, "aws.cloudwatch.LogGroup", {
        "retentionInDays": node["props"].get("retention_days", 30), "tags": _tags(nid),
    })]


PULUMI_BUILDERS = {
    "vpc": _vpc, "subnet": _subnet, "security_group": _security_group, "ec2_instance": _ec2_instance,
    "igw": _igw, "nat_gateway": _nat_gateway, "route_table": _route_table, "s3_bucket": _s3_bucket,
    "iam_role": _iam_role, "alb": _alb, "target_group": _target_group, "rds": _rds,
    "dynamodb": _dynamodb, "sqs": _sqs, "sns": _sns, "cloudwatch": _cloudwatch,
}


def compile_pulumi(ir: dict) -> dict:
    """Compile an IR design into a Pulumi (TypeScript) project ({path: content})."""
    validate(ir)
    nodes = {n["id"]: n for n in ir["nodes"]}
    ctx = {"region": ir["region"], "name": ir["name"]}
    statements: list = []
    unmapped: list = []
    for nid in _topo_sort(ir["nodes"]):
        node = nodes[nid]
        builder = PULUMI_BUILDERS.get(node["type"])
        if builder is None:
            unmapped.append(node["type"])
            continue
        statements.extend(builder(nid, node, node.get("inputs", {}), ctx))

    body = "\n".join(statements)
    consts = []
    if "defaultAmi" in body:
        consts.append('const defaultAmi = "ami-0c55b159cbfafe1f0"; // override for your region')
    if "dbPassword" in body:
        consts.append('const dbPassword = "CHANGE_ME"; // use pulumi config set --secret in real use')
    preamble = 'import * as aws from "@pulumi/aws";\n'
    if consts:
        preamble += "\n" + "\n".join(consts) + "\n"
    index = f"// {ir['name']} - generated by Neviri-Ansi (Pulumi)\n{preamble}\n{body}\n"

    project = re.sub(r"[^a-zA-Z0-9-]", "-", ir["name"])
    return normalize_files({
        "index.ts": index,
        "Pulumi.yaml": f"name: {project}\nruntime: nodejs\ndescription: {ir['name']} - generated by Neviri-Ansi\n",
        "package.json": json.dumps({
            "name": project,
            "main": "index.ts",
            "dependencies": {"@pulumi/pulumi": "^3.0.0", "@pulumi/aws": "^6.0.0"},
        }, indent=2) + "\n",
        ".gitignore": "node_modules/\nPulumi.*.yaml\n",
        "README.md": _readme(ir, unmapped),
    })


def _readme(ir: dict, unmapped: list) -> str:
    lines = [
        f"# {ir['name']} - Pulumi (TypeScript)",
        "",
        f"Region: {ir['region']}",
        "",
        "## Run",
        "```bash",
        "npm install",
        f"pulumi config set aws:region {ir['region']}",
        "pulumi up",
        "```",
    ]
    if unmapped:
        lines += ["", "## Not yet mapped", "", "These designed components have no Pulumi mapping yet and were skipped:", ""]
        lines += [f"- `{u}`" for u in sorted(set(unmapped))]
    return "\n".join(lines) + "\n"
