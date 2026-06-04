import pytest

from app.services.generator import list_templates, load_manifest, render_project, sample_config
from app.services.linter import lint_files

READY_SLUGS = [t["slug"] for t in list_templates() if t["ready"]]


def test_at_least_two_ready_templates():
    assert len(READY_SLUGS) >= 2  # web-3tier + the new ones


@pytest.mark.parametrize("slug", READY_SLUGS)
def test_ready_template_renders_valid_yaml(slug):
    manifest = load_manifest(slug)
    files = render_project(slug, sample_config(manifest, "uat"), env="uat")

    assert files, f"{slug} rendered no files"
    # every ready template must ship a runnable entrypoint
    assert any(name.endswith("site.yml") for name in files), f"{slug} has no site.yml"

    report = lint_files(files)
    assert report["status"] == "passed", f"{slug} produced invalid YAML: {report['errors']}"
