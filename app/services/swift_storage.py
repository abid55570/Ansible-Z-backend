import openstack

from app.config import get_settings


def _connection():
    settings = get_settings()
    return openstack.connect(
        auth_url=settings.os_auth_url,
        auth_type="v3applicationcredential",
        application_credential_id=settings.os_app_cred_id,
        application_credential_secret=settings.os_app_cred_secret,
        region_name=settings.os_region,
        verify=settings.os_verify_tls,
    )


def ensure_bucket() -> None:
    """Create the Swift container if it does not already exist (idempotent)."""
    _connection().object_store.create_container(name=get_settings().swift_container)


def put_object(key: str, data: bytes, content_type: str = "application/zip") -> None:
    _connection().object_store.upload_object(
        container=get_settings().swift_container, name=key, data=data
    )


def get_object(key: str) -> bytes:
    return _connection().object_store.download_object(key, container=get_settings().swift_container)
