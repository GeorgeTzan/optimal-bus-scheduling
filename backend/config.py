import os
from typing import List
from dotenv import load_dotenv

load_dotenv()
# Local generated runtime-role credentials are separate from the existing migration-owner settings.
from pathlib import Path
load_dotenv(Path(__file__).resolve().parent / '.env.runtime.local')
# Mail credentials live in their own git-ignored file (matches .env*.local) so they never sit in the tracked .env.
load_dotenv(Path(__file__).resolve().parent / '.env.mail.local')


class Settings:
    def __init__(self, **kwargs):
        self.ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
        self.SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")
        self.REFERENCE_TOOLS_ENABLED: bool = os.getenv("REFERENCE_TOOLS_ENABLED", "false").lower() == "true"
        self.DATABASE_URL: str = os.getenv(
            "DATABASE_URL", "postgresql://postgres:postgres@db:5432/scheduling"
        )
        self.DATABASE_RUNTIME_URL: str = os.getenv('DATABASE_RUNTIME_URL', self.DATABASE_URL)
        self.DATABASE_WORKER_URL: str = os.getenv('DATABASE_WORKER_URL', self.DATABASE_RUNTIME_URL)
        self.AUTH_LOGIN_LIMIT: int = int(os.getenv('AUTH_LOGIN_LIMIT','5' if self.ENVIRONMENT=='production' else '20'))
        self.IMPORT_MAX_ROWS: int = int(os.getenv('IMPORT_MAX_ROWS','1000'))
        self.IMPORT_MAX_UPLOAD_BYTES: int = int(os.getenv('IMPORT_MAX_UPLOAD_BYTES',str(5*1024*1024)))
        self.IMPORT_STAGING_DAYS: int = int(os.getenv('IMPORT_STAGING_DAYS','7'))
        self.IMPORT_COMMITTED_RAW_DAYS: int = int(os.getenv('IMPORT_COMMITTED_RAW_DAYS','30'))
        self.AUTH_RESET_LIMIT: int = int(os.getenv('AUTH_RESET_LIMIT','3'))
        self.PUBLIC_APP_URL: str = os.getenv('PUBLIC_APP_URL','http://127.0.0.1:3000').rstrip('/')
        self.SMTP_HOST: str = os.getenv('SMTP_HOST','')
        self.SMTP_PORT: int = int(os.getenv('SMTP_PORT','587'))
        self.SMTP_USERNAME: str = os.getenv('SMTP_USERNAME','')
        self.SMTP_PASSWORD: str = os.getenv('SMTP_PASSWORD','')
        self.SMTP_FROM: str = os.getenv('SMTP_FROM','')
        self.SMTP_USE_TLS: bool = os.getenv('SMTP_USE_TLS','true').lower()=='true'
        self.EMAIL_OUTBOX_KEY: str = os.getenv('EMAIL_OUTBOX_KEY','')
        self.SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-in-production")
        self.ALGORITHM: str = "HS256"
        self.ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

        self.ALLOWED_ORIGINS: List[str] = [
            origin.strip()
            for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
            if origin.strip()
        ]

        for k, v in kwargs.items():
            setattr(self, k, v)


def validate_settings(settings: Settings) -> None:
    """Enforces fail-closed configuration invariants in production."""
    if settings.ENVIRONMENT == "production":
        if not settings.SECRET_KEY or settings.SECRET_KEY == "change-this-in-production":
            raise ValueError("SECRET_KEY must be securely configured in production (cannot use default).")
        from urllib.parse import urlsplit
        public_url=urlsplit(settings.PUBLIC_APP_URL)
        if public_url.scheme!='https' or not public_url.hostname or public_url.username or public_url.query or public_url.fragment:
            raise ValueError('PUBLIC_APP_URL must be an HTTPS application URL in production.')
        if settings.SMTP_HOST and not settings.SMTP_FROM:
            raise ValueError('SMTP_FROM must be configured with SMTP_HOST.')
        if settings.SMTP_HOST and not settings.SMTP_USE_TLS:
            raise ValueError('SMTP_USE_TLS must be enabled in production.')
        if not settings.DATABASE_URL or "postgres:postgres@" in settings.DATABASE_URL:
            raise ValueError("DATABASE_URL must not use default credentials in production.")


settings = Settings()
validate_settings(settings)


def get_settings() -> Settings:
    return Settings()
