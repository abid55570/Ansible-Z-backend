"""CloudFormation target: compile an IR design into an AWS CloudFormation template (JSON).

CloudFormation is structurally distinct enough from Terraform (intrinsic Ref/GetAtt,
KeyValue tag lists, explicit gateway attachments, Parameters for secrets) that it gets
its own per-block builders rather than translating the Terraform model. Each builder
returns a list of (logical_id, resource_dict); the block's FIRST logical id is the one
other nodes reference via {"Ref": ...}. Blocks without a builder are reported as unmapped.
"""

import json
import re

from app.ir.compiler import _topo_sort, validate
from app.services.projectfmt import normalize_files


def _lid(node_id: str) -> str:
    """A CloudFormation logical id (alphanumeric only)."""
    return re.sub(r"[^A-Za-z0-9]", "", node_id) or "R"


def _ref(node_id: str) -> dict:
    return {"Ref": _lid(node_id)}


def _listify(value) -> list:
    return value if isinstance(value, list) else [value]


def _refs(value) -> list:
    return [_ref(v) for v in _listify(value)]


def _tags(node_id: str) -> list:
    return [{"Key": "Name", "Value": node_id}, {"Key": "ManagedBy", "Value": "neviri-ansi"}]


def _bucket_name(name: str) -> str:
    return re.sub(r"[^a-z0-9.-]", "-", name.lower())


def _vpc(nid, node, refs, ctx):
    return [(_lid(nid), {"Type": "AWS::EC2::VPC", "Properties": {
        "CidrBlock": node["props"].get("cidr", "10.0.0.0/16"),
        "EnableDnsSupport": True, "EnableDnsHostnames": True, "Tags": _tags(nid),
    }})]


def _subnet(nid, node, refs, ctx):
    p = node["props"]
    props = {"VpcId": _ref(refs["vpc"]), "CidrBlock": p.get("cidr", "10.0.1.0/24"), "Tags": _tags(nid)}
    if p.get("az"):
        props["AvailabilityZone"] = p["az"]
    if p.get("public"):
        props["MapPublicIpOnLaunch"] = True
    return [(_lid(nid), {"Type": "AWS::EC2::Subnet", "Properties": props})]


def _security_group(nid, node, refs, ctx):
    p = node["props"]
    ingress = []
    if p.get("ssh_cidr"):
        ingress.append({"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "CidrIp": p["ssh_cidr"]})
    if p.get("allow_http"):
        ingress.append({"IpProtocol": "tcp", "FromPort": 80, "ToPort": 80, "CidrIp": "0.0.0.0/0"})
    if p.get("allow_https"):
        ingress.append({"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "CidrIp": "0.0.0.0/0"})
    props = {"GroupDescription": p.get("description", nid), "VpcId": _ref(refs["vpc"]), "Tags": _tags(nid)}
    if ingress:
        props["SecurityGroupIngress"] = ingress
    return [(_lid(nid), {"Type": "AWS::EC2::SecurityGroup", "Properties": props})]


def _ec2_instance(nid, node, refs, ctx):
    p = node["props"]
    return [(_lid(nid), {"Type": "AWS::EC2::Instance", "Properties": {
        "InstanceType": p.get("instance_type", "t3.micro"),
        "ImageId": p["ami"] if p.get("ami") else {"Ref": "DefaultAmi"},
        "SubnetId": _ref(refs["subnet"]),
        "SecurityGroupIds": [_ref(refs["security_group"])],
        "Tags": _tags(nid),
    }})]


def _igw(nid, node, refs, ctx):
    return [
        (_lid(nid), {"Type": "AWS::EC2::InternetGateway", "Properties": {"Tags": _tags(nid)}}),
        (_lid(nid) + "Attach", {"Type": "AWS::EC2::VPCGatewayAttachment", "Properties": {
            "VpcId": _ref(refs["vpc"]), "InternetGatewayId": _ref(nid),
        }}),
    ]


def _nat_gateway(nid, node, refs, ctx):
    eip = _lid(nid) + "Eip"
    return [
        (_lid(nid), {"Type": "AWS::EC2::NatGateway", "Properties": {
            "SubnetId": _ref(refs["subnet"]),
            "AllocationId": {"Fn::GetAtt": [eip, "AllocationId"]},
            "Tags": _tags(nid),
        }}),
        (eip, {"Type": "AWS::EC2::EIP", "Properties": {"Domain": "vpc"}}),
    ]


def _route_table(nid, node, refs, ctx):
    out = [(_lid(nid), {"Type": "AWS::EC2::RouteTable", "Properties": {"VpcId": _ref(refs["vpc"]), "Tags": _tags(nid)}})]
    for i, sub in enumerate(_listify(refs["subnets"])):
        out.append((_lid(nid) + f"Assoc{i}", {"Type": "AWS::EC2::SubnetRouteTableAssociation", "Properties": {
            "SubnetId": _ref(sub), "RouteTableId": _ref(nid),
        }}))
    return out


def _s3_bucket(nid, node, refs, ctx):
    props = {"BucketName": _bucket_name(node["props"].get("bucket_name", nid)), "Tags": _tags(nid)}
    if node["props"].get("versioning"):
        props["VersioningConfiguration"] = {"Status": "Enabled"}
    return [(_lid(nid), {"Type": "AWS::S3::Bucket", "Properties": props})]


def _iam_role(nid, node, refs, ctx):
    svc = node["props"].get("service", "ec2.amazonaws.com")
    return [(_lid(nid), {"Type": "AWS::IAM::Role", "Properties": {
        "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [
            {"Effect": "Allow", "Principal": {"Service": svc}, "Action": "sts:AssumeRole"},
        ]},
        "Tags": _tags(nid),
    }})]


def _alb(nid, node, refs, ctx):
    return [(_lid(nid), {"Type": "AWS::ElasticLoadBalancingV2::LoadBalancer", "Properties": {
        "Type": "application",
        "Subnets": _refs(refs["subnets"]),
        "SecurityGroups": [_ref(refs["security_group"])],
        "Tags": _tags(nid),
    }})]


def _target_group(nid, node, refs, ctx):
    p = node["props"]
    return [(_lid(nid), {"Type": "AWS::ElasticLoadBalancingV2::TargetGroup", "Properties": {
        "Port": p.get("port", 80), "Protocol": p.get("protocol", "HTTP"),
        "VpcId": _ref(refs["vpc"]), "TargetType": "instance", "HealthCheckPath": p.get("health_check_path", "/"),
    }})]


def _rds(nid, node, refs, ctx):
    p = node["props"]
    group = _lid(nid) + "Subnets"
    return [
        (_lid(nid), {"Type": "AWS::RDS::DBInstance", "Properties": {
            "Engine": p.get("engine", "postgres"),
            "DBInstanceClass": p.get("instance_class", "db.t3.micro"),
            "AllocatedStorage": str(p.get("storage", 20)),
            "MasterUsername": p.get("username", "appadmin"),
            "MasterUserPassword": {"Ref": "DbPassword"},
            "DBSubnetGroupName": _ref(group),
            "PubliclyAccessible": False,
        }}),
        (group, {"Type": "AWS::RDS::DBSubnetGroup", "Properties": {
            "DBSubnetGroupDescription": f"Subnets for {nid}", "SubnetIds": _refs(refs["subnets"]),
        }}),
    ]


def _dynamodb(nid, node, refs, ctx):
    hk = node["props"].get("hash_key", "id")
    return [(_lid(nid), {"Type": "AWS::DynamoDB::Table", "Properties": {
        "TableName": node["props"].get("table_name", nid),
        "BillingMode": "PAY_PER_REQUEST",
        "AttributeDefinitions": [{"AttributeName": hk, "AttributeType": "S"}],
        "KeySchema": [{"AttributeName": hk, "KeyType": "HASH"}],
    }})]


def _sqs(nid, node, refs, ctx):
    return [(_lid(nid), {"Type": "AWS::SQS::Queue", "Properties": {"QueueName": node["props"].get("name", nid)}})]


def _sns(nid, node, refs, ctx):
    return [(_lid(nid), {"Type": "AWS::SNS::Topic", "Properties": {"TopicName": node["props"].get("name", nid)}})]


def _cloudwatch(nid, node, refs, ctx):
    return [(_lid(nid), {"Type": "AWS::Logs::LogGroup", "Properties": {
        "LogGroupName": node["props"].get("name", "/neviri-ansi/" + nid),
        "RetentionInDays": node["props"].get("retention_days", 30),
    }})]


CFN_BUILDERS = {
    "vpc": _vpc, "subnet": _subnet, "security_group": _security_group, "ec2_instance": _ec2_instance,
    "igw": _igw, "nat_gateway": _nat_gateway, "route_table": _route_table, "s3_bucket": _s3_bucket,
    "iam_role": _iam_role, "alb": _alb, "target_group": _target_group, "rds": _rds,
    "dynamodb": _dynamodb, "sqs": _sqs, "sns": _sns, "cloudwatch": _cloudwatch,
}


def compile_cloudformation(ir: dict) -> dict:
    """Compile an IR design into a CloudFormation project ({path: content})."""
    validate(ir)
    nodes = {n["id"]: n for n in ir["nodes"]}
    ctx = {"region": ir["region"], "name": ir["name"]}
    resources: dict = {}
    unmapped: list = []
    for nid in _topo_sort(ir["nodes"]):
        node = nodes[nid]
        builder = CFN_BUILDERS.get(node["type"])
        if builder is None:
            unmapped.append(node["type"])
            continue
        for logical_id, resource in builder(nid, node, node.get("inputs", {}), ctx):
            resources[logical_id] = resource

    template = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": f"{ir['name']} - generated by Neviri-Ansi (CloudFormation)",
        "Resources": resources,
    }
    blob = json.dumps(resources)
    params = {}
    if '"DefaultAmi"' in blob:
        params["DefaultAmi"] = {"Type": "AWS::EC2::Image::Id", "Description": "AMI id for EC2 instances"}
    if '"DbPassword"' in blob:
        params["DbPassword"] = {"Type": "String", "NoEcho": True, "Description": "RDS master password"}
    if params:
        template = {**template, "Parameters": params, "Resources": resources}

    return normalize_files({
        "template.json": json.dumps(template, indent=2) + "\n",
        ".gitignore": "*.zip\npackaged.json\n",
        "README.md": _readme(ir, unmapped),
    })


def _readme(ir: dict, unmapped: list) -> str:
    lines = [
        f"# {ir['name']} - CloudFormation",
        "",
        f"Region: {ir['region']}",
        "",
        "## Deploy",
        "```bash",
        "aws cloudformation deploy \\",
        f"  --template-file template.json --stack-name {re.sub(r'[^a-zA-Z0-9-]', '-', ir['name'])} \\",
        "  --capabilities CAPABILITY_NAMED_IAM",
        "```",
    ]
    if unmapped:
        lines += ["", "## Not yet mapped", "", "These designed components have no CloudFormation mapping yet and were skipped:", ""]
        lines += [f"- `{u}`" for u in sorted(set(unmapped))]
    return "\n".join(lines) + "\n"
