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


@register("eks_cluster")
def eks_cluster(node, refs, ctx):
    vpc_cfg = {"subnet_ids": [Ref(s) for s in _as_list(refs["subnets"])]}
    if "security_group" in refs:
        vpc_cfg["security_group_ids"] = [Ref(s) for s in _as_list(refs["security_group"])]
    return [Resource("aws_eks_cluster", node["id"], {
        "name": node["props"].get("name", node["id"]),
        "role_arn": node["props"].get("role_arn", "arn:aws:iam::000000000000:role/eks-cluster"),
        "vpc_config": Block("vpc_config", vpc_cfg),
        "tags": _tags(node),
    })]


@register("eks_nodegroup")
def eks_nodegroup(node, refs, ctx):
    p = node["props"]
    return [Resource("aws_eks_node_group", node["id"], {
        "cluster_name": p.get("cluster_name", "cluster"),
        "node_group_name": p.get("name", node["id"]),
        "node_role_arn": p.get("node_role_arn", "arn:aws:iam::000000000000:role/eks-node"),
        "subnet_ids": [Ref(s) for s in _as_list(refs["subnets"])],
        "scaling_config": Block("scaling_config", {
            "desired_size": p.get("desired_size", 2),
            "max_size": p.get("max_size", 4),
            "min_size": p.get("min_size", 1),
        }),
        "tags": _tags(node),
    })]


@register("transit_gateway")
def transit_gateway(node, refs, ctx):
    return [Resource("aws_ec2_transit_gateway", node["id"], {
        "description": node["props"].get("description", node["id"]),
        "tags": _tags(node),
    })]


@register("vpn_gateway")
def vpn_gateway(node, refs, ctx):
    return [Resource("aws_vpn_gateway", node["id"], {"vpc_id": Ref(refs["vpc"]), "tags": _tags(node)})]


@register("cloudtrail")
def cloudtrail(node, refs, ctx):
    return [Resource("aws_cloudtrail", node["id"], {
        "name": node["props"].get("name", node["id"]),
        "s3_bucket_name": node["props"].get("bucket_name", "audit-logs"),
        "is_multi_region_trail": True,
    })]


@register("api_gateway")
def api_gateway(node, refs, ctx):
    return [Resource("aws_apigatewayv2_api", node["id"], {
        "name": node["props"].get("name", node["id"]),
        "protocol_type": "HTTP",
        "tags": _tags(node),
    })]


@register("eventbridge")
def eventbridge(node, refs, ctx):
    return [Resource("aws_cloudwatch_event_rule", node["id"], {
        "name": node["props"].get("name", node["id"]),
        "schedule_expression": node["props"].get("schedule", "rate(5 minutes)"),
        "tags": _tags(node),
    })]


@register("vpc_endpoint")
def vpc_endpoint(node, refs, ctx):
    return [Resource("aws_vpc_endpoint", node["id"], {
        "vpc_id": Ref(refs["vpc"]),
        "service_name": node["props"].get("service", f"com.amazonaws.{ctx['region']}.ssm"),
        "vpc_endpoint_type": node["props"].get("endpoint_type", "Interface"),
        "tags": _tags(node),
    })]


@register("ecs_cluster")
def ecs_cluster(node, refs, ctx):
    return [Resource("aws_ecs_cluster", node["id"], {"name": node["props"].get("name", node["id"]), "tags": _tags(node)})]


@register("ecs_service")
def ecs_service(node, refs, ctx):
    p = node["props"]
    name = node["id"]
    task = f"{name}_task"
    container = (
        'jsonencode([{ name = "' + name + '-app", image = "'
        + p.get("image", "public.ecr.aws/nginx/nginx:latest")
        + '", essential = true, portMappings = [{ containerPort = '
        + str(p.get("container_port", 80)) + ', protocol = "tcp" }] }])'
    )
    return [
        Resource("aws_ecs_service", name, {
            "name": f"{name}-svc",
            "cluster": Ref(refs["cluster"], "arn"),
            "task_definition": LocalRef("aws_ecs_task_definition", task, "arn"),
            "desired_count": p.get("desired_count", 2),
            "launch_type": "FARGATE",
            "network_configuration": Block("network_configuration", {
                "subnets": [Ref(s) for s in _as_list(refs["subnets"])],
                "assign_public_ip": False,
            }),
        }),
        Resource("aws_ecs_task_definition", task, {
            "family": f"{name}-task",
            "requires_compatibilities": ["FARGATE"],
            "network_mode": "awsvpc",
            "cpu": p.get("cpu", "512"),
            "memory": p.get("memory", "1024"),
            "execution_role_arn": p.get("execution_role_arn", "arn:aws:iam::000000000000:role/ecsTaskExecutionRole"),
            "container_definitions": Raw(container),
        }),
    ]


@register("cloudfront")
def cloudfront(node, refs, ctx):
    p = node["props"]
    origin_id = f"origin-{node['id']}"
    return [Resource("aws_cloudfront_distribution", node["id"], {
        "enabled": True,
        "default_root_object": p.get("index_document", "index.html"),
        "origin": Block("origin", {
            "domain_name": p.get("origin_domain", "example-bucket.s3.amazonaws.com"),
            "origin_id": origin_id,
        }),
        "default_cache_behavior": Block("default_cache_behavior", {
            "allowed_methods": ["GET", "HEAD"],
            "cached_methods": ["GET", "HEAD"],
            "target_origin_id": origin_id,
            "viewer_protocol_policy": "redirect-to-https",
            "forwarded_values": Block("forwarded_values", {
                "query_string": False,
                "cookies": Block("cookies", {"forward": "none"}),
            }),
        }),
        "restrictions": Block("restrictions", {
            "geo_restriction": Block("geo_restriction", {"restriction_type": "none"}),
        }),
        "viewer_certificate": Block("viewer_certificate", {"cloudfront_default_certificate": True}),
        "tags": _tags(node),
    })]


@register("glue_crawler")
def glue_crawler(node, refs, ctx):
    p = node["props"]
    return [Resource("aws_glue_crawler", node["id"], {
        "name": p.get("name", node["id"]),
        "database_name": p.get("database", "analytics_db"),
        "role": p.get("role_arn", "arn:aws:iam::000000000000:role/GlueServiceRole"),
        "s3_target": Block("s3_target", {"path": p.get("s3_path", "s3://my-bucket/")}),
    })]


@register("glue_job")
def glue_job(node, refs, ctx):
    p = node["props"]
    return [Resource("aws_glue_job", node["id"], {
        "name": p.get("name", node["id"]),
        "role_arn": p.get("role_arn", "arn:aws:iam::000000000000:role/GlueServiceRole"),
        "command": Block("command", {
            "name": "glueetl",
            "script_location": p.get("script_location", "s3://my-bucket/etl.py"),
        }),
    })]


@register("backup_vault")
def backup_vault(node, refs, ctx):
    return [Resource("aws_backup_vault", node["id"], {"name": node["props"].get("name", node["id"]), "tags": _tags(node)})]


@register("backup_plan")
def backup_plan(node, refs, ctx):
    p = node["props"]
    return [Resource("aws_backup_plan", node["id"], {
        "name": p.get("name", node["id"]),
        "rule": Block("rule", {
            "rule_name": "daily",
            "target_vault_name": p.get("vault", "Default"),
            "schedule": p.get("schedule", "cron(0 5 * * ? *)"),
        }),
        "tags": _tags(node),
    })]


@register("backup_selection")
def backup_selection(node, refs, ctx):
    p = node["props"]
    return [Resource("aws_backup_selection", node["id"], {
        "name": p.get("name", node["id"]),
        "plan_id": p.get("plan_id", "PLAN_ID"),
        "iam_role_arn": p.get("role_arn", "arn:aws:iam::000000000000:role/BackupServiceRole"),
        "selection_tag": Block("selection_tag", {"type": "STRINGEQUALS", "key": "Backup", "value": "true"}),
    })]


@register("waf")
def waf(node, refs, ctx):
    return [Resource("aws_wafv2_web_acl", node["id"], {
        "name": node["props"].get("name", node["id"]),
        "scope": "REGIONAL",
        "default_action": Block("default_action", {"allow": Block("allow", {})}),
        "visibility_config": Block("visibility_config", {
            "cloudwatch_metrics_enabled": True,
            "metric_name": node["id"],
            "sampled_requests_enabled": True,
        }),
        "tags": _tags(node),
    })]


@register("datacenter")
def datacenter(node, refs, ctx):
    return []  # on-prem marker (diagram-only) — no AWS resource
