"""FastAPI application bootstrap."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.v1.auth import router as auth_router
from backend.api.v1.candidate import router as candidate_router
from backend.api.v1.certifications import router as certifications_router
from backend.api.v1.education import router as education_router
from backend.api.v1.experience import router as experience_router
from backend.api.v1.resumes import router as resumes_router
from backend.api.v1.skills import router as skills_router
from backend.core.config import get_settings
from backend.core.exceptions import ForbiddenError, NotFoundError, ValidationError


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # noqa: ARG001
    settings = get_settings()
    # Ensure local upload directory exists for development storage.
    if settings.storage_provider == "local":
        settings.storage_local_path.mkdir(parents=True, exist_ok=True)
    yield


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
app.include_router(candidate_router, prefix="/api/v1")
app.include_router(skills_router, prefix="/api/v1")
app.include_router(experience_router, prefix="/api/v1")
app.include_router(education_router, prefix="/api/v1")
app.include_router(certifications_router, prefix="/api/v1")
app.include_router(resumes_router, prefix="/api/v1")
