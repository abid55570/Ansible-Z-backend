import yaml


def lint_files(files: dict[str, str]) -> dict:
    """Validate that every rendered YAML file parses. Returns a report.

    This is the fast first gate that guarantees an export is not broken YAML.
    A deeper ansible-lint / --syntax-check pass is added once ansible is in the image.
    """
    errors: list[dict] = []
    for path, content in sorted(files.items()):
        if path.endswith((".yml", ".yaml")):
            try:
                list(yaml.safe_load_all(content))
            except yaml.YAMLError as exc:
                errors.append({"file": path, "error": str(exc)})
    return {"status": "passed" if not errors else "failed", "errors": errors}
