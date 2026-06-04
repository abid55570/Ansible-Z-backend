"""Render every ready template and run ansible-playbook --syntax-check. Dev/CI tool.

Usage:
    .venv/Scripts/python scripts/check_templates.py
"""

from app.services.ansible_check import ansible_available, syntax_check
from app.services.day2 import day2_files
from app.services.generator import list_templates, load_manifest, render_project, sample_config

print("ansible-playbook available:", ansible_available())
print("-" * 50)

failed = 0
for tpl in list_templates():
    if not tpl["ready"]:
        continue
    slug = tpl["slug"]
    manifest = load_manifest(slug)
    files = {**day2_files(), **render_project(slug, sample_config(manifest, "uat"), env="uat")}
    statuses = []
    for playbook in ("site.yml", "deploy.yml", "rollback.yml"):
        report = syntax_check(files, playbook=playbook)
        statuses.append(f"{playbook.split('.')[0]}={report['status']}")
        if report["status"] == "failed":
            failed += 1
            print(f"  {slug} {playbook} FAILED:")
            print(report.get("output", ""))
    print(f"{slug:26} " + " ".join(statuses))

print("-" * 50)
print("FAILED" if failed else "ALL READY TEMPLATES PASS SYNTAX-CHECK (site + day-2)")
