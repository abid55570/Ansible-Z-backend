from moto import mock_aws

from app.config import get_settings
from app.services import storage


@mock_aws
def test_storage_roundtrip(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "s3_bucket", "az-test-bucket")
    monkeypatch.setattr(settings, "s3_endpoint", "")

    storage.ensure_bucket()
    storage.ensure_bucket()  # idempotent (bucket already exists branch)

    storage.put_object("generations/1/uat.zip", b"PK-fake-zip")
    assert storage.get_object("generations/1/uat.zip") == b"PK-fake-zip"
