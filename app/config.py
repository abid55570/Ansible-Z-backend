from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment / .env (case-insensitive)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Ansible-Z API"
    env: str = "local"

    # security
    jwt_secret: str = "dev-insecure-change-me-please-set-a-real-32char-secret"
    jwt_alg: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    # google sign-in
    google_client_id: str = ""

    # database
    database_url: str = "sqlite+pysqlite:///:memory:"

    # object storage — provider is "s3" or "swift"
    storage_provider: str = "s3"

    # S3 / S3-compatible (boto3)
    s3_endpoint: str = ""
    s3_bucket: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""

    # OpenStack Swift (Keystone v3 application credential)
    os_auth_url: str = ""
    os_app_cred_id: str = ""
    os_app_cred_secret: str = ""
    os_region: str = ""
    swift_container: str = "ansible-z"
    os_verify_tls: bool = True

    # deep validation: run `ansible-playbook --syntax-check` on generated projects.
    # Requires ansible-core (Linux). Off by default; the fast YAML lint always runs.
    deep_lint: bool = False

    # cors
    frontend_origin: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
