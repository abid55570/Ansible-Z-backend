import app.services.ansible_check as ac


def test_ansible_available(monkeypatch):
    monkeypatch.setattr(ac.shutil, "which", lambda name: "/usr/bin/ansible-playbook")
    assert ac.ansible_available() is True
    monkeypatch.setattr(ac.shutil, "which", lambda name: None)
    assert ac.ansible_available() is False


def test_syntax_check_skipped_when_unavailable(monkeypatch):
    monkeypatch.setattr(ac.shutil, "which", lambda name: None)
    assert ac.syntax_check({"site.yml": "---\n- hosts: localhost\n"})["status"] == "skipped"


def test_syntax_check_skipped_without_playbook(monkeypatch):
    monkeypatch.setattr(ac.shutil, "which", lambda name: "/usr/bin/ansible-playbook")
    report = ac.syntax_check({"group_vars/all.yml": "a: 1\n"})
    assert report["status"] == "skipped"


def test_syntax_check_passed(monkeypatch):
    monkeypatch.setattr(ac.shutil, "which", lambda name: "/usr/bin/ansible-playbook")

    class _Proc:
        returncode = 0
        stdout = "playbook: site.yml"
        stderr = ""

    monkeypatch.setattr(ac.subprocess, "run", lambda *a, **k: _Proc())
    assert ac.syntax_check({"site.yml": "---\n- hosts: localhost\n"})["status"] == "passed"


def test_syntax_check_failed(monkeypatch):
    monkeypatch.setattr(ac.shutil, "which", lambda name: "/usr/bin/ansible-playbook")

    class _Proc:
        returncode = 1
        stdout = "ERROR! bad playbook"
        stderr = "syntax error"

    monkeypatch.setattr(ac.subprocess, "run", lambda *a, **k: _Proc())
    report = ac.syntax_check({"site.yml": "broken"})
    assert report["status"] == "failed"
    assert "bad playbook" in report["output"]
