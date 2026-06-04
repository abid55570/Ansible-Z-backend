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
    rules = [
        {"proto": "tcp", "ports": [r["port"]], "cidr_ip": r.get("cidr", "0.0.0.0/0")}
        for r in node["props"].get("ingress", [])
    ]
    return {
        "name": f"Security group: {node['id']}",
        "amazon.aws.ec2_security_group": {
            "name": node["props"].get("name", node["id"]),
            "description": node["props"].get("description", node["id"]),
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


BLOCKS: dict[str, dict] = {
    "vpc": {"inputs": {}, "required": ["cidr"], "output": "vpc.id", "render": _vpc},
    "subnet": {
        "inputs": {"vpc": {"type": "vpc", "many": False}},
        "required": ["cidr"],
        "output": "subnet.id",
        "render": _subnet,
    },
    "security_group": {
        "inputs": {"vpc": {"type": "vpc", "many": False}},
        "required": [],
        "output": "group_id",
        "render": _security_group,
    },
    "ec2_instance": {
        "inputs": {
            "subnet": {"type": "subnet", "many": False},
            "security_group": {"type": "security_group", "many": False},
        },
        "required": [],
        "output": "instance_ids",
        "render": _ec2_instance,
    },
    "alb": {
        "inputs": {
            "subnets": {"type": "subnet", "many": True},
            "security_group": {"type": "security_group", "many": False},
        },
        "required": [],
        "output": "dns_name",
        "render": _alb,
    },
    "rds": {
        "inputs": {"subnets": {"type": "subnet", "many": True}},
        "required": [],
        "output": "endpoint",
        "render": _rds,
    },
}
