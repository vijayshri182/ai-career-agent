"""Job source schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from backend.models.job_source import JobSourceType


class _CrawlConfigValidated(BaseModel):
    """Shared crawl_config validation injected into create/update payloads."""

    crawl_config: dict[str, object] | None = None

    @model_validator(mode="after")
    def validate_crawl_config(self) -> "_CrawlConfigValidated":
        config = self.crawl_config
        if config is None:
            return self
        mode = config.get("mode")
        if mode is not None and mode not in {"json", "html"}:
            raise ValueError("crawl_config.mode must be 'json' or 'html'")
        rpms = config.get("requests_per_minute")
        if rpms is not None and (not isinstance(rpms, (int, float)) or rpms < 1):
            raise ValueError("crawl_config.requests_per_minute must be >= 1")
        return self


class JobSourceCreate(_CrawlConfigValidated):
    name: str = "Job feed"
    source_type: JobSourceType = JobSourceType.JOB_BOARD
    base_url: str
    terms_allow_automation: bool = False


class JobSourceUpdate(_CrawlConfigValidated):
    name: str | None = None
    source_type: JobSourceType | None = None
    base_url: str | None = None
    terms_allow_automation: bool | None = None
    is_enabled: bool | None = None


class JobSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    name: str
    source_type: JobSourceType
    base_url: str
    terms_allow_automation: bool
    is_enabled: bool
    crawl_config: dict[str, object]
    last_error: str | None
    last_run_at: datetime | None
    last_success_at: datetime | None
    created_at: datetime
    updated_at: datetime
