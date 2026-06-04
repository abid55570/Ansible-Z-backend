from pydantic import BaseModel, ConfigDict


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email: str
    name: str | None = None
    avatar_url: str | None = None


class TemplateSummary(BaseModel):
    slug: str
    name: str
    pci: str
    summary: str
    ready: bool


class TemplateDetail(TemplateSummary):
    version: str
    roles: list[str] = []
    variables: dict = {}


class ProjectCreate(BaseModel):
    name: str
    template_slug: str
    config: dict = {}


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    template_slug: str
    config: dict
    created_at: object | None = None


class GenerateIn(BaseModel):
    env: str = "uat"


class GenerationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    env: str
    artifact_key: str
    lint_status: str
    lint_report: dict
