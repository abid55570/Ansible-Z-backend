from fastapi import APIRouter, Body, Depends

from app.deps import get_current_user
from app.ir.blocks import BLOCKS
from app.ir.compiler import IRError, validate
from app.ir.targets import list_targets
from app.models import User
from app.services.cost import estimate as estimate_cost

router = APIRouter(prefix="/designs", tags=["designs"])


@router.get("/blocks")
def list_blocks() -> dict:
    """Catalogue of building blocks for the canvas palette (ports + schema)."""
    return {
        name: {"inputs": spec["inputs"], "props": spec["props"], "output": spec["output"]}
        for name, spec in BLOCKS.items()
    }


@router.get("/targets")
def targets() -> dict:
    """Export targets available for a design (Ansible, Terraform, …) for the picker."""
    return {"targets": list_targets()}


@router.post("/validate")
def validate_design(ir: dict = Body(...), user: User = Depends(get_current_user)) -> dict:
    """Validate an IR graph without generating — powers the canvas's live validation."""
    try:
        validate(ir)
    except IRError as exc:
        return {"valid": False, "errors": exc.errors}
    return {"valid": True, "errors": []}


@router.post("/cost")
def cost(ir: dict = Body(...), user: User = Depends(get_current_user)) -> dict:
    """Rough monthly cost estimate for a design — powers the live cost panel."""
    return estimate_cost(ir)


@router.get("/pricing")
def pricing() -> dict:
    """Per-flavour monthly prices (USD) so the property panel can show cost per size."""
    from app.services.cost import EC2_HOURLY, HOURS_PER_MONTH, RDS_HOURLY

    return {
        "ec2": {k: round(v * HOURS_PER_MONTH, 2) for k, v in EC2_HOURLY.items()},
        "rds": {k: round(v * HOURS_PER_MONTH, 2) for k, v in RDS_HOURLY.items()},
    }
