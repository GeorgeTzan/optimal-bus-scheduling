import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@db:5432/scheduling"
    )
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24


settings = Settings()
