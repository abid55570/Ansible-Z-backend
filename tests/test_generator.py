import pytest

from app.services.generator import (
    TemplateError,
    load_manifest,
    render_project,
    required_variables,
    sample_config,
    validate_variables,
)


def test_sample_config_uses_defaults_examples_and_fallbacks():
    manifest = {
        "variables": {
            "a": {"required": True, "type": "cidr"},  # no default/example -> cidr fallback
            "b": {"required": True},                    # no type -> "sample"
            "c": {"required": True, "default": "d"},    # default wins
            "e": {"required": True, "example": "x"},    # example
            "opt": {"required": False},                 # not required -> skipped
        }
    }
    config = sample_config(manifest)
    assert config == {"a": "10.0.0.0/16", "b": "sample", "c": "d", "e": "x"}

# The three environment-agnostic required vars (office_ip is scoped to uat/prod only).
BASE_VARS = {
    "project_name": "acme-web",
    "aws_region": "ap-south-1",
    "vpc_cidr": "10.20.0.0/16",
}
UAT_VARS = {**BASE_VARS, "office_ip": "203.0.113.10/32"}


def test_load_manifest_ok():
    manifest = load_manifest("web-3tier")
    assert manifest["id"] == "web-3tier"
    assert "variables" in manifest


def test_load_manifest_unknown():
    with pytest.raises(TemplateError):
        load_manifest("does-not-exist")


def test_required_variables_env_agnostic():
    manifest = load_manifest("web-3tier")
    required = required_variables(manifest)  # env=None -> only unscoped required
    assert "project_name" in required
    assert "office_ip" not in required        # scoped to uat/prod
    assert "certificate_arn" not in required  # required: false


def test_required_variables_for_uat():
    manifest = load_manifest("web-3tier")
    required = required_variables(manifest, env="uat")
    assert "office_ip" in required             # required once env is uat


def test_validate_missing_required():
    manifest = load_manifest("web-3tier")
    with pytest.raises(TemplateError):
        validate_variables(manifest, {})


def test_validate_base_ok():
    manifest = load_manifest("web-3tier")
    validate_variables(manifest, BASE_VARS)  # env=None -> passes without office_ip


def test_validate_uat_requires_office_ip():
    manifest = load_manifest("web-3tier")
    with pytest.raises(TemplateError):
        validate_variables(manifest, BASE_VARS, env="uat")
    validate_variables(manifest, UAT_VARS, env="uat")  # passes with office_ip


def test_render_project_ok():
    files = render_project("web-3tier", BASE_VARS)
    assert "README.md" in files
    assert "acme-web" in files["README.md"]
    assert "ap-south-1" in files["README.md"]


def test_render_project_with_uat_env():
    files = render_project("web-3tier", UAT_VARS, env="uat")
    assert "203.0.113.10/32" in files["README.md"]


def test_render_project_missing_var():
    with pytest.raises(TemplateError):
        render_project("web-3tier", {"project_name": "x"})
