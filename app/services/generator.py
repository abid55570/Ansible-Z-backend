from pathlib import Path

import yaml
from jinja2 import Environment, StrictUndefined

from app.services.projectfmt import normalize_files

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


class TemplateError(Exception):
    """Raised for unknown templates or invalid/missing variables."""


def load_manifest(slug: str) -> dict:
    manifest_path = TEMPLATES_DIR / slug / "template.yaml"
    if not manifest_path.exists():
        raise TemplateError(f"Unknown template: {slug}")
    return yaml.safe_load(manifest_path.read_text(encoding="utf-8"))


def _is_required_in_env(spec: dict, env: str | None) -> bool:
    """A variable is required if ``required`` is set AND it applies to ``env``.

    A variable with no ``scope`` applies to every environment. A scoped variable
    (e.g. ``scope: [uat, prod]``) is only required when rendering for one of those
    environments; with no env context (``env is None``) scoped vars are skipped.
    """
    if not spec.get("required"):
        return False
    scope = spec.get("scope")
    if not scope:
        return True
    if env is None:
        return False
    return env in scope


def required_variables(manifest: dict, env: str | None = None) -> list[str]:
    return [
        name
        for name, spec in manifest.get("variables", {}).items()
        if _is_required_in_env(spec, env)
    ]


def validate_variables(manifest: dict, variables: dict, env: str | None = None) -> None:
    missing = [
        name
        for name in required_variables(manifest, env)
        if name not in variables or variables[name] in (None, "")
    ]
    if missing:
        raise TemplateError(f"Missing required variables: {', '.join(sorted(missing))}")


def render_project(slug: str, variables: dict, env: str | None = None) -> dict[str, str]:
    """Render a template's ``files/**/*.j2`` into a mapping of {relative_path: content}.

    Required variables (for the given ``env``) are validated first. A ``__env__`` token in a
    file path is replaced with the environment name (e.g. ``group_vars/__env__.yml`` ->
    ``group_vars/uat.yml``). Returns the rendered project tree in memory.
    """
    manifest = load_manifest(slug)
    validate_variables(manifest, variables, env)

    files_dir = TEMPLATES_DIR / slug / "files"
    jinja_env = Environment(undefined=StrictUndefined, keep_trailing_newline=True, autoescape=False)
    context = {"_meta": manifest, "env": env or "all", **variables}

    rendered: dict[str, str] = {}
    for path in sorted(files_dir.rglob("*.j2")):
        relative = path.relative_to(files_dir).as_posix()[:-3]  # strip the trailing ".j2"
        relative = relative.replace("__env__", env or "all")
        template = jinja_env.from_string(path.read_text(encoding="utf-8"))
        rendered[relative] = template.render(**context)
    return normalize_files(rendered)


def template_is_ready(slug: str) -> bool:
    """A template is generatable once it has a ``files/`` directory containing templates."""
    files_dir = TEMPLATES_DIR / slug / "files"
    return files_dir.is_dir() and any(files_dir.rglob("*.j2"))


def _summary(manifest: dict) -> dict:
    return {
        "slug": manifest["id"],
        "name": manifest.get("name", manifest["id"]),
        "pci": manifest.get("pci", "none"),
        "tier": manifest.get("tier", "enterprise"),
        "summary": manifest.get("summary", ""),
        "ready": template_is_ready(manifest["id"]),
    }


def list_templates() -> list[dict]:
    items: list[dict] = []
    for child in sorted(TEMPLATES_DIR.iterdir()):
        manifest_path = child / "template.yaml"
        if child.is_dir() and manifest_path.exists():
            items.append(_summary(yaml.safe_load(manifest_path.read_text(encoding="utf-8"))))
    return items


def sample_config(manifest: dict, env: str | None = None) -> dict:
    """Build a config satisfying every required var for ``env`` using defaults/examples.

    Used for previews and for the render/syntax test gates.
    """
    config: dict = {}
    variables = manifest.get("variables", {})
    for name in required_variables(manifest, env):
        spec = variables[name]
        if "default" in spec:
            config[name] = str(spec["default"])
        elif "example" in spec:
            config[name] = str(spec["example"])
        elif spec.get("type") == "cidr":
            config[name] = "10.0.0.0/16"
        else:
            config[name] = "sample"
    return config


def get_template_detail(slug: str) -> dict:
    manifest = load_manifest(slug)
    detail = _summary(manifest)
    detail.update(
        {
            "version": str(manifest.get("version", "")),
            "roles": manifest.get("roles", []),
            "variables": manifest.get("variables", {}),
            "diagram": manifest.get("diagram"),
            "key_points": manifest.get("key_points", []),
            "security_groups": manifest.get("security_groups", []),
        }
    )
    return detail
