import pytest

from app.services.ansible_check import ansible_available, syntax_check
from app.services.generator import list_templates, load_manifest, render_project, sample_config

READY_SLUGS = [t["slug"] for t in list_templates() if t["ready"]]


@pytest.mark.skipif(not ansible_available(), reason="ansible-playbook not installed (e.g. native Windows)")
@pytest.mark.parametrize("slug", READY_SLUGS)
def test_ready_template_passes_ansible_syntax_check(slug):
    manifest = load_manifest(slug)
    files = render_project(slug, sample_config(manifest, "uat"), env="uat")
    report = syntax_check(files)
    assert report["status"] == "passed", report.get("output")
