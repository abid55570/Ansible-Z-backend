from app.services.linter import lint_files


def test_lint_passes_for_valid_yaml():
    report = lint_files({"vars.yml": "a: 1\nb: two\n", "notes.md": "ignored: [unclosed"})
    assert report["status"] == "passed"
    assert report["errors"] == []


def test_lint_fails_for_broken_yaml():
    report = lint_files({"bad.yml": "a: [1, 2\n"})
    assert report["status"] == "failed"
    assert report["errors"][0]["file"] == "bad.yml"
