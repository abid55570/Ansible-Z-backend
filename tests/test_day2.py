import io
import zipfile

import yaml

from app.services.day2 import day2_files
from app.services.linter import lint_files

from test_generate import CUSTOM_IR, _make_project


def test_day2_bundle_is_valid():
    files = day2_files()
    assert set(files) == {"apps.yml", "deploy.yml", "rollback.yml", "DAY2.md"}
    assert lint_files(files)["status"] == "passed"


def test_deploy_and_rollback_are_playbooks():
    files = day2_files()
    for name in ("deploy.yml", "rollback.yml"):
        plays = yaml.safe_load(files[name])
        assert isinstance(plays, list) and len(plays) == 1
        play = plays[0]
        assert play["hosts"] and play["tasks"]
        assert play["vars_files"] == ["apps.yml"]


def test_apps_manifest_shape():
    manifest = yaml.safe_load(day2_files()["apps.yml"])
    assert manifest["app_host_group"] == "role_app"
    assert isinstance(manifest["apps"], list) and manifest["apps"]
    app = manifest["apps"][0]
    for key in ("name", "image", "tag", "rollback_tag", "port"):
        assert key in app


def _download_members(auth_client, project_id, env="uat"):
    auth_client.post(f"/projects/{project_id}/generate", json={"env": env})
    blob = auth_client.get(f"/projects/{project_id}/download", params={"env": env}).content
    return set(zipfile.ZipFile(io.BytesIO(blob)).namelist())


def test_template_project_includes_day2(auth_client, fake_storage):
    members = _download_members(auth_client, _make_project(auth_client))
    assert {"apps.yml", "deploy.yml", "rollback.yml", "DAY2.md"} <= members


def test_custom_design_includes_day2(auth_client, fake_storage):
    project_id = _make_project(auth_client, slug="__custom__", config=CUSTOM_IR)
    members = _download_members(auth_client, project_id)
    assert {"apps.yml", "deploy.yml", "rollback.yml", "DAY2.md"} <= members
