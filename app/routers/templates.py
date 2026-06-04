from fastapi import APIRouter, HTTPException

from app.schemas import TemplateDetail, TemplateSummary
from app.services.generator import TemplateError, get_template_detail, list_templates

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=list[TemplateSummary])
def list_all() -> list[dict]:
    return list_templates()


@router.get("/{slug}", response_model=TemplateDetail)
def detail(slug: str) -> dict:
    try:
        return get_template_detail(slug)
    except TemplateError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
