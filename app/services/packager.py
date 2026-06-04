import io
import zipfile


def zip_files(files: dict[str, str]) -> bytes:
    """Pack a {relative_path: content} mapping into a deterministic in-memory zip."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in sorted(files.items()):
            archive.writestr(path, content)
    return buffer.getvalue()
