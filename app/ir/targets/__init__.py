"""Export-target registry: compile an IR design into a project for a chosen tool.

Ansible is the original target; Terraform is the first multi-target addition.
CloudFormation, Pulumi, CDK, Bicep, Kubernetes and Compose register here too.
"""

from app.ir.compiler import compile_ir
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
