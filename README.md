# AI Career Agent — 24×7 Job Search & Application Assistant

A privacy-first, human-in-the-loop AI system that continuously discovers relevant job opportunities, verifies their legitimacy, evaluates fit against a professional profile, prepares tailored application materials, and tracks the entire job-search lifecycle.

> **Status:** Phase 1 — Candidate Profile backend foundation in progress.  
> Project foundation and architecture (Phase 0) plus the Phase 1 backend: schema, migration, REST API, and tests.  
> No application automation, scraping, or production integrations are implemented yet.

## Vision

```text
DISCOVER  →  VERIFY  →  MATCH  →  PRIORITIZE  →  PERSONALIZE  →  PREPARE  →  APPROVE  →  APPLY  →  CONTACT  →  TRACK  →  LEARN
```

The agent operates 24×7 in the cloud, but the user remains in control. Sensitive actions such as submitting applications or sending recruiter outreach require explicit approval by default.

## Responsible Automation Principles

* User control and transparency first.
* Privacy and security are non-negotiable.
* All decisions are auditable.
* External websites and job descriptions are treated as untrusted input.
* No CAPTCHA bypass, MFA bypass, anti-bot circumvention, credential harvesting, or spam behavior.
* No automatic submission on sites that prohibit automation.
* No fake identities, fabricated experience, or guessed private contact information.

## Repository Guide

| Path | Purpose |
|------|---------|
| [`PROJECT_PLAN.md`](PROJECT_PLAN.md) | Goals, scope, MVP definition, success metrics |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | High-level system architecture and component interactions |
| [`AGENT_ARCHITECTURE.md`](AGENT_ARCHITECTURE.md) | Agent responsibilities, orchestration, and state management |
| [`DATA_MODEL.md`](DATA_MODEL.md) | Database entities, relationships, and lifecycle states |
| [`SECURITY.md`](SECURITY.md) | Security model, trust boundaries, and PII protection |
| [`ROADMAP.md`](ROADMAP.md) | Phased implementation plan with acceptance criteria |
| [`DEVELOPMENT_GUIDELINES.md`](DEVELOPMENT_GUIDELINES.md) | Coding standards, repo conventions, and quality gates |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How to contribute, commit conventions, review process |
| `docs/adr/` | Architecture Decision Records |
| `docs/architecture/` | Detailed workflow and data-flow diagrams |
| `docs/agents/` | Agent-specific design notes |
| `docs/workflows/` | Step-by-step process flows |
| `docs/security/` | Threat model and compliance notes |
| `src/` | Application source — `src/backend/` holds the Phase 1 backend |
| `tests/` | Test suites |
| `config/` | Configuration templates and examples |
| `scripts/` | Development and operational scripts |

## Phase 1 — Candidate Profile (backend foundation)

The backend foundation for the Candidate Profile Service is implemented in `src/backend/`:

- `models/` — `Candidate`, `CandidateSkill`, `Experience`, `Education`, `Certification`, `Resume`, `ResumeVersion`, `User` (SQLModel).
- `schemas/` — request/response models and validation.
- `repositories/` — persistence layer for profiles, resumes, experience, education, certifications, users, and audit.
- `services/` — profile completeness scoring and resume parsing (PDF/DOCX).
- `api/` — FastAPI routers under `/api/v1`.
- `db/` — SQLAlchemy async engine/session and `EncryptedString` PII type decorator.
- `core/` — settings, security, and audit helpers.

Database migrations live in `migrations/` (Alembic, async template). Run them with:

```bash
alembic upgrade head
```

Run the API locally:

```bash
uvicorn backend.app.main:app --reload
```

Run the quality gates:

```bash
pytest            # tests use SQLite + aiosqlite via tests/conftest.py
ruff check src tests
mypy src
```

## MVP Scope

The first usable MVP proves:

1. Job discovery from permitted sources.
2. Job verification and risk scoring.
3. Candidate-profile matching with an explainable 0–100 score.
4. Resume recommendation and application preparation.
5. Human approval before any external action.
6. Application tracking and notifications.

Automation is added only after the manual workflow is validated.

## Candidate Profile

The system is being built for **Vijay Shrivastava**. The candidate profile will store professional information, skills, experience, target roles, and preferences through the application UI and database. It will be editable and protected; no personal facts are hard-coded in source.

## Technology Direction

* **Backend:** Python + FastAPI
* **Frontend:** Next.js (React)
* **Database:** PostgreSQL + pgvector
* **Queue / Cache:** Redis + Celery
* **Browser automation:** Playwright
* **LLM abstraction:** LangChain/LangGraph with swappable providers
* **Auth:** OAuth2 / OIDC
* **Document storage:** S3-compatible object store
* **Deployment:** Docker, cloud-ready (initial target: container platform)

See [`docs/adr/`](docs/adr/) for the full rationale and alternatives considered.

## 24×7 Operation

An event/queue-based scheduler runs continuously in the cloud. Jobs are discovered, verified, matched, and prepared asynchronously. Human approvals pause external actions. Retries, dead-letter queues, health checks, and idempotency ensure resilience.

