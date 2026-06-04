import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import Generation, Project, User
from app.schemas import GenerateIn, GenerationOut, ProjectCreate, ProjectOut
from app.ir.compiler import IRError, compile_ir
from app.services import ansible_check, day2, linter, packager, storage
from app.services.generator import TemplateError, load_manifest, render_project, template_is_ready

router = APIRouter(prefix="/projects", tags=["projects"])


def _get_owned_project(project_id: int, user: User, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == user.id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    body: ProjectCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Project:
    if body.template_slug != "__custom__":
        try:
            load_manifest(body.template_slug)
        except TemplateError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    project = Project(user_id=user.id, name=body.name, template_slug=body.template_slug, config=body.config)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=list[ProjectOut])
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Project]:
    return db.query(Project).filter(Project.user_id == user.id).order_by(Project.id.desc()).all()


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Project:
    return _get_owned_project(project_id, user, db)


@router.post("/{project_id}/generate", response_model=GenerationOut)
def generate(
    project_id: int,
    body: GenerateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Generation:
    project = _get_owned_project(project_id, user, db)

    if project.template_slug == "__custom__":
        try:
            files = compile_ir(project.config)
        except IRError as exc:
            raise HTTPException(status_code=400, detail={"message": "Invalid design", "errors": exc.errors}) from exc
    else:
        if not template_is_ready(project.template_slug):
            raise HTTPException(status_code=409, detail="Template is not ready for generation yet")
        try:
            files = render_project(project.template_slug, project.config, env=body.env)
        except TemplateError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Merge the Day-2 ops layer (deploy/update/rollback apps); a template that
    # ships its own deploy.yml keeps it.
    files = {**day2.day2_files(), **files}

    report = linter.lint_files(files)
    if report["status"] == "failed":
        raise HTTPException(status_code=422, detail={"message": "Generated project failed lint", "report": report})

    if get_settings().deep_lint:
        for playbook in ("site.yml", "deploy.yml", "rollback.yml"):
            deep = ansible_check.syntax_check(files, playbook=playbook)
            if deep["status"] == "failed":
                raise HTTPException(
                    status_code=422,
                    detail={"message": f"ansible --syntax-check failed: {playbook}", "report": deep},
                )

    blob = packager.zip_files(files)
    key = f"generations/{project.id}/{body.env}-{uuid.uuid4().hex[:8]}.zip"
    storage.ensure_bucket()
    storage.put_object(key, blob)

    generation = Generation(
        project_id=project.id,
        env=body.env,
        artifact_key=key,
        lint_status=report["status"],
        lint_report=report,
    )
    db.add(generation)
    db.commit()
    db.refresh(generation)
    return generation


@router.get("/{project_id}/download")
def download(
    project_id: int,
    env: str = "uat",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    project = _get_owned_project(project_id, user, db)
    generation = (
        db.query(Generation)
        .filter(Generation.project_id == project.id, Generation.env == env)
        .order_by(Generation.id.desc())
        .first()
    )
    if generation is None:
        raise HTTPException(status_code=404, detail="No generation found for this environment")

    data = storage.get_object(generation.artifact_key)
    filename = f"{project.template_slug}-{env}.zip"
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
