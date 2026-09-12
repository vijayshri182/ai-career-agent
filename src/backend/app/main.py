"""FastAPI application bootstrap."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.deps import make_discovery_service
from backend.api.v1.applications import router as applications_router
from backend.api.v1.approvals import router as approvals_router
from backend.api.v1.auth import router as auth_router
from backend.api.v1.authentication import router as authentication_router
from backend.api.v1.automation import router as automation_router
from backend.api.v1.candidate import router as candidate_router
from backend.api.v1.certifications import router as certifications_router
from backend.api.v1.discoveries import router as discoveries_router
from backend.api.v1.education import router as education_router
from backend.api.v1.experience import router as experience_router
from backend.api.v1.jobs import router as jobs_router
from backend.api.v1.matching import router as matching_router
from backend.api.v1.outreach import router as outreach_router
from backend.api.v1.recruiter_contacts import router as recruiter_contacts_router
from backend.api.v1.resumes import router as resumes_router
from backend.api.v1.skills import router as skills_router
from backend.api.v1.sources import router as sources_router
from backend.core.config import get_settings
from backend.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from backend.db.engine import make_engine, make_session_factory
from backend.models.candidate import Candidate
from backend.models.job_source import JobSource
from backend.repositories.candidate import CandidateRepository
from backend.repositories.job_source import JobSourceRepository
from backend.services.scheduler import AgentScheduler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # noqa: ARG001
    settings = get_settings()
    # Ensure local upload directory exists for development storage.
    if settings.storage_provider == "local":
        settings.storage_local_path.mkdir(parents=True, exist_ok=True)

    scheduler: AgentScheduler | None = None
    if settings.discovery_enabled:
        engine = make_engine(settings)
        factory = make_session_factory(engine)

        async def _run_discovery(candidate_id: UUID, user_id: UUID) -> None:
            async with factory() as session:
                try:
                    await make_discovery_service(session, settings).run_discovery(
                        candidate_id, user_id
                    )
                    await session.commit()
                except Exception:  # noqa: BLE001
                    await session.rollback()

        async def _get_active_candidates() -> list[Candidate]:
            async with factory() as session:
                return await CandidateRepository(session).list_active()

        async def _get_enabled_sources(candidate_id: UUID) -> list[JobSource]:
            async with factory() as session:
                sources = await JobSourceRepository(session).list_for_candidate(candidate_id)
                return [s for s in sources if s.is_enabled]

        scheduler = AgentScheduler(
            interval_seconds=settings.discovery_interval_seconds,
            run_fn=_run_discovery,
            get_candidates=_get_active_candidates,
            get_sources=_get_enabled_sources,
        )
        scheduler.start()
        app.state.scheduler = scheduler
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.stop()


app = FastAPI(
    title=get_settings().app_name,
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:  # noqa: ARG001
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:  # noqa: ARG001
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)})


@app.exception_handler(ForbiddenError)
async def forbidden_handler(request: Request, exc: ForbiddenError) -> JSONResponse:  # noqa: ARG001
    return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": str(exc)})


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["health"])
async def ready() -> dict[str, str]:
    return {"status": "ready"}


app.include_router(auth_router, prefix="/api/v1")
app.include_router(authentication_router, prefix="/api/v1")
app.include_router(candidate_router, prefix="/api/v1")
app.include_router(skills_router, prefix="/api/v1")
app.include_router(experience_router, prefix="/api/v1")
app.include_router(education_router, prefix="/api/v1")
app.include_router(certifications_router, prefix="/api/v1")
app.include_router(resumes_router, prefix="/api/v1")
app.include_router(sources_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(discoveries_router, prefix="/api/v1")
app.include_router(matching_router, prefix="/api/v1")
app.include_router(applications_router, prefix="/api/v1")
app.include_router(approvals_router, prefix="/api/v1")
app.include_router(automation_router, prefix="/api/v1")
app.include_router(recruiter_contacts_router, prefix="/api/v1")
app.include_router(outreach_router, prefix="/api/v1")
