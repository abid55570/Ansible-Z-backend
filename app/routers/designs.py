from fastapi import APIRouter, Body, Depends

from app.deps import get_current_user
from app.ir.blocks import BLOCKS
from app.ir.compiler import IRError, validate
from app.models import User

router = APIRouter(prefix="/designs", tags=["designs"])


@router.get("/blocks")
def list_blocks() -> dict:
    """Catalogue of building blocks for the canvas palette (ports + schema)."""
    return {
        name: {"inputs": spec["inputs"], "props": spec["props"], "output": spec["output"]}
        for name, spec in BLOCKS.items()
    }


@router.post("/validate")
def validate_design(ir: dict = Body(...), user: User = Depends(get_current_user)) -> dict:
    """Validate an IR graph without generating — powers the canvas's live validation."""
    try:
        validate(ir)
    except IRError as exc:
        return {"valid": False, "errors": exc.errors}
    return {"valid": True, "errors": []}
