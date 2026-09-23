# AI Career Agent — Development Guidelines

## 1. Repository Conventions

* **Language:** English for all code, comments, documentation, and commit messages.
* **Branching:** `main` is the default branch. Use feature branches `feature/<short-name>` for changes.
* **Commits:** Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`, `security:`).
* **No secrets:** Never commit credentials, tokens, or `.env` files.

## 2. Technology Stack

* **Backend:** Python 3.12+, FastAPI, Pydantic v2, SQLModel or SQLAlchemy, Alembic.
* **Frontend:** Next.js 14+ (App Router), TypeScript, Tailwind CSS.
* **Database:** PostgreSQL 15+ (pgvector deferred; no embeddings in the current implementation).
* **Queue/Workers:** Redis, Celery, Celery Beat (optional `[infra]` extra; not required at runtime today).
* **Browser automation:** Playwright (Python) (declared; unused by the current pipeline).
* **LLM:** None installed. All intelligence is deterministic; LangChain/LangGraph and AI SDKs are deferred. Do not add AI SDKs without an ADR + explicit approval.
* **Testing:** pytest, Playwright Test, Jest, React Testing Library.

## 3. Code Quality

* Use type hints in Python; strict TypeScript in frontend.
* Format Python with `ruff` / `black`; frontend with `prettier`.
* Lint with `ruff`, `eslint`.
* Keep functions small and focused.
* Prefer explicit over implicit.
* Document non-obvious business logic.

## 4. Project Structure

```text
ai-career-agent/
├── src/
│   ├── backend/
│   │   ├── app/
│   │   ├── agents/
│   │   ├── models/
│   │   ├── services/
│   │   ├── repositories/
│   │   ├── api/
│   │   ├── core/
│   │   └── migrations/
│   ├── frontend/
│   │   ├── app/
│   │   ├── components/
│   │   ├── lib/
│   │   └── styles/
│   ├── agent_workers/
│   └── shared/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── agent/
│   └── e2e/
├── config/
├── docs/
└── scripts/
```

* `src/backend/app/` — FastAPI application bootstrap.
* `src/backend/agents/` — Agent implementations.
* `src/backend/services/` — Business logic and workflows.
* `src/backend/repositories/` — Database access.
* `src/backend/api/` — HTTP routers.
* `src/backend/core/` — Config, security, logging.
* `src/agent_workers/` — reserved for future worker entrypoints (currently empty; Celery is not used in v1.0 — the scheduler is in-process and OFF by default).
* `src/shared/` — Contracts, types, utilities shared between backend/frontend.

## 5. Configuration

* Environment-specific config in `config/*.yaml` and environment variables.
* Use Pydantic `Settings` for validation.
* Commit only `.example` files and templates.
* Secrets loaded from vault or environment at runtime.

## 6. Database

* Schema changes via Alembic migrations.
* All tables have `created_at` and `updated_at`.
* Use enums for status columns.
* Add indexes consciously; measure with `EXPLAIN ANALYZE`.

## 7. Testing Strategy

| Test Type | Scope | Tool |
|-----------|-------|------|
| Unit | Functions, models, utilities | pytest, Jest |
| Integration | API endpoints, repositories | pytest + TestClient |
| Agent | Agent behavior with mocked tools | pytest |
| Prompt | LLM output quality | evaluation datasets |
| Browser | Mock Playwright flows | Playwright Test |
| Security | Dependency scan, secret scan | pip-audit, truffleHog |
| E2E | Full user flows | Playwright |

* Aim for high coverage on core business logic; integration tests for API contracts.
* Recorded HTTP responses (VCR) for external source tests.
* AI outputs evaluated against a curated evaluation dataset.

## 8. AI Output Safety

* LLM outputs must be parsed into strict Pydantic models.
* Validate that generated resumes contain only facts from the profile.
* Always keep a human approval checkpoint before external actions.
* Store prompt versions for reproducibility and regression testing.

## 9. Security & Privacy

* Encrypt PII at the application layer.
* Validate and sanitize all external inputs.
* No plaintext credentials in code, logs, or tests.
* Browser automation isolated in containers.
* Each feature documents its trust boundary.

## 10. Documentation

* Update relevant docs when adding or changing a feature.
* ADRs required for new major technology or architecture decisions.
* Keep README and architecture diagrams current.

## 11. Commit & PR Process

1. Branch from `main`.
2. Make focused commits with clear messages.
3. Open a PR with a description referencing the motivation and scope.
4. Ensure CI passes (lint, tests, secret scan).
5. Request review; merge via squash or merge commit as configured.

## 12. Local Development Setup

```bash
# From the repository root, with PostgreSQL 16 running locally:
copy config\.env.example .env
# fill in DATABASE_URL / SECRET_KEY / ENCRYPTION_KEY
py -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\alembic.exe upgrade head      # current head: f6e5d4c3b2a1
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
.venv\Scripts\python.exe -m pytest
```

Redis/Celery are **not** required for local development (scheduler in-process, OFF by
default). `docker-compose up -d db redis` is available but only PostgreSQL is needed.

## 13. Operational Runbooks

* Deploy via Docker Compose or cloud container service.
* Health endpoints: `/health`, `/ready`.
* Logs in JSON format.
* Alerts for failed jobs, dead-letter queue growth, and security events.
