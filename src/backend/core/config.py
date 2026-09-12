"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Runtime settings. Secrets come from environment only."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Career Agent"
    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    database_url: str = Field(
        default="postgresql+asyncpg://ai_career_agent:password@localhost:5432/ai_career_agent",
        alias="DATABASE_URL",
    )
    database_echo: bool = False

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    secret_key: str = Field(default="change-me-in-production", alias="SECRET_KEY")
    encryption_key: str | None = Field(default=None, alias="ENCRYPTION_KEY")

    access_token_expire_minutes: int = 60 * 24  # 1 day

    storage_provider: str = Field(default="local", alias="STORAGE_PROVIDER")
    storage_local_path: Path = Field(
        default=PROJECT_ROOT / "data" / "uploads", alias="STORAGE_LOCAL_PATH"
    )
    storage_endpoint: str | None = Field(default=None, alias="STORAGE_ENDPOINT")
    storage_access_key: str | None = Field(default=None, alias="STORAGE_ACCESS_KEY")
    storage_secret_key: str | None = Field(default=None, alias="STORAGE_SECRET_KEY")
    storage_bucket: str = Field(default="ai-career-agent-documents", alias="STORAGE_BUCKET")
    storage_region: str = Field(default="us-east-1", alias="STORAGE_REGION")
    storage_encrypt_files: bool = Field(default=True, alias="STORAGE_ENCRYPT_FILES")

    max_upload_size_bytes: int = 10 * 1024 * 1024  # 10 MB
    allowed_resume_extensions: set[str] = {"pdf", "docx"}

    profile_completeness_weights: str = Field(
        default="basic=15,summary=10,experience=20,skills=15,education=10,certifications=5,preferences=15,resumes=10",
        alias="PROFILE_COMPLETENESS_WEIGHTS",
    )

    discovery_enabled: bool = Field(default=False, alias="DISCOVERY_ENABLED")
    discovery_interval_seconds: int = Field(
        default=21600, alias="DISCOVERY_INTERVAL_SECONDS"
    )
    crawl_user_agent: str = Field(
        default="AI-Career-Agent/0.1 (+privacy-human-in-the-loop)",
        alias="CRAWL_USER_AGENT",
    )
    crawl_timeout_seconds: float = Field(default=20.0, alias="CRAWL_TIMEOUT_SECONDS")
    crawl_backoff_seconds: float = Field(default=2.0, alias="CRAWL_BACKOFF_SECONDS")
    crawl_max_retries: int = Field(default=2, alias="CRAWL_MAX_RETRIES")
    discovery_default_requests_per_minute: int = Field(
        default=10, alias="DISCOVERY_DEFAULT_REQUESTS_PER_MINUTE"
    )

    match_rules_version: str = Field(default="3.0.0", alias="MATCH_RULES_VERSION")
    match_weights: str = Field(
        default=(
            "skills=25,role_alignment=20,seniority=10,years_experience=10,domain=10,"
            "industry=5,leadership=5,location=5,work_mode=5,compensation=5"
        ),
        alias="MATCH_WEIGHTS",
    )
    match_threshold: float = Field(default=70.0, alias="MATCH_THRESHOLD")

    autonomy_level: int = Field(default=2, alias="AUTONOMY_LEVEL")

    automation_enabled: bool = Field(default=True, alias="AUTOMATION_ENABLED")
    automation_max_attempts: int = Field(default=3, alias="AUTOMATION_MAX_ATTEMPTS")
    automation_retry_base_seconds: int = Field(
        default=60, alias="AUTOMATION_RETRY_BASE_SECONDS"
    )

    outreach_daily_limit: int = Field(default=20, alias="OUTREACH_DAILY_LIMIT")
    outreach_approval_required: bool = Field(
        default=True, alias="OUTREACH_APPROVAL_REQUIRED"
    )

    notification_enabled: bool = Field(default=True, alias="NOTIFICATION_ENABLED")


@lru_cache
def get_settings() -> Settings:
    return Settings()
