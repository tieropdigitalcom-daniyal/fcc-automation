from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_mode: str = "demo"
    database_url: str = "sqlite:///runtime/fccs.db"
    public_origin: str = "http://localhost:3000"
    session_secret: str = ""
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    storage_backend: str = "local"
    evidence_path: str = "runtime/evidence"
    s3_endpoint: str = ""
    s3_bucket: str = "fccs-evidence"
    s3_region: str = "us-east-1"
    s3_object_lock: bool = False
    s3_retention_days: int = 2555
    queue_mode: str = "inline"
    redis_url: str = "redis://localhost:6379/0"
    notification_url: str = ""
    oracle_base_url: str = ""
    oracle_application: str = ""
    oracle_access_token: str = ""
    oracle_enabled: bool = False
    oracle_environment: str = "test"
    oracle_approved_jobs: str = ""

    def check(self):
        if self.app_mode not in {"demo", "production"}:
            raise ValueError("APP_MODE must be demo or production")
        if self.app_mode == "production":
            required = (self.oidc_issuer, self.oidc_client_id, self.oidc_client_secret)
            if not all(required) or len(self.session_secret) < 32:
                raise ValueError("Production requires OIDC and a strong session secret")
            if not self.database_url.startswith("postgresql") or self.storage_backend != "s3":
                raise ValueError("Production requires PostgreSQL and approved S3 storage")
            if not self.s3_object_lock or self.queue_mode != "celery" or not self.public_origin.startswith("https://"):
                raise ValueError("Production requires retention, durable workers and HTTPS")
        Path("runtime").mkdir(exist_ok=True)


settings = Settings()
