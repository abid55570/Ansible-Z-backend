"""AWS CDK target: compile an IR design into a TypeScript CDK app (aws-cdk-lib, L1 Cfn* constructs).

L1 constructs mirror CloudFormation 1:1 with camelCase properties, so the builders read
like the CloudFormation ones but emit ``new <ns>.Cfn<Type>(this, "<id>", { ... })`` with
references resolved as ``<var>.ref`` (or ``.attr*``). Reuses the generic TS-literal helpers
from the Pulumi target. Blocks without a builder are reported as unmapped.
"""

import json
import re

from app.ir.compiler import _topo_sort, validate
from app.ir.targets.pulumi import Expr, _js, _listify, _var
from app.services.projectfmt import normalize_files


def _ref(node_id: str, attr: str = "ref") -> Expr:
    return Expr(f"{_var(node_id)}.{attr}")


def _refs(value, attr: str = "ref") -> list:
    return [_ref(v, attr) for v in _listify(value)]


def _tags(node_id: str) -> list:
    return [{"key": "Name", "value": node_id}, {"key": "ManagedBy", "value": "neviri-ansi"}]


def _decl(nid: str, cdk_type: str, props: dict) -> str:
    return f'    const {_var(nid)} = new {cdk_type}(this, "{nid}", {_js(props, 2)});'


def _vpc(nid, node, refs, ctx):
    return [_decl(nid, "ec2.CfnVPC", {
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
    return [_decl(nid, "ec2.CfnSubnet", props)]


def _security_group(nid, node, refs, ctx):
    p = node["props"]
    ingress = []
    if p.get("ssh_cidr"):
        ingress.append({"ipProtocol": "tcp", "fromPort": 22, "toPort": 22, "cidrIp": p["ssh_cidr"]})
    if p.get("allow_http"):
        ingress.append({"ipProtocol": "tcp", "fromPort": 80, "toPort": 80, "cidrIp": "0.0.0.0/0"})
    if p.get("allow_https"):
        ingress.append({"ipProtocol": "tcp", "fromPort": 443, "toPort": 443, "cidrIp": "0.0.0.0/0"})
    props = {"groupDescription": p.get("description", nid), "vpcId": _ref(refs["vpc"]), "tags": _tags(nid)}
    if ingress:
        props["securityGroupIngress"] = ingress
    return [_decl(nid, "ec2.CfnSecurityGroup", props)]


def _ec2_instance(nid, node, refs, ctx):
    p = node["props"]
    return [_decl(nid, "ec2.CfnInstance", {
        "imageId": p["ami"] if p.get("ami") else Expr("defaultAmi"),
        "instanceType": p.get("instance_type", "t3.micro"),
        "subnetId": _ref(refs["subnet"]),
        "securityGroupIds": [_ref(refs["security_group"], "attrGroupId")],
        "tags": _tags(nid),
    })]


def _igw(nid, node, refs, ctx):
    return [
        _decl(nid, "ec2.CfnInternetGateway", {"tags": _tags(nid)}),
        _decl(nid + "_attach", "ec2.CfnVPCGatewayAttachment", {
            "vpcId": _ref(refs["vpc"]), "internetGatewayId": _ref(nid),
        }),
    ]


def _nat_gateway(nid, node, refs, ctx):
    eip = nid + "_eip"
    return [
        _decl(eip, "ec2.CfnEIP", {"domain": "vpc", "tags": _tags(nid)}),
        _decl(nid, "ec2.CfnNatGateway", {
            "subnetId": _ref(refs["subnet"]),
            "allocationId": _ref(eip, "attrAllocationId"),
            "tags": _tags(nid),
        }),
    ]


def _route_table(nid, node, refs, ctx):
    out = [_decl(nid, "ec2.CfnRouteTable", {"vpcId": _ref(refs["vpc"]), "tags": _tags(nid)})]
    for i, sub in enumerate(_listify(refs["subnets"])):
        out.append(_decl(f"{nid}_assoc{i}", "ec2.CfnSubnetRouteTableAssociation", {
            "subnetId": _ref(sub), "routeTableId": _ref(nid),
        }))
    return out


def _s3_bucket(nid, node, refs, ctx):
    props = {"tags": _tags(nid)}
    if node["props"].get("bucket_name"):
        props["bucketName"] = re.sub(r"[^a-z0-9.-]", "-", node["props"]["bucket_name"].lower())
    if node["props"].get("versioning"):
        props["versioningConfiguration"] = {"status": "Enabled"}
    return [_decl(nid, "s3.CfnBucket", props)]


def _iam_role(nid, node, refs, ctx):
    svc = node["props"].get("service", "ec2.amazonaws.com")
    return [_decl(nid, "iam.CfnRole", {
        "assumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [
            {"Effect": "Allow", "Principal": {"Service": svc}, "Action": "sts:AssumeRole"},
        ]},
        "tags": _tags(nid),
    })]


def _alb(nid, node, refs, ctx):
    return [_decl(nid, "elbv2.CfnLoadBalancer", {
        "type": "application",
        "subnets": _refs(refs["subnets"]),
        "securityGroups": [_ref(refs["security_group"], "attrGroupId")],
        "tags": _tags(nid),
    })]


def _target_group(nid, node, refs, ctx):
    p = node["props"]
    return [_decl(nid, "elbv2.CfnTargetGroup", {
        "port": p.get("port", 80), "protocol": p.get("protocol", "HTTP"),
        "vpcId": _ref(refs["vpc"]), "targetType": "instance", "healthCheckPath": p.get("health_check_path", "/"),
    })]


def _rds(nid, node, refs, ctx):
    p = node["props"]
    group = nid + "_subnets"
    return [
        _decl(group, "rds.CfnDBSubnetGroup", {
            "dbSubnetGroupDescription": f"Subnets for {nid}", "subnetIds": _refs(refs["subnets"]),
        }),
        _decl(nid, "rds.CfnDBInstance", {
            "engine": p.get("engine", "postgres"),
            "dbInstanceClass": p.get("instance_class", "db.t3.micro"),
            "allocatedStorage": str(p.get("storage", 20)),
            "masterUsername": p.get("username", "appadmin"),
            "masterUserPassword": Expr("dbPassword"),
            "dbSubnetGroupName": _ref(group),
            "publiclyAccessible": False,
        }),
    ]


def _dynamodb(nid, node, refs, ctx):
    hk = node["props"].get("hash_key", "id")
    return [_decl(nid, "dynamodb.CfnTable", {
        "billingMode": "PAY_PER_REQUEST",
        "attributeDefinitions": [{"attributeName": hk, "attributeType": "S"}],
        "keySchema": [{"attributeName": hk, "keyType": "HASH"}],
    })]


def _sqs(nid, node, refs, ctx):
    return [_decl(nid, "sqs.CfnQueue", {"tags": _tags(nid)})]


def _sns(nid, node, refs, ctx):
    return [_decl(nid, "sns.CfnTopic", {"tags": _tags(nid)})]


def _cloudwatch(nid, node, refs, ctx):
    return [_decl(nid, "logs.CfnLogGroup", {"retentionInDays": node["props"].get("retention_days", 30)})]


CDK_BUILDERS = {
    "vpc": _vpc, "subnet": _subnet, "security_group": _security_group, "ec2_instance": _ec2_instance,
    "igw": _igw, "nat_gateway": _nat_gateway, "route_table": _route_table, "s3_bucket": _s3_bucket,
    "iam_role": _iam_role, "alb": _alb, "target_group": _target_group, "rds": _rds,
    "dynamodb": _dynamodb, "sqs": _sqs, "sns": _sns, "cloudwatch": _cloudwatch,
}

_IMPORTS = {
    "ec2": "aws-cdk-lib/aws-ec2", "s3": "aws-cdk-lib/aws-s3", "iam": "aws-cdk-lib/aws-iam",
    "elbv2": "aws-cdk-lib/aws-elasticloadbalancingv2", "rds": "aws-cdk-lib/aws-rds",
    "dynamodb": "aws-cdk-lib/aws-dynamodb", "sqs": "aws-cdk-lib/aws-sqs", "sns": "aws-cdk-lib/aws-sns",
    "logs": "aws-cdk-lib/aws-logs",
}


def compile_cdk(ir: dict) -> dict:
    """Compile an IR design into an AWS CDK (TypeScript) project ({path: content})."""
    validate(ir)
    nodes = {n["id"]: n for n in ir["nodes"]}
    ctx = {"region": ir["region"], "name": ir["name"]}
    statements: list = []
    unmapped: list = []
    for nid in _topo_sort(ir["nodes"]):
        node = nodes[nid]
        builder = CDK_BUILDERS.get(node["type"])
        if builder is None:
            unmapped.append(node["type"])
            continue
        statements.extend(builder(nid, node, node.get("inputs", {}), ctx))

    body = "\n".join(statements)
    imports = [f'import * as {alias} from "{module}";' for alias, module in _IMPORTS.items() if f"{alias}." in body]
    consts = []
    if "defaultAmi" in body:
        consts.append('    const defaultAmi = "ami-0c55b159cbfafe1f0"; // override for your region')
    if "dbPassword" in body:
        consts.append('    const dbPassword = "CHANGE_ME"; // use Secrets Manager in real use')
    const_block = ("\n".join(consts) + "\n") if consts else ""

    stack = (
        'import { Stack, StackProps } from "aws-cdk-lib";\n'
        'import { Construct } from "constructs";\n'
        + ("\n".join(imports) + "\n" if imports else "")
        + "\nexport class NeviriStack extends Stack {\n"
        "  constructor(scope: Construct, id: string, props?: StackProps) {\n"
        "    super(scope, id, props);\n"
        + const_block + body + "\n  }\n}\n"
    )
    project = re.sub(r"[^a-zA-Z0-9-]", "-", ir["name"])
    app = (
        'import { App } from "aws-cdk-lib";\n'
        'import { NeviriStack } from "../lib/stack";\n\n'
        f'const app = new App();\nnew NeviriStack(app, "{project}");\n'
    )
    return normalize_files({
        "lib/stack.ts": stack,
        "bin/app.ts": app,
        "cdk.json": json.dumps({"app": "npx ts-node --prefer-ts-exts bin/app.ts"}, indent=2) + "\n",
        "package.json": json.dumps({
            "name": project, "bin": {project: "bin/app.ts"},
            "dependencies": {"aws-cdk-lib": "^2.150.0", "constructs": "^10.0.0"},
            "devDependencies": {"aws-cdk": "^2.150.0", "ts-node": "^10.9.0", "typescript": "^5.4.0"},
        }, indent=2) + "\n",
        "tsconfig.json": json.dumps({
            "compilerOptions": {"target": "ES2020", "module": "commonjs", "strict": True, "esModuleInterop": True},
        }, indent=2) + "\n",
        ".gitignore": "node_modules/\ncdk.out/\n*.js\n",
        "README.md": _readme(ir, unmapped),
    })


def _readme(ir: dict, unmapped: list) -> str:
    lines = [
        f"# {ir['name']} - AWS CDK (TypeScript)",
        "",
        f"Region: {ir['region']}",
        "",
        "## Run",
        "```bash",
        "npm install",
        "npx cdk synth",
        "npx cdk deploy",
        "```",
    ]
    if unmapped:
        lines += ["", "## Not yet mapped", "", "These designed components have no CDK mapping yet and were skipped:", ""]
        lines += [f"- `{u}`" for u in sorted(set(unmapped))]
    return "\n".join(lines) + "\n"
