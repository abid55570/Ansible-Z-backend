import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def ansible_available() -> bool:
    return shutil.which("ansible-playbook") is not None


def syntax_check(files: dict[str, str], playbook: str = "site.yml") -> dict:
    """Write rendered files to a temp dir and run ``ansible-playbook --syntax-check``.

    Returns {"status": "passed" | "failed" | "skipped", ...}. Skips gracefully when ansible
    is not installed, so the fast YAML lint stays the only hard dependency of the pipeline.
    """
    if not ansible_available():
        return {"status": "skipped", "reason": "ansible-playbook not installed"}

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel, content in files.items():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        if not (root / playbook).exists():
            return {"status": "skipped", "reason": f"no {playbook} in project"}

        proc = subprocess.run(
            ["ansible-playbook", "--syntax-check", playbook],
            cwd=tmp,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "ANSIBLE_LOCALHOST_WARNING": "False",
                "ANSIBLE_DEPRECATION_WARNINGS": "False",
                "ANSIBLE_INVENTORY_UNPARSED_WARNING": "False",
            },
        )
        if proc.returncode == 0:
            return {"status": "passed"}
        return {"status": "failed", "output": (proc.stdout + proc.stderr).strip()[-2000:]}
