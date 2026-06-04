import boto3

from app.config import get_settings


def _is_swift() -> bool:
    return get_settings().storage_provider == "swift"


# --- S3 / S3-compatible (boto3) ---

def _s3_client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint or None,
        aws_access_key_id=settings.s3_access_key or None,
        aws_secret_access_key=settings.s3_secret_key or None,
        region_name="us-east-1",
    )


def _s3_ensure_bucket() -> None:
    settings = get_settings()
    client = _s3_client()
    existing = [b["Name"] for b in client.list_buckets().get("Buckets", [])]
    if settings.s3_bucket not in existing:
        client.create_bucket(Bucket=settings.s3_bucket)


def _s3_put(key: str, data: bytes, content_type: str) -> None:
    settings = get_settings()
    _s3_client().put_object(Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type)


def _s3_get(key: str) -> bytes:
    settings = get_settings()
    return _s3_client().get_object(Bucket=settings.s3_bucket, Key=key)["Body"].read()


# --- public API (dispatched by STORAGE_PROVIDER) ---

def ensure_bucket() -> None:
    if _is_swift():
        from app.services import swift_storage

        swift_storage.ensure_bucket()
    else:
        _s3_ensure_bucket()


def put_object(key: str, data: bytes, content_type: str = "application/zip") -> None:
    if _is_swift():
        from app.services import swift_storage

        swift_storage.put_object(key, data, content_type)
    else:
        _s3_put(key, data, content_type)


def get_object(key: str) -> bytes:
    if _is_swift():
        from app.services import swift_storage

        return swift_storage.get_object(key)
    return _s3_get(key)
