# AI Career Agent — 24×7 Job Search & Application Assistant

A privacy-first, human-in-the-loop AI system that continuously discovers relevant job opportunities, verifies their legitimacy, evaluates fit against a professional profile, prepares tailored application materials, and tracks the entire job-search lifecycle.

> **Status:** Phase 1 — Candidate Profile backend foundation, Authentication & Challenge Management
> foundation, and the Phase 1 frontend (Next.js) are complete. **Phase 2 — Job Discovery** backend
> foundation (source adapters, robots.txt compliance, normalization, deduplication, freshness,
> scheduler, API routers, migration) is complete and exercised through integration tests.
> **Phase 4 — AI Job Matching** backend (deterministic, explainable ten-component scoring engine,
> untrusted job-text parsing, skills vocabulary + synonym matching, configurable weights/threshold,
> idempotent `job_matches` persistence + migration, candidate-scoped APIs) is complete and exercised
> through unit + integration tests. **Phase 5 — Resume & Application Preparation** backend foundation
> (deterministic best-resume selection, fact-grounded screening questions + answers, versioned
> encrypted documents: cover letter, tailored resume, answers sheet, with structured hallucination
> validation and `fact_sources` traceability) is complete and exercised through unit + integration tests.
> No application automation, submission, or production integrations are implemented yet.

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

