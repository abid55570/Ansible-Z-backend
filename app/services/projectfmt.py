"""Whitespace normalization for generated project files so output is lint-clean.

Strips trailing whitespace, collapses runs of blank lines to a single blank, and
ensures each file ends with exactly one newline — satisfying yamllint's empty-lines
checks (max / max-start / max-end) under ansible-lint's production profile.
"""


def normalize(content: str) -> str:
    lines = [line.rstrip() for line in content.replace("\r\n", "\n").split("\n")]
    out: list[str] = []
    blank = 0
    for line in lines:
        if line:
            blank = 0
            out.append(line)
        else:
            blank += 1
            if blank == 1:
                out.append(line)
    while out and out[-1] == "":
        out.pop()
    while out and out[0] == "":
        out.pop(0)
    return "\n".join(out) + "\n" if out else ""


def normalize_files(files: dict[str, str]) -> dict[str, str]:
    """Apply :func:`normalize` to every file in a generated project."""
    return {path: normalize(content) for path, content in files.items()}
