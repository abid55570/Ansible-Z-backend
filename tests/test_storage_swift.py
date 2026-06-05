import app.services.swift_storage as swift_storage
from app.config import get_settings
from app.services import storage


class _FakeObjectStore:
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}
        self.created_container: str | None = None

    def create_container(self, name):
        self.created_container = name

    def upload_object(self, container, name, data):
        self.objects[(container, name)] = data

    def download_object(self, name, container):
        return self.objects[(container, name)]


class _FakeConnection:
    def __init__(self):
        self.object_store = _FakeObjectStore()


def test_swift_roundtrip_via_dispatch(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "storage_provider", "swift")
    monkeypatch.setattr(settings, "swift_container", "neviri-ansi")

    fake = _FakeConnection()
    monkeypatch.setattr(swift_storage.openstack, "connect", lambda **kwargs: fake)

    # Goes through the public storage facade, which dispatches to the Swift backend.
    storage.ensure_bucket()
    storage.put_object("generations/1/uat.zip", b"swift-bytes")
    assert storage.get_object("generations/1/uat.zip") == b"swift-bytes"
    assert fake.object_store.created_container == "neviri-ansi"
