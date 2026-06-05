from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.schemas import TemplateDetail, TemplateSummary
from app.services.generator import TEMPLATES_DIR, TemplateError, get_template_detail, list_templates

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


@router.get("/{slug}/diagram.png")
def diagram_image(slug: str) -> FileResponse:
    """Serve the pre-rendered, publication-quality architecture diagram (PNG)."""
    if slug not in {t["slug"] for t in list_templates()}:
        raise HTTPException(status_code=404, detail="Unknown template")
    path = TEMPLATES_DIR / slug / "diagram.png"
    if not path.is_file():  # pragma: no cover - every catalogue template ships one
        raise HTTPException(status_code=404, detail="No diagram image for this template")
    return FileResponse(path, media_type="image/png")
