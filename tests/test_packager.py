import io
import zipfile

from app.services.packager import zip_files


def test_zip_files_roundtrip():
    blob = zip_files({"a.txt": "hello", "dir/b.txt": "world"})
    assert blob[:2] == b"PK"

    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        assert set(archive.namelist()) == {"a.txt", "dir/b.txt"}
        assert archive.read("a.txt") == b"hello"
        assert archive.read("dir/b.txt") == b"world"
