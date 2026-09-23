# AI Career Agent — 24×7 Job Search & Application Assistant

A privacy-first, human-in-the-loop AI system that continuously discovers relevant job opportunities, verifies their legitimacy, evaluates fit against a professional profile, prepares tailored application materials, and tracks the entire job-search lifecycle.

> **Status:** Master-plan Phases 1–16 are complete and exercised through
> unit + integration tests on both SQLite (test suite) and PostgreSQL 16 (validated
> end-to-end). Highlights: candidate profile + auth/challenges foundation; deterministic
> AI job matching; fact-grounded application prep; job-source strategy with an optional,
> credential-gated Adzuna adapter; ingestion safety (quarantine, idempotent replay);
> recruiter-signal pipeline; outreach with a **recording sender only (outbound = 0)**;
> candidate-scoped approvals + audit-trail API; structured JSON logging; failure recovery
> (DB-level at-most-once guards); security review and maintenance; AI/LLM boundary; scheduler
> OFF by default; and index-parity/performance sanity. The scheduler is OFF by default, no
> AI/LLM SDKs are declared or installed (the AI boundary is enforced at the dependency level),
> and no external AI calls are made.

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
| `docs/architecture/authentication-and-challenges.md` | Auth state machine, challenge workflow, secrets-references design |
| `src/` | Application source — `src/backend/` holds the FastAPI backend, `src/frontend/` holds the Next.js frontend |
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
alembic upgrade head    # current head: f6e5d4c3b2a1
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

## Configuration (`.env`)

Secrets and knobs come from environment variables (see `src/backend/core/config.py`
for the full list). The `.env` file is gitignored. Key settings:

| Variable | Default | Notes |
|----------|---------|-------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | Async engine URL (dev/tests keep `tests/conftest.py` on SQLite) |
| `SECRET_KEY` | `change-me-in-production` | Forbidden (boot error) when `APP_ENV=production` and unset/placeholder |
| `ENCRYPTION_KEY` | unset | Fernet key for PII encryption (store secrets with `generate_encryption_key()`) |
| `APP_ENV` | `development` | `production` enables the SECRET_KEY guard |
| `DISCOVERY_ENABLED` | `false` | Scheduler is **OFF by default**; only explicit opt-in starts runs |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | unset | Optional Adzuna adapter credentials — env-only, never fabricated; missing creds = no network |
| `OUTREACH_ENABLED` | `true` | Sending is plugged to the recording sender (outbound = 0); approval required by default |
| `AUTOMATION_ENABLED` | `true` | Automation runs are recorded only; submission is a future phase |

Structured (JSON) logging is applied at bootstrap (`backend/core/logging_utils.py`),
controlled by `LOG_LEVEL`.

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
* **Database:** PostgreSQL 16 (pgvector not in the declared runtime — matching is rule-based, no embeddings)
* **Queue / Cache:** Redis + Celery (optional `[infra]` extra; not required at runtime — scheduler is in-process and OFF by default)
* **Browser automation:** Playwright (optional `[infra]` extra; unused at runtime today)
* **LLM abstraction:** None. All intelligence is deterministic; LangChain/LangGraph, `pgvector` and all AI SDKs have been **removed from `pyproject.toml`** (the AI boundary is enforced at the dependency level). See [`docs/adr/`](docs/adr/).
* **Auth:** OAuth2 / OIDC
* **Document storage:** S3-compatible object store (local storage provider by default)
* **Deployment:** Docker, cloud-ready (initial target: container platform)

See [`docs/adr/`](docs/adr/) for the full rationale and alternatives considered.

## Authentication & Challenge Management (foundation)

A provider/site-neutral backend foundation that records:

* **Auth providers** — which sites the candidate may need to authenticate to
  (`AuthProvider`), their configured method, and current auth state
  (`AuthProviderState`).
* **Challenges** — when a site asks for human verification (CAPTCHA, MFA/OTP,
  login, bot protection, rate limits), tracked as durable `Challenge` records.
* **Human-in-the-loop workflows** — a challenge pauses the linked `WorkflowRun`;
  it is resumed exactly once after the challenge is closed.
* **References, not secrets** — secrets, sessions, and browser state are stored
  only as opaque references resolved by an injected external secrets provider.

Hard rules: **no** CAPTCHA/MFA/anti-bot bypass, **no** automatic resolution,
**no** secret values stored in the database, logs, tests, or API. Application
automation is a **future phase**; day-to-day site interaction remains fully
manual today. See
[`docs/architecture/authentication-and-challenges.md`](docs/architecture/authentication-and-challenges.md).

## Frontend (Next.js)

The Phase 1 frontend lives in `src/frontend/` and provides the interactive UI for every
Phase 1 feature:

- **Register / Login** — exchange credentials for an HttpOnly session cookie backed by
  the backend token (`/api/auth/{register,login}` route handlers). The token never
  reaches the browser.
- **Profile editor** — basic info, headline, summary, preferences, and completeness.
- **Skills / Experience / Education / Certifications** — CRUD panels against the backend.
- **Resumes** — create containers, upload versions, list, and trigger parsing.
- **Connections** — manage auth providers, sessions, secrets references, and challenges
  (human-in-the-loop).
- **Proxy** (`proxy.ts`) — forwards `/api/v1/*` to the backend, injecting
  `Authorization: Bearer <token>` from the cookie; protected pages redirect to
  `/login` when no session exists.

To run it against a backend on `http://localhost:8000`:

```bash
cd src/frontend
npm install
npm run dev        # development (non-secure cookies over http)
npm run build      # production build
npm start          # production server (expects HTTPS in real deployments)
```

Quality gates: `npm run lint`, `npx tsc --noEmit`, `npm run build`. `API_BASE_URL`
configures the backend origin for both the route handlers and the proxy.

## AI Job Matching (Phase 4)

A deterministic, explainable matching engine that scores a candidate against a job from
0–100 using ten transparent components — skills, role alignment, seniority, years experience,
domain, industry, leadership, location, work mode, and compensation:

- **Job text is untrusted.** Parsing only tokenizes descriptions into skills, years, salary,
  location and work-mode signals; a description can never alter rules, weights, thresholds, or
  policies (prompt-injection invariant covered by tests).
- **Configurable weights.** `MATCH_WEIGHTS` (default sums to 100), `MATCH_THRESHOLD`
  (default `70.0`), `MATCH_RULES_VERSION` (default `3.0.0`).
- **Exploreable output.** Every result carries matched/missing skills, strengths, gaps, blockers,
  recommendation/rejection reasons, and a full component-weighted breakdown.
- **Semantic matching protocol.** `SemanticSkillMatcher` is pluggable; the default is a
  deterministic synonym matcher (a vector matcher may later broaden *related-skill credit* only).
- **Idempotent persistence.** Results are upserted per candidate+job (`job_matches`) and can be
  re-evaluated in batch; the orchestrator path (`score_for_orchestrator`) is backend-usable.

Endpoints:

```text
POST|GET /api/v1/candidates/{candidate_id}/jobs/{job_id}/match
POST     /api/v1/candidates/{candidate_id}/matching/evaluate?limit=&recompute=
GET      /api/v1/candidates/{candidate_id}/matches?is_match=&status=&min_score=&sort=&limit=&offset=
```

## Resume & Application Preparation (Phase 5)

Deterministic, fact-grounded preparation of application materials for a (candidate, job) pair,
built on top of a completed match:

- **Preparation requires a match first.** `prepare` returns 400 unless the job has been evaluated,
  so materials always build on the explainable match output.
- **Never invents facts.** One `Application` per pair owns screening questions, answers, and
  versioned documents (cover letter, tailored resume, answers sheet). Answers and documents are
  assembled only from profile entities (skills, experiences, education, certifications, verified
  compensation) plus the match result; every claim is recorded as `fact_sources` JSON so it can be
  traced back to the profile. Questions that cannot be answered from profile data (motivation,
  missing skills, clearance, relocation, unset compensation) are flagged `requires_review`.
- **Structured hallucination guard.** `FactGroundingValidator` rejects any generated content that
  introduces capitalized proper-noun-like tokens that are not known profile facts, framing words, or
  known skills. The deterministic writer only echoes matched skills that appear in the profile —
  raw match strengths that repeat untrusted job text (e.g. "Apache Kafka") are never copied
  verbatim.
- **Encrypted at rest.** Document content uses `EncryptedString`; each regeneration produces a new
  per-type version number.
- **Best-resume selection.** Active-version + default + resume-type alignment scoring picks the
  resume for the application (or an explicit `resume_id` can be supplied).

Endpoints:

```text
POST /api/v1/candidates/{candidate_id}/applications/jobs/{job_id}/prepare[?resume_id=]
GET  /api/v1/candidates/{candidate_id}/applications?limit=&offset=
GET  /api/v1/candidates/{candidate_id}/applications/{application_id}
GET  /api/v1/candidates/{candidate_id}/applications/{application_id}/documents
POST /api/v1/candidates/{candidate_id}/applications/{application_id}/documents/generate?doc_type=
GET  /api/v1/candidates/{candidate_id}/applications/{application_id}/documents/{document_id}
PUT  /api/v1/candidates/{candidate_id}/applications/{application_id}/questions/{question_id}/answer
POST /api/v1/candidates/{candidate_id}/applications/{application_id}/status?status=
```

## 24×7 Operation

An event/queue-based scheduler runs continuously in the cloud. Jobs are discovered, verified, matched, and prepared asynchronously. Human approvals pause external actions. Retries, dead-letter queues, health checks, and idempotency ensure resilience.

## Observability (audit trail & logging)

* **Audit-trail API** — candidate-scoped, read-only listing of audit events with
  `event_type` / `limit` / `offset` filtering:

  ```text
  GET /api/v1/candidates/{candidate_id}/audit-events?event_type=&limit=&offset=
  ```

  Ownership is enforced via `get_owned_candidate` (cross-user 404) and re-checked in the
  service. Evidence: `tests/integration/api/test_audit.py`.
* **Structured logging** — JSON logging is configured at bootstrap
  (`backend/core/logging_utils.py`, `LOG_LEVEL`); the in-process scheduler emits structured
  events. Evidence: `tests/unit/test_logging.py`.
* **Performance** — model-declared indexes align with the real PG schema (migration
  `f6e5d4c3b2a1` restored `ix_outreach_messages_parent_id` and `ix_outreach_runs_status`;
  audit script reports `ALL DECLARED INDEXES PRESENT` on both PG databases).

