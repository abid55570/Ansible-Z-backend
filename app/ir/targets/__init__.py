"""Export-target registry: compile an IR design into a project for a chosen tool.

Ansible is the original target; Terraform is the first multi-target addition.
CloudFormation, Pulumi, CDK, Bicep, Kubernetes and Compose register here too.
"""

from app.ir.compiler import compile_ir
from app.ir.targets.cdk import compile_cdk
from app.ir.targets.cloudformation import compile_cloudformation
from app.ir.targets.compose import compile_compose
from app.ir.targets.kubernetes import compile_kubernetes
from app.ir.targets.pulumi import compile_pulumi
from app.ir.targets.terraform import compile_terraform


class TargetError(Exception):
    """Raised for an unknown export target."""


TARGETS: dict = {
    "ansible": {
        "label": "Ansible",
        "coverage": "full",
        "description": "Runnable Ansible project (amazon.aws / community.aws collections).",
        "compile": compile_ir,
    },
    "terraform": {
        "label": "Terraform / OpenTofu",
        "coverage": "full",
        "description": "HCL for the AWS provider — run with terraform or tofu.",
        "compile": compile_terraform,
    },
    "cloudformation": {
        "label": "CloudFormation",
        "coverage": "partial",
        "description": "AWS CloudFormation template (JSON) — core networking, compute, storage & data.",
        "compile": compile_cloudformation,
    },
    "pulumi": {
        "label": "Pulumi (TypeScript)",
        "coverage": "partial",
        "description": "A Pulumi program in TypeScript (@pulumi/aws) — core resources.",
        "compile": compile_pulumi,
    },
    "cdk": {
        "label": "AWS CDK (TypeScript)",
        "coverage": "partial",
        "description": "An AWS CDK app in TypeScript (aws-cdk-lib L1 constructs) — core resources.",
        "compile": compile_cdk,
    },
    "compose": {
        "label": "Docker Compose",
        "coverage": "containers",
        "description": "Container workloads (ECS services, databases, object store) as a Compose file.",
        "compile": compile_compose,
    },
    "kubernetes": {
        "label": "Kubernetes",
        "coverage": "containers",
        "description": "Kubernetes manifests for the container workloads (Deployments + Services).",
        "compile": compile_kubernetes,
    },
}


def list_targets() -> list[dict]:
    """Public catalogue of export targets (for the designer's target picker)."""
    return [
        {"id": tid, "label": t["label"], "coverage": t["coverage"], "description": t["description"]}
        for tid, t in TARGETS.items()
    ]


def compile_target(ir: dict, target: str = "ansible") -> dict:
    """Compile an IR into a project for ``target`` (defaults to Ansible)."""
    spec = TARGETS.get(target)
    if spec is None:
        raise TargetError(f"unknown export target '{target}'")
    return spec["compile"](ir)
