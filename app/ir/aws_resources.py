"""Canonical AWS resource mappings: IR block -> provider-neutral Resource(s).

Shared by every AWS-family target (Terraform, CloudFormation, Pulumi, CDK). Each
mapper returns a list of Resources; the FIRST is the block's primary resource (the
one other nodes reference). References to other nodes use Ref(); references to a
sibling resource in the same block use LocalRef().
"""

from app.ir.canonical import Block, LocalRef, Raw, Ref, Resource, register


def _tags(node: dict, **extra) -> dict:
    return {"Name": node["id"], "ManagedBy": "neviri-ansi", **extra}


def _as_list(value) -> list:
    return value if isinstance(value, list) else [value]


@register("vpc")
def vpc(node, refs, ctx):
    return [Resource("aws_vpc", node["id"], {
        "cidr_block": node["props"].get("cidr", "10.0.0.0/16"),
        "enable_dns_support": True,
        "enable_dns_hostnames": True,
        "tags": _tags(node),
    })]


@register("subnet")
def subnet(node, refs, ctx):
    p = node["props"]
    attrs = {"vpc_id": Ref(refs["vpc"]), "cidr_block": p.get("cidr", "10.0.1.0/24"), "tags": _tags(node)}
    if p.get("az"):
        attrs["availability_zone"] = p["az"]
    if p.get("public"):
        attrs["map_public_ip_on_launch"] = True
    return [Resource("aws_subnet", node["id"], attrs)]


@register("security_group")
def security_group(node, refs, ctx):
    p = node["props"]
    ingress = []
    if p.get("ssh_cidr"):
        ingress.append(Block("ingress", {"from_port": 22, "to_port": 22, "protocol": "tcp", "cidr_blocks": [p["ssh_cidr"]]}))
    if p.get("allow_http"):
        ingress.append(Block("ingress", {"from_port": 80, "to_port": 80, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"]}))
    if p.get("allow_https"):
        ingress.append(Block("ingress", {"from_port": 443, "to_port": 443, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"]}))
    return [Resource("aws_security_group", node["id"], {
        "name": p.get("name", node["id"]),
        "description": p.get("description", node["id"]),
        "vpc_id": Ref(refs["vpc"]),
        "ingress": ingress,
        "egress": [Block("egress", {"from_port": 0, "to_port": 0, "protocol": "-1", "cidr_blocks": ["0.0.0.0/0"]})],
        "tags": _tags(node),
    })]


@register("ec2_instance")
def ec2_instance(node, refs, ctx):
    p = node["props"]
    attrs = {
        "ami": p["ami"] if p.get("ami") else Raw("var.default_ami"),
        "instance_type": p.get("instance_type", "t3.micro"),
        "subnet_id": Ref(refs["subnet"]),
        "vpc_security_group_ids": [Ref(refs["security_group"])],
        "tags": _tags(node),
    }
    if p.get("public"):
        attrs["associate_public_ip_address"] = True
    return [Resource("aws_instance", node["id"], attrs)]


@register("igw")
def igw(node, refs, ctx):
    return [Resource("aws_internet_gateway", node["id"], {"vpc_id": Ref(refs["vpc"]), "tags": _tags(node)})]


@register("nat_gateway")
def nat_gateway(node, refs, ctx):
    eip = f"{node['id']}_eip"
    return [
        Resource("aws_nat_gateway", node["id"], {
            "subnet_id": Ref(refs["subnet"]),
            "allocation_id": LocalRef("aws_eip", eip, "id"),
            "tags": _tags(node),
        }),
        Resource("aws_eip", eip, {"domain": "vpc", "tags": _tags(node)}),
    ]


@register("route_table")
def route_table(node, refs, ctx):
    out = [Resource("aws_route_table", node["id"], {"vpc_id": Ref(refs["vpc"]), "tags": _tags(node)})]
    for i, sub in enumerate(_as_list(refs["subnets"])):
        out.append(Resource("aws_route_table_association", f"{node['id']}_assoc{i}", {
            "subnet_id": Ref(sub),
            "route_table_id": LocalRef("aws_route_table", node["id"], "id"),
        }))
    return out


@register("s3_bucket")
def s3_bucket(node, refs, ctx):
    out = [Resource("aws_s3_bucket", node["id"], {"bucket": node["props"].get("bucket_name", node["id"]), "tags": _tags(node)})]
    if node["props"].get("versioning"):
        out.append(Resource("aws_s3_bucket_versioning", f"{node['id']}_versioning", {
            "bucket": LocalRef("aws_s3_bucket", node["id"], "id"),
            "versioning_configuration": Block("versioning_configuration", {"status": "Enabled"}),
        }))
    return out


@register("s3_website")
def s3_website(node, refs, ctx):
    p = node["props"]
    return [Resource("aws_s3_bucket_website_configuration", node["id"], {
        "bucket": Ref(refs["bucket"]),
        "index_document": Block("index_document", {"suffix": p.get("index_document", "index.html")}),
        "error_document": Block("error_document", {"key": p.get("error_document", "error.html")}),
    })]


@register("iam_role")
def iam_role(node, refs, ctx):
    service = node["props"].get("service", "ec2.amazonaws.com")
    policy = (
        'jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", '
        'Principal = { Service = "' + service + '" }, Action = "sts:AssumeRole" }] })'
    )
    return [Resource("aws_iam_role", node["id"], {
        "name": node["props"].get("name", node["id"]),
        "assume_role_policy": Raw(policy),
        "tags": _tags(node),
    })]


@register("launch_template")
def launch_template(node, refs, ctx):
    p = node["props"]
    return [Resource("aws_launch_template", node["id"], {
        "name": p.get("name", node["id"]),
        "image_id": p["ami"] if p.get("ami") else Raw("var.default_ami"),
        "instance_type": p.get("instance_type", "t3.micro"),
    })]


@register("lambda")
def lambda_fn(node, refs, ctx):
    p = node["props"]
    return [Resource("aws_lambda_function", node["id"], {
        "function_name": p.get("name", node["id"]),
        "runtime": p.get("runtime", "python3.12"),
        "handler": p.get("handler", "app.handler"),
        "role": p["role_arn"] if p.get("role_arn") else Raw("var.lambda_role_arn"),
        "filename": p.get("zip_file", "function.zip"),
    })]


@register("dynamodb")
def dynamodb(node, refs, ctx):
    hash_key = node["props"].get("hash_key", "id")
    return [Resource("aws_dynamodb_table", node["id"], {
        "name": node["props"].get("table_name", node["id"]),
        "billing_mode": "PAY_PER_REQUEST",
        "hash_key": hash_key,
        "attribute": Block("attribute", {"name": hash_key, "type": "S"}),
        "tags": _tags(node),
    })]


@register("kms_key")
def kms_key(node, refs, ctx):
    return [
        Resource("aws_kms_key", node["id"], {"description": node["props"].get("description", node["id"]), "tags": _tags(node)}),
        Resource("aws_kms_alias", f"{node['id']}_alias", {
            "name": "alias/" + node["props"].get("alias", node["id"]),
            "target_key_id": LocalRef("aws_kms_key", node["id"], "id"),
        }),
    ]


@register("sqs")
def sqs(node, refs, ctx):
    return [Resource("aws_sqs_queue", node["id"], {"name": node["props"].get("name", node["id"]), "tags": _tags(node)})]


@register("sns")
def sns(node, refs, ctx):
    return [Resource("aws_sns_topic", node["id"], {"name": node["props"].get("name", node["id"]), "tags": _tags(node)})]


@register("cloudwatch")
def cloudwatch(node, refs, ctx):
    return [Resource("aws_cloudwatch_log_group", node["id"], {
        "name": node["props"].get("name", "/neviri-ansi/" + node["id"]),
        "retention_in_days": node["props"].get("retention_days", 30),
        "tags": _tags(node),
    })]


@register("alb")
def alb(node, refs, ctx):
    return [Resource("aws_lb", node["id"], {
        "name": node["props"].get("name", node["id"]),
        "internal": False,
        "load_balancer_type": "application",
        "security_groups": [Ref(refs["security_group"])],
        "subnets": [Ref(s) for s in _as_list(refs["subnets"])],
        "tags": _tags(node),
    })]


@register("target_group")
def target_group(node, refs, ctx):
    p = node["props"]
    return [Resource("aws_lb_target_group", node["id"], {
        "name": p.get("name", node["id"]),
        "port": p.get("port", 80),
        "protocol": p.get("protocol", "HTTP"),
        "vpc_id": Ref(refs["vpc"]),
        "target_type": "instance",
        "health_check": Block("health_check", {"path": p.get("health_check_path", "/"), "protocol": "HTTP"}),
        "tags": _tags(node),
    })]


@register("rds")
def rds(node, refs, ctx):
    p = node["props"]
    group = f"{node['id']}_subnets"
    return [
        Resource("aws_db_instance", node["id"], {
            "identifier": node["id"],
            "engine": p.get("engine", "postgres"),
            "instance_class": p.get("instance_class", "db.t3.micro"),
            "allocated_storage": p.get("storage", 20),
            "username": p.get("username", "appadmin"),
            "password": Raw("var.db_password"),
            "db_subnet_group_name": LocalRef("aws_db_subnet_group", group, "name"),
            "publicly_accessible": False,
            "skip_final_snapshot": True,
            "tags": _tags(node),
        }),
        Resource("aws_db_subnet_group", group, {
            "name": group,
            "subnet_ids": [Ref(s) for s in _as_list(refs["subnets"])],
            "tags": _tags(node),
        }),
    ]
