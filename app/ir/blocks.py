"""The block library: one tested, parameterized Ansible fragment per infra primitive.

Each block declares:
  inputs   — port name -> {"type": <required block type>, "many": <bool>}
  required — required property names
  output   — the attribute path on the registered task result (how others reference it)
  render   — (node, refs, ctx) -> a task dict (or list of task dicts)

``refs`` maps each input port to a resolved Ansible expression (e.g. "{{ pub1_result.subnet.id }}")
or a list of them for ``many`` ports. ``ctx`` carries the region.
"""

TAGS = "{{ common_tags }}"


def _vpc(node, refs, ctx):
    return {
        "name": f"Create VPC: {node['id']}",
        "amazon.aws.ec2_vpc_net": {
            "name": node["props"].get("name", node["id"]),
            "cidr_block": node["props"]["cidr"],
            "region": ctx["region"],
            "tags": TAGS,
            "state": "present",
        },
    }


def _subnet(node, refs, ctx):
    return {
        "name": f"Create subnet: {node['id']}",
        "amazon.aws.ec2_vpc_subnet": {
            "vpc_id": refs["vpc"],
            "cidr": node["props"]["cidr"],
            "region": ctx["region"],
            "az": node["props"].get("az"),
            "map_public": node["props"].get("public", False),
            "tags": TAGS,
            "state": "present",
        },
    }


def _security_group(node, refs, ctx):
    props = node["props"]
    rules = []
    if props.get("ssh_cidr"):
        rules.append({"proto": "tcp", "ports": [22], "cidr_ip": props["ssh_cidr"]})
    if props.get("allow_http"):
        rules.append({"proto": "tcp", "ports": [80], "cidr_ip": "0.0.0.0/0"})
    if props.get("allow_https"):
        rules.append({"proto": "tcp", "ports": [443], "cidr_ip": "0.0.0.0/0"})
    return {
        "name": f"Security group: {node['id']}",
        "amazon.aws.ec2_security_group": {
            "name": props.get("name", node["id"]),
            "description": props.get("description", node["id"]),
            "vpc_id": refs["vpc"],
            "region": ctx["region"],
            "rules": rules,
            "tags": TAGS,
            "state": "present",
        },
    }


def _ec2_instance(node, refs, ctx):
    return {
        "name": f"Launch instance: {node['id']}",
        "amazon.aws.ec2_instance": {
            "name": node["props"].get("name", node["id"]),
            "region": ctx["region"],
            "instance_type": node["props"].get("instance_type", "t3.micro"),
            "image_id": node["props"].get("ami", "{{ default_ami }}"),
            "vpc_subnet_id": refs["subnet"],
            "security_groups": [refs["security_group"]],
            "network": {"assign_public_ip": node["props"].get("public", False)},
            "tags": TAGS,
            "state": "present",
        },
    }


def _alb(node, refs, ctx):
    return {
        "name": f"Create ALB: {node['id']}",
        "amazon.aws.elb_application_lb": {
            "name": node["props"].get("name", node["id"]),
            "region": ctx["region"],
            "subnets": refs["subnets"],
            "security_groups": [refs["security_group"]],
            "listeners": [
                {
                    "Protocol": "HTTP",
                    "Port": 80,
                    "DefaultActions": [
                        {"Type": "forward", "TargetGroupName": node["props"].get("target_group", f"{node['id']}-tg")}
                    ],
                }
            ],
            "state": "present",
        },
    }


def _rds(node, refs, ctx):
    subnet_group = f"{node['id']}-subnets"
    return [
        {
            "name": f"DB subnet group: {node['id']}",
            "amazon.aws.rds_subnet_group": {
                "name": subnet_group,
                "region": ctx["region"],
                "description": f"Subnets for {node['id']}",
                "subnets": refs["subnets"],
                "state": "present",
            },
        },
        {
            "name": f"Create RDS: {node['id']}",
            "amazon.aws.rds_instance": {
                "id": node["id"],
                "region": ctx["region"],
                "engine": node["props"].get("engine", "postgres"),
                "db_instance_class": node["props"].get("instance_class", "db.t3.micro"),
                "allocated_storage": node["props"].get("storage", 20),
                "master_username": node["props"].get("username", "appadmin"),
                "master_user_password": "{{ db_password | default('CHANGE_ME_IN_VAULT') }}",
                "db_subnet_group_name": subnet_group,
                "publicly_accessible": False,
                "state": "present",
            },
        },
    ]


def _igw(node, refs, ctx):
    return {
        "name": f"Internet gateway: {node['id']}",
        "amazon.aws.ec2_vpc_igw": {
            "vpc_id": refs["vpc"],
            "region": ctx["region"],
            "tags": TAGS,
            "state": "present",
        },
    }


def _nat_gateway(node, refs, ctx):
    return {
        "name": f"NAT gateway: {node['id']}",
        "amazon.aws.ec2_vpc_nat_gateway": {
            "subnet_id": refs["subnet"],
            "region": ctx["region"],
            "wait": True,
            "if_exist_do_not_create": True,
            "tags": TAGS,
            "state": "present",
        },
    }


def _route_table(node, refs, ctx):
    return {
        "name": f"Route table: {node['id']}",
        "amazon.aws.ec2_vpc_route_table": {
            "vpc_id": refs["vpc"],
            "region": ctx["region"],
            "subnets": refs["subnets"],
            "tags": TAGS,
            "state": "present",
        },
    }


def _s3_bucket(node, refs, ctx):
    return {
        "name": f"S3 bucket: {node['id']}",
        "amazon.aws.s3_bucket": {
            "name": node["props"].get("bucket_name", node["id"]),
            "region": ctx["region"],
            "versioning": node["props"].get("versioning", False),
            "tags": TAGS,
            "state": "present",
        },
    }


def _s3_website(node, refs, ctx):
    return {
        "name": f"S3 website: {node['id']}",
        "community.aws.s3_website": {
            "name": refs["bucket"],
            "suffix": node["props"].get("index_document", "index.html"),
            "error_key": node["props"].get("error_document", "error.html"),
            "state": "present",
        },
    }


def _target_group(node, refs, ctx):
    return {
        "name": f"Target group: {node['id']}",
        "community.aws.elb_target_group": {
            "name": node["props"].get("name", node["id"]),
            "region": ctx["region"],
            "protocol": node["props"].get("protocol", "HTTP"),
            "port": node["props"].get("port", 80),
            "vpc_id": refs["vpc"],
            "target_type": "instance",
            "health_check_path": node["props"].get("health_check_path", "/"),
            "state": "present",
        },
    }


def _launch_template(node, refs, ctx):
    return {
        "name": f"Launch template: {node['id']}",
        "amazon.aws.ec2_launch_template": {
            "name": node["props"].get("name", node["id"]),
            "region": ctx["region"],
            "instance_type": node["props"].get("instance_type", "t3.micro"),
            "image_id": node["props"].get("ami", "{{ default_ami }}"),
            "tags": TAGS,
        },
    }


def _lambda(node, refs, ctx):
    return {
        "name": f"Lambda function: {node['id']}",
        "amazon.aws.lambda": {
            "name": node["props"].get("name", node["id"]),
            "region": ctx["region"],
            "runtime": node["props"].get("runtime", "python3.12"),
            "handler": node["props"].get("handler", "app.handler"),
            "role": node["props"].get("role_arn", "arn:aws:iam::000000000000:role/lambda-exec"),
            "zip_file": node["props"].get("zip_file", "build/function.zip"),
            "state": "present",
        },
    }


def _dynamodb(node, refs, ctx):
    return {
        "name": f"DynamoDB table: {node['id']}",
        "community.aws.dynamodb_table": {
            "name": node["props"].get("table_name", node["id"]),
            "region": ctx["region"],
            "hash_key_name": node["props"].get("hash_key", "id"),
            "hash_key_type": "STRING",
            "billing_mode": "PAY_PER_REQUEST",
            "tags": TAGS,
            "state": "present",
        },
    }


def _kms_key(node, refs, ctx):
    return {
        "name": f"KMS key: {node['id']}",
        "amazon.aws.kms_key": {
            "alias": node["props"].get("alias", node["id"]),
            "region": ctx["region"],
            "description": node["props"].get("description", node["id"]),
            "tags": TAGS,
            "state": "present",
        },
    }


def _iam_role(node, refs, ctx):
    return {
        "name": f"IAM role: {node['id']}",
        "amazon.aws.iam_role": {
            "name": node["props"].get("name", node["id"]),
            "assume_role_policy_document": node["props"].get(
                "assume_role_policy",
                '{ "Version": "2012-10-17", "Statement": [{ "Effect": "Allow", '
                '"Principal": {"Service": "ec2.amazonaws.com"}, "Action": "sts:AssumeRole" }] }',
            ),
            "state": "present",
        },
    }


def _eks_cluster(node, refs, ctx):
    return {
        "name": f"EKS cluster: {node['id']}",
        "community.aws.eks_cluster": {
            "name": node["props"].get("name", node["id"]),
            "region": ctx["region"],
            "role_arn": node["props"].get("role_arn", "arn:aws:iam::000000000000:role/eks-cluster"),
            "subnets": refs["subnets"],
            "state": "present",
        },
    }


def _eks_nodegroup(node, refs, ctx):
    return {
        "name": f"EKS node group: {node['id']}",
        "community.aws.eks_nodegroup": {
            "name": node["props"].get("name", node["id"]),
            "cluster_name": node["props"].get("cluster_name", "cluster"),
            "region": ctx["region"],
            "node_role": node["props"].get("node_role_arn", "arn:aws:iam::000000000000:role/eks-node"),
            "subnets": refs["subnets"],
            "state": "present",
        },
    }


def _transit_gateway(node, refs, ctx):
    return {
        "name": f"Transit gateway: {node['id']}",
        "community.aws.ec2_transit_gateway": {
            "description": node["props"].get("description", node["id"]),
            "region": ctx["region"],
            "tags": TAGS,
            "state": "present",
        },
    }


def _vpn_gateway(node, refs, ctx):
    return {
        "name": f"VPN gateway: {node['id']}",
        "amazon.aws.ec2_vpc_vgw": {
            "name": node["props"].get("name", node["id"]),
            "vpc_id": refs["vpc"],
            "region": ctx["region"],
            "type": "ipsec.1",
            "tags": TAGS,
            "state": "present",
        },
    }


def _cloudtrail(node, refs, ctx):
    return {
        "name": f"CloudTrail: {node['id']}",
        "amazon.aws.cloudtrail": {
            "name": node["props"].get("name", node["id"]),
            "region": ctx["region"],
            "s3_bucket_name": node["props"].get("bucket_name", "audit-logs"),
            "is_multi_region_trail": True,
            "state": "present",
        },
    }


def _api_gateway(node, refs, ctx):
    return {
        "name": f"API gateway: {node['id']}",
        "community.aws.api_gateway": {
            "region": ctx["region"],
            "swagger_text": node["props"].get("swagger_text", "{}"),
            "stage": node["props"].get("stage", "prod"),
            "state": "present",
        },
    }


def _eventbridge(node, refs, ctx):
    return {
        "name": f"EventBridge rule: {node['id']}",
        "amazon.aws.cloudwatchevent_rule": {
            "name": node["props"].get("name", node["id"]),
            "region": ctx["region"],
            "schedule_expression": node["props"].get("schedule", "rate(5 minutes)"),
            "state": "present",
        },
    }


def _vpc_endpoint(node, refs, ctx):
    return {
        "name": f"VPC endpoint: {node['id']}",
        "amazon.aws.ec2_vpc_endpoint": {
            "vpc_id": refs["vpc"],
            "region": ctx["region"],
            "service": node["props"].get("service", "com.amazonaws." + ctx["region"] + ".ssm"),
            "vpc_endpoint_type": node["props"].get("endpoint_type", "Interface"),
            "state": "present",
        },
    }


def _ecs_cluster(node, refs, ctx):
    return {
        "name": f"ECS cluster: {node['id']}",
        "community.aws.ecs_cluster": {
            "name": node["props"].get("name", node["id"]),
            "region": ctx["region"],
            "state": "present",
        },
    }


def _ecs_service(node, refs, ctx):
    p = node["props"]
    name = node["id"]
    return [
        {
            "name": f"ECS task definition: {name}",
            "community.aws.ecs_taskdefinition": {
                "family": f"{name}-task",
                "region": ctx["region"],
                "launch_type": "FARGATE",
                "network_mode": "awsvpc",
                "cpu": p.get("cpu", "512"),
                "memory": p.get("memory", "1024"),
                "execution_role_arn": p.get(
                    "execution_role_arn", "arn:aws:iam::000000000000:role/ecsTaskExecutionRole"
                ),
                "containers": [
                    {
                        "name": f"{name}-app",
                        "image": p.get("image", "public.ecr.aws/nginx/nginx:latest"),
                        "essential": True,
                        "portMappings": [{"containerPort": p.get("container_port", 80), "protocol": "tcp"}],
                    }
                ],
                "state": "present",
            },
        },
        {
            "name": f"ECS service: {name}",
            "community.aws.ecs_service": {
                "name": f"{name}-svc",
                "cluster": refs["cluster"],
                "task_definition": f"{name}-task",
                "desired_count": p.get("desired_count", 2),
                "launch_type": "FARGATE",
                "network_configuration": {"subnets": refs["subnets"], "assign_public_ip": False},
                "state": "present",
            },
        },
    ]


BLOCKS: dict[str, dict] = {
    "vpc": {
        "inputs": {},
        "props": {
            "cidr": {"type": "cidr", "required": True, "default": "10.0.0.0/16", "guidance": "Network range for the VPC."},
            "name": {"type": "string", "guidance": "Optional Name tag."},
        },
        "output": "vpc.id",
        "render": _vpc,
    },
    "subnet": {
        "inputs": {"vpc": {"type": "vpc", "many": False}},
        "props": {
            "cidr": {"type": "cidr", "required": True, "example": "10.0.1.0/24", "guidance": "Subnet range within the VPC CIDR."},
            "az": {"type": "string", "example": "ap-south-1a", "guidance": "Availability zone."},
            "public": {"type": "bool", "default": False, "guidance": "Auto-assign public IPs?"},
        },
        "output": "subnet.id",
        "render": _subnet,
    },
    "security_group": {
        "inputs": {"vpc": {"type": "vpc", "many": False}},
        "props": {
            "name": {"type": "string", "guidance": "Optional name."},
            "ssh_cidr": {"type": "cidr", "example": "203.0.113.10/32", "guidance": "Allow SSH (22) from this IP. Avoid 0.0.0.0/0."},
            "allow_http": {"type": "bool", "default": False, "guidance": "Allow HTTP (80) from anywhere."},
            "allow_https": {"type": "bool", "default": False, "guidance": "Allow HTTPS (443) from anywhere."},
        },
        "output": "group_id",
        "render": _security_group,
    },
    "ec2_instance": {
        "inputs": {
            "subnet": {"type": "subnet", "many": False},
            "security_group": {"type": "security_group", "many": False},
        },
        "props": {
            "name": {"type": "string"},
            "instance_type": {"type": "string", "default": "t3.micro", "guidance": "EC2 instance size."},
            "ami": {"type": "string", "guidance": "AMI id (defaults to a group_var placeholder)."},
            "public": {"type": "bool", "default": False, "guidance": "Assign a public IP?"},
        },
        "output": "instance_ids",
        "render": _ec2_instance,
    },
    "alb": {
        "inputs": {
            "subnets": {"type": "subnet", "many": True},
            "security_group": {"type": "security_group", "many": False},
        },
        "props": {
            "name": {"type": "string"},
            "target_group": {"type": "string", "guidance": "Target group name (defaults to <id>-tg)."},
        },
        "output": "dns_name",
        "render": _alb,
    },
    "rds": {
        "inputs": {"subnets": {"type": "subnet", "many": True}},
        "props": {
            "engine": {"type": "string", "default": "postgres", "guidance": "Database engine."},
            "instance_class": {"type": "string", "default": "db.t3.micro"},
            "storage": {"type": "number", "default": 20, "guidance": "Allocated storage (GB)."},
            "username": {"type": "string", "default": "appadmin"},
        },
        "output": "endpoint",
        "render": _rds,
    },
    "igw": {
        "inputs": {"vpc": {"type": "vpc", "many": False}},
        "props": {},
        "output": "gateway_id",
        "render": _igw,
    },
    "nat_gateway": {
        "inputs": {"subnet": {"type": "subnet", "many": False}},
        "props": {},
        "output": "nat_gateway_id",
        "render": _nat_gateway,
    },
    "route_table": {
        "inputs": {"vpc": {"type": "vpc", "many": False}, "subnets": {"type": "subnet", "many": True}},
        "props": {},
        "output": "route_table.id",
        "render": _route_table,
    },
    "s3_bucket": {
        "inputs": {},
        "props": {
            "bucket_name": {"type": "string", "guidance": "Globally-unique bucket name."},
            "versioning": {"type": "bool", "default": False, "guidance": "Enable object versioning?"},
        },
        "output": "name",
        "render": _s3_bucket,
    },
    "s3_website": {
        "inputs": {"bucket": {"type": "s3_bucket", "many": False}},
        "props": {
            "index_document": {"type": "string", "default": "index.html", "guidance": "Root document."},
            "error_document": {"type": "string", "default": "error.html", "guidance": "4xx error document."},
        },
        "output": "website_endpoint",
        "render": _s3_website,
    },
    "target_group": {
        "inputs": {"vpc": {"type": "vpc", "many": False}},
        "props": {
            "name": {"type": "string"},
            "protocol": {"type": "string", "default": "HTTP"},
            "port": {"type": "number", "default": 80},
            "health_check_path": {"type": "string", "default": "/"},
        },
        "output": "target_group_arn",
        "render": _target_group,
    },
    "launch_template": {
        "inputs": {},
        "props": {
            "name": {"type": "string"},
            "instance_type": {"type": "string", "default": "t3.micro"},
            "ami": {"type": "string", "guidance": "AMI id (e.g. a Packer golden image)."},
        },
        "output": "template.launch_template_id",
        "render": _launch_template,
    },
    "lambda": {
        "inputs": {},
        "props": {
            "name": {"type": "string"},
            "runtime": {"type": "string", "default": "python3.12"},
            "handler": {"type": "string", "default": "app.handler"},
            "role_arn": {"type": "string", "guidance": "Execution role ARN."},
            "zip_file": {"type": "string", "default": "build/function.zip"},
        },
        "output": "configuration.function_arn",
        "render": _lambda,
    },
    "dynamodb": {
        "inputs": {},
        "props": {
            "table_name": {"type": "string"},
            "hash_key": {"type": "string", "default": "id"},
        },
        "output": "table_arn",
        "render": _dynamodb,
    },
    "kms_key": {
        "inputs": {},
        "props": {
            "alias": {"type": "string", "guidance": "Key alias."},
            "description": {"type": "string"},
        },
        "output": "key_id",
        "render": _kms_key,
    },
    "iam_role": {
        "inputs": {},
        "props": {
            "name": {"type": "string"},
            "assume_role_policy": {"type": "string", "guidance": "Trust policy JSON."},
        },
        "output": "arn",
        "render": _iam_role,
    },
    "eks_cluster": {
        "inputs": {"subnets": {"type": "subnet", "many": True}},
        "props": {
            "name": {"type": "string"},
            "role_arn": {"type": "string", "guidance": "EKS cluster IAM role ARN."},
        },
        "output": "name",
        "render": _eks_cluster,
    },
    "eks_nodegroup": {
        "inputs": {"subnets": {"type": "subnet", "many": True}},
        "props": {
            "name": {"type": "string"},
            "cluster_name": {"type": "string", "guidance": "Name of the EKS cluster."},
            "node_role_arn": {"type": "string", "guidance": "Node IAM role ARN."},
        },
        "output": "nodegroup.nodegroup_name",
        "render": _eks_nodegroup,
    },
    "transit_gateway": {
        "inputs": {},
        "props": {"description": {"type": "string"}},
        "output": "transit_gateway.transit_gateway_id",
        "render": _transit_gateway,
    },
    "vpn_gateway": {
        "inputs": {"vpc": {"type": "vpc", "many": False}},
        "props": {"name": {"type": "string"}},
        "output": "vgw.id",
        "render": _vpn_gateway,
    },
    "cloudtrail": {
        "inputs": {},
        "props": {
            "name": {"type": "string"},
            "bucket_name": {"type": "string", "guidance": "S3 bucket for the trail."},
        },
        "output": "trail.name",
        "render": _cloudtrail,
    },
    "api_gateway": {
        "inputs": {},
        "props": {
            "stage": {"type": "string", "default": "prod"},
            "swagger_text": {"type": "string", "guidance": "OpenAPI/Swagger definition (JSON)."},
        },
        "output": "api_id",
        "render": _api_gateway,
    },
    "eventbridge": {
        "inputs": {},
        "props": {
            "name": {"type": "string"},
            "schedule": {"type": "string", "default": "rate(5 minutes)"},
        },
        "output": "name",
        "render": _eventbridge,
    },
    "vpc_endpoint": {
        "inputs": {"vpc": {"type": "vpc", "many": False}},
        "props": {
            "service": {"type": "string", "guidance": "e.g. com.amazonaws.<region>.ssm"},
            "endpoint_type": {"type": "string", "default": "Interface"},
        },
        "output": "endpoint.vpc_endpoint_id",
        "render": _vpc_endpoint,
    },
    "ecs_cluster": {
        "inputs": {},
        "props": {"name": {"type": "string", "guidance": "ECS cluster name."}},
        "output": "cluster.clusterName",
        "render": _ecs_cluster,
    },
    "ecs_service": {
        "inputs": {
            "cluster": {"type": "ecs_cluster", "many": False},
            "subnets": {"type": "subnet", "many": True},
        },
        "props": {
            "image": {"type": "string", "default": "public.ecr.aws/nginx/nginx:latest", "guidance": "Container image."},
            "container_port": {"type": "number", "default": 80, "guidance": "Port the container listens on."},
            "desired_count": {"type": "number", "default": 2, "guidance": "Number of running tasks."},
            "cpu": {"type": "string", "default": "512", "guidance": "Fargate task CPU units."},
            "memory": {"type": "string", "default": "1024", "guidance": "Fargate task memory (MiB)."},
            "execution_role_arn": {"type": "string", "guidance": "ECS task execution role ARN."},
        },
        "output": "service.serviceName",
        "render": _ecs_service,
    },
}
