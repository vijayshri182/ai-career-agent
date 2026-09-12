# Project Progress — Handoff Document

> Authoritative handoff for future ChatGPT/OpenCode sessions. Preserve history;
> do not delete completed workstreams. Never invent or guess status.

## Repo / Git Reference (captured at last check)

| Field | Value |
|-------|-------|
| Repository | `vijayshri182/ai-career-agent` (`git@github.com:vijayshri182/ai-career-agent.git`) |
| Current branch | `main` |
| HEAD SHA | `970f449` (`feat: implement recruiter contact discovery`) |
| HEAD == origin/main | **Yes** |
| Upstream | `main` tracks `origin/main`, even |

---

## Workstream History (preserved, oldest → newest)

| # | Workstream | Result | Committed? |
|---|-----------|--------|-----------|
| WS-0 | Phase 0 — project foundation, architecture, ADRs, docs | Complete | `fd4de13` `chore: initialize AI career agent architecture and project plan` |
| WS-1 | Phase 1 — candidate profile backend (models, migration, REST API, services, tests) | Complete, 37 tests | `eee3e2a` `feat: implement candidate profile foundation` |
| WS-2 | Phase 1 — HTTP-layer ownership dependency (`get_owned_candidate`) + parse/apply-parsed workflow | Complete | `8a67306` `docs: update project progress` (doc), `fe8aa29` incl. in Phase 1 completion |
| WS-3 | Phase 1 — hardening: service-layer ownership, safe re-apply, explicit confirmation | Complete, 49 tests | `fe8aa29` `feat: complete phase 1 candidate profile foundation` |
| WS-4 | Phase 1 — authentication & challenge management foundation (provider-neutral auth state, challenges, workflows, secret references) | Complete | `73b5506` `feat: add authentication and challenge management foundation` |
| WS-5 | Phase 1 — Next.js frontend (all profile/resume/connections UI, HttpOnly-cookie auth, `/api/v1` proxy) + backend integration fixes | Complete; committed + pushed | `fa0acd1` `feat: add phase 1 frontend` |
| WS-6 | Phase 2 — Job Discovery (models, repos, services, adapters, API routers, scheduler, migration, tests) | Complete; committed + pushed | `ec9fee7` `feat: implement job discovery foundation` |
| WS-7 | Phase 4 — AI Job Matching (deterministic scoring engine, job-text parsing, skills vocabulary/synonym matcher, persistence + migration, APIs, tests) | Complete; committed + pushed | `eb8abc4` `feat: implement job matching engine` |
| WS-8 | Phase 5 — Resume & Application Preparation (info: backend foundation) | Complete; committed + pushed | `3fe9e79` `feat: implement application preparation foundation` |
| WS-9 | Phase 6 — Human Approval Workflow (approvals + append-only decisions, candidate-scoped API, tests) | Complete; committed + pushed | `cc3f570` `feat: implement human approval workflow` |
| WS-10 | Phase 5/7 — Permitted Application Automation (automation runs, policy gates, challenge handoff, retries, API) | Complete; committed + pushed | `89da2fc` `feat: implement permitted application automation` |
| WS-11 | Phase 8 — Recruiter Contact Discovery (contact sources + contacts, confidence scoring, privacy-safe discovery service, APIs, migration, tests) | Complete; committed + pushed | `970f449` `feat: implement recruiter contact discovery` |

---

## Current Workstream: WS-6 — Phase 2 Job Discovery foundation (backend)

**Project / Phase:** AI Career Agent (ai-career-agent) — Phase 2 (Job Discovery, backend foundation).
**Workstream:** Models, repositories, services, source adapters, API routers, scheduler wiring,
Alembic migration, and tests for discovering/normalizing/deduplicating job postings.

### What Was Implemented

1. **Models + migration** — `Company`, `JobSource`, `Job`, `RawJobExtraction`, `AgentTask`. New tables
   created by hand-written Alembic migration `5e5f4c256726` (`down_revision = 005485fe2c1f`) with
   indexes/unique constraints/FKs. Enum columns store member **NAMEs** (UPPERCASE) — verified with
   SQLite. Job uniqueness is per-candidate (`uq_jobs_candidate_url`, `uq_jobs_candidate_company_external`).
   Company partial unique index uses `'VERIFIED'`. `RawJobExtraction.job` uses string-annotation `"Job"`
   (the MySQL-style `"Job | None"` annotation broke SQLAlchemy mapper resolution).
2. **Source adapters** — `services/adapters/base.py` (`AdapterFetchResult`, `JobSourceAdapter`
   protocol); `generic_http.py` (`GenericHttpAdapter`, `mode:"json"` with `list_path` + dotted
   `selectors`, `mode:"html"` anchor extraction with job-hint filtering).
3. **Services** — `robots.py` (robots.txt policy parser; crawls UA group, allow/disallow,
   crawl-delay; explicit-`*` precedence), `url_validation.py` (scheme/host validation + SSRF guard vs
   private IPs), `normalization.py` (`JobNormalizer`, content hashing, `domain_of`, `parse_utc`),
   `dedup.py` (`JobDedupService.classify` — precedence URL → company+external_id → content hash),
   `freshness.py` (`JobFreshnessService.mark_expired`), `job_source.py` (source CRUD + audit + base_url
   validation), `job.py` (job list/get), `discovery.py` (`DiscoveryService` orchestrator — single
   per-run httpx client, per-source robots cache + crawl-rate limiter, get-or-create company, raw
   extraction capture, agent-task lifecycle, freshness pass, per-source outcome counts),
   `scheduler.py` (`AgentScheduler` for periodic discovery runs, wired in `app/main.py` lifespan when
   `settings.discovery_enabled`).
4. **API routers** — `api/v1/sources.py`, `api/v1/jobs.py`, `api/v1/discoveries.py`, all candidate-
   scoped under `/api/v1/candidates/{candidate_id}/...`. `api/deps.py` gained factory-based DI
   (`get_job_source_service`, `get_job_service`, `get_discovery_service`, `make_discovery_service`).
5. **Tests** — `tests/unit/test_url_validation.py`, `tests/unit/test_robots.py`,
   `tests/unit/test_normalization.py`, `tests/integration/api/test_job_discovery.py` (sources CRUD,
   unsafe-URL rejection, discovery run creates jobs, idempotent re-run, discovery-run listing).

### Files Changed (WS-6, uncommitted)

**New:** `src/backend/models/{company,job_source,job,raw_job_extraction,agent_task}.py`,
`src/backend/schemas/{company,job_source,job,agent_task,discovery}.py`,
`src/backend/repositories/{company,job_source,job,raw_job_extraction,agent_task}.py`,
`src/backend/services/{robots,url_validation,normalization,dedup,freshness,job_source,job,discovery,scheduler}.py`,
`src/backend/services/adapters/{__init__,base,generic_http}.py`,
`src/backend/api/v1/{sources,jobs,discoveries}.py`,
`migrations/versions/5e5f4c256726_add_job_discovery_foundation.py`,
`tests/unit/test_{url_validation,robots,normalization}.py`,
`tests/integration/api/test_job_discovery.py`.

**Modified:** `src/backend/app/main.py` (routers + scheduler lifespan), `src/backend/api/deps.py`
(discovery DI), `src/backend/repositories/base.py` (added `flush`), `src/backend/repositories/job.py`
(`find_identical`, `_first_where`), `src/backend/repositories/agent_task.py` (`list_for_candidate`),
`README.md`, `ROADMAP.md`, `PROGRESS.md`.

### Tests Executed & Exact Results

| Gate | Command | Result |
|------|---------|--------|
| Backend tests | `.venv\Scripts\python.exe -m pytest` | **134 passed** (was 100 in WS-5) |
| Backend lint | `.venv\Scripts\python.exe -m ruff check src/backend tests` | All checks passed |
| Backend types | `.venv\Scripts\python.exe -m mypy src/backend` | Success: no issues in 106 files |

Notable bugs fixed during WS-6: `crawl_config` validator rejected a source lacking
`requests_per_minute` (only validate when present); robots parser dropped `crawl-delay` lines and
groups lacking allow/disallow; discovery tests created sources disabled (must enable before a run).

### Commit Status / Next Step

- WS-6 committed + pushed: `ec9fee7` `feat: implement job discovery foundation`; `HEAD == origin/main`,
  working tree clean.

### Known Risks / Issues

1. Phase 3+ (apply flow, enrichments, deployment, Postgres) remains out of scope.
2. The scheduler runs only when `settings.discovery_enabled` is true; background discovery against real
   external sources is not exercised by CI (tests use a stub adapter + MockTransport).
3. No real-world robots.txt corpus is loaded; parser is unit-tested against representative cases.

---

## Current Workstream: WS-7 — Phase 4 AI Job Matching (backend)

**Project / Phase:** AI Career Agent (ai-career-agent) — Phase 4 (AI Job Matching, backend).
**Workstream:** Deterministic, explainable job-matching engine: job-text parsing, candidate profile
projection, ten-component weighted scoring, skills vocabulary + synonym matching, idempotent
persistence (`job_matches`), Alembic migration, canddate-scoped APIs, and tests.

### What Was Implemented

1. **Models + migration** — `JobMatch` + `JobMatchStatus` (PENDING/MATCHED/REJECTED) in
   `models/job_match.py`; new table `job_matches` by hand-written migration `6b7f1d3c8a22`
   (`down_revision = 5e5f4c256726`) with `uq_job_matches_candidate_job` unique constraint, indexes on
   `candidate_id`/`job_id`/`status`/`is_match`, JSON text columns, `rules_version`, `evaluated_at`.
   Verified apply + downgrade on a fresh SQLite DB. Enum columns store member NAMEs (UPPERCASE).
2. **Skills vocabulary** — `services/skills.py`: `SKILLS` (~140 skills), `SYNONYMS`, `RELATED`,
   `EXTRACTION_PATTERNS`, `canonical_skill()`, `SkillExtractor`, and the `SemanticSkillMatcher`
   protocol with deterministic `SynonymSkillMatcher` (default) and `NoopSkillMatcher` stubs. A
   vector/embedding matcher is allowed later but may only *broaden related-skill credit*, never weaken
   hard requirements.
3. **Scoring engine** — `services/matching.py`: `ScoreWeights` (`MATCH_WEIGHTS`, defaults sum to 100;
   partial overrides keep other defaults; scorer normalizes by total), `JobTextParser` (line-preserving
   section detection for required vs preferred skills, years, salary scales LPA/lakh/k, work modes,
   clearance, work authorization), stateless `JobMatchScorer.score(candidate, job)` → `MatchOutput`
   (score, confidence, is_match, matched/missing/transferable skills, strengths, gaps, blockers,
   recommendation/rejection reasons, full breakdown). Blocker semantics: missing required skills, hard
   years gap, disclosed compensation below expectation, security clearance, and work authorization are
   blockers; unknown candidate data never blocks. Determinism: no timestamps inside the breakdown.
4. **Service + repository** — `JobMatchingService` (`evaluate`, `batch_evaluate`, `score_for_orchestrator`
   for the future 24×7 layer, `get_for_job`, `list` with filters/sort); `repositories/job_match.py`
   (`get_for_job`, idempotent `upsert`, `list_for_candidate`, `count_for_candidate`).
   `repositories/skill.py` gained `list_for_candidate`.
5. **Config + API** — `core/config.py` adds `match_rules_version` (default `3.0.0`), `match_weights`,
   `match_threshold` (default `70.0`). `api/deps.py` gains `get_job_matching_service`; new router
   `api/v1/matching.py` registered in `app/main.py`:
   `POST|GET /api/v1/candidates/{candidate_id}/jobs/{job_id}/match`,
   `POST /api/v1/candidates/{candidate_id}/matching/evaluate` (limit, recompute),
   `GET /api/v1/candidates/{candidate_id}/matches`.
6. **Tests** — `tests/unit/test_matching.py` (10 components, full-match high score, skill gaps +
   rejection below threshold, clearance blocker, prompt-injection invariance, deterministic
   reproducibility, remote preference, weights parse, years/salary parsing, required vs preferred
   sections, canonical aliases, telecom extraction, synonym suggestions) and
   `tests/integration/api/test_job_matching.py` (evaluate endpoint, idempotency, list filters/sort,
   batch evaluate, 404 before evaluation).

### Files Changed (WS-7)

**New:** `src/backend/models/job_match.py`, `src/backend/schemas/matching.py`,
`src/backend/repositories/job_match.py`, `src/backend/services/{matching,skills}.py`,
`src/backend/api/v1/matching.py`, `migrations/versions/6b7f1d3c8a22_add_job_matching_foundation.py`,
`tests/unit/test_matching.py`, `tests/integration/api/test_job_matching.py`.

**Modified:** `src/backend/models/{__init__,candidate,job}.py` (job-match relationship),
`src/backend/repositories/skill.py` (`list_for_candidate`), `src/backend/core/config.py`,
`src/backend/api/deps.py`, `src/backend/app/main.py`, `README.md`, `ROADMAP.md`, `PROGRESS.md`.

### Tests Executed & Exact Results

| Gate | Command | Result |
|------|---------|--------|
| Backend tests | `.venv\Scripts\python.exe -m pytest` | **167 passed** (was 134 in WS-6) |
| Backend lint | `.venv\Scripts\python.exe -m ruff check src/backend tests` | All checks passed |
| Backend types | `.venv\Scripts\python.exe -m mypy src/backend` | Success: no issues in 112 files |
| Migration | `alembic upgrade head` / `downgrade 5e5f4c256726` | apply + downgrade OK on fresh DB |

Notable fixes during WS-7: newline-preserving text normalization so section-aware skill parsing works
(`normalize_text` collapsed newlines, breaking required/preferred detection); salary parsing required a
currency/scale signal (avoided treating `5-8 years` as a salary); "Responsibility:"-style duty lines no
longer harvested as required skills; gaps semantics now include blockers (missing skills surface in
`gaps`), blockers are per-component; removed timestamp from breakdown for exact reproducibility;
weights test asserts partial-override total (not forced to 100).

### Commit Status / Next Step

- WS-7 committed + pushed: `eb8abc4` `feat: implement job matching engine`; `HEAD == origin/main`,
  working tree clean.

### Known Risks / Issues

1. No vector/embedding semantic matcher yet (pluggable protocol exists; deterministic synonym default).
2. No LLM involvement in scoring by design — deterministic and fully explainable (per requirements).
3. Postgres-specific SQL not exercised (development DB is SQLite).

---

## Current Workstream: WS-8 — Phase 5 Resume & Application Preparation (backend, first increment)

**Project / Phase:** AI Career Agent (ai-career-agent) — Phase 5 (Resume & Application Preparation,
backend foundation — the plan refers to this as Phase 5; mission conversation labels it Phase 4).

**Workstream:** Create one application per (candidate, job): deterministic best-resume selection,
screening questions with fact-grounded answers, versioned generated documents (cover letter, tailored
resume, answers sheet), encrypted document content, ownership-enforced APIs, Alembic migration.

### What Was Implemented

1. **Models + migration** — `models/application.py`: `Application`, `ApplicationQuestion`,
   `ApplicationAnswer`, `ApplicationDocument` plus enums `ApplicationStatus` (draft/ready/submitted/
   withdrawn), `QuestionCategory`, `AnswerStatus` (auto/requires_review/manual), `DocumentType`
   (cover_letter/tailored_resume/answers_sheet/other). Tables `applications`,
   `application_questions`, `application_answers` (unique per question), `application_documents`
   (per-doc-type `version_number`; content stored with `EncryptedString`). Relationships
   `applications` added to Candidate/Job/Resume. Hand-written migration `b2fe40980eea`
   (`down_revision = 6b7f1d3c8a22`); enum columns are `sa.String(N)` matching the SQLModel
   lowercased-values convention verified in prior phases; apply + full downgrade verified on a fresh
   SQLite DB.
2. **Deterministic writer** — `services/application_prep.py`: `ProfileFacts` (fact corpus = candidate,
   skills, experiences, education, certifications + verified job title / company name — job body is
   **untrusted**), `FactGroundingValidator` (capitalized-token claim check; flags invented companies/
   skills/qualifications; framing vocabulary for prose + question stems), `ApplicationWriter` ABC +
   `DeterministicApplicationWriter`. Answers/documents are assembled only from profile entities so
   nothing invents facts; questions never answerable from profile (motivation, missing skills,
   compensation when unset, clearance, relocation) default to `requires_review`. `GENERATION_RULES_VERSION
   = "1.0.0"` stamped on generated documents. Cover-letter / skills-answer narrative only echoes
   matched skills that appear in the candidate profile (raw match strengths may repeat untrusted job
   text like "Apache Kafka" and are therefore never copied verbatim into generated content).
3. **Service + repositories** — `ApplicationPrepService` (`prepare` requires an existing match —
   `ValidationError`/400 otherwise; returns existing non-withdrawn application idempotently),
   `generate_document` (per-doc-type versioning + `fact_sources` JSON), `update_answer` (forces
   `MANUAL`), `update_status`, candidate-scoped detail/list. Repos in `repositories/application.py`
   (`BaseRepository` CRUD, `get_detailed` with selectinload for questions→answer + documents, per-type
   `next_version_number`).
4. **Config + API** — `api/deps.py` gains `get_application_prep_service`; router `api/v1/applications.py`
   registered under `/api/v1`:
   `POST /api/v1/candidates/{candidate_id}/applications/jobs/{job_id}/prepare`,
   `GET .../applications`, `GET .../applications/{application_id}`
   (detail with questions/answers/documents), `GET .../applications/{id}/documents`,
   `POST .../applications/{id}/documents/generate?doc_type=...`, `GET .../documents/{document_id}`,
   `PUT .../applications/{id}/questions/{question_id}/answer`,
   `POST .../applications/{id}/status?status=...`. All routes depend on `get_owned_candidate`
   (404 for cross-user/non-existent) + `handle_domain_error` mapping.
5. **Tests** — `tests/unit/test_application_prep_writer.py` (13): fact-grounded question generation,
   auto vs requires-review classification, compensation-missing → review, missing-skill questions,
   all three documents pass the grounding validator, invented capitalized company flagged, known skill
   not in profile flagged, framing prose passes, resume-type scoring, fact sources traceable, resume
   selection, no-match guard. `tests/integration/api/test_application_prep.py` (7): prepare requires
   existing match (400), prepare creates application + ≥4 questions + 3 versioned documents with
   `generation_version` and `fact_sources`, idempotent prepare, generate creates new version per
   doc type, update_answer → manual, status flow, cross-candidate 404/empty.

### Files Changed (WS-8)

**New:** `src/backend/models/application.py`, `src/backend/schemas/application.py`,
`src/backend/repositories/application.py`, `src/backend/services/application_prep.py`,
`src/backend/api/v1/applications.py`,
`migrations/versions/b2fe40980eea_add_application_preparation_foundation.py`,
`tests/unit/test_application_prep_writer.py`, `tests/integration/api/test_application_prep.py`.

**Modified:** `src/backend/models/{__init__,candidate,job,resume}.py` (application relationship),
`src/backend/api/deps.py`, `src/backend/app/main.py`, `README.md`, `ROADMAP.md`, `PROGRESS.md`.

### Tests Executed & Exact Results

| Gate | Command | Result |
|------|---------|--------|
| Backend tests | `.venv\Scripts\python.exe -m pytest` | **187 passed** (was 167 in WS-7) |
| Backend lint | `.venv\Scripts\python.exe -m ruff check src/backend tests` | All checks passed |
| Backend types | `.venv\Scripts\python.exe -m mypy src/backend` | Success: no issues in 117 files |
| Migration | `alembic upgrade head` / `downgrade base` / `upgrade head` | apply + full downgrade + re-apply OK on fresh DB |

Notable fixes during WS-8: `"Resume | None"`-style string relationship annotations broke SQLAlchemy
mapper resolution (switched to `Optional["Resume"]`); `ApplicationDocument.content` widened to
`EncryptedString(65535)` so resumes fit; the answers-sheet grounding check validates only auto-answer
lines (question stems echo untrusted job text and "requires manual input" is not a claim); cover-letter
and skills-answer narrative grounded to profile skills only (no verbatim match strengths).

### Commit Status / Next Step

- WS-8 committed + pushed: `3fe9e79` `feat: implement application preparation foundation`.
- Next: Phase 6 approval workflow (WS-9) — since completed.

### Known Risks / Issues

1. PDF generation for tailored resume is deferred (content is stored as encrypted text; PDF/export is a
   later increment).
2. LLM-backed cover-letter drafting is intentionally not implemented — deterministic writer only, per
   the fact-grounding mandate.
3. Postgres-specific SQL not exercised (development DB is SQLite).

---

## Current Workstream: WS-9 — Phase 6 Human Approval Workflow (backend)

**Project / Phase:** AI Career Agent (ai-career-agent) — Phase 6 (Human Approval Workflow, backend).
**Workstream:** Explicit human-in-the-loop gate before external actions (application submission, and
later outreach send): `approvals` records with an append-only `approval_decisions` log, candidate-scoped
APIs, state-machine service, audit mirroring, and tests.

### What Was Implemented

1. **Models + migration** — `models/approval.py`: `Approval` (kind application_submission/outreach_send,
   status pending/approved/rejected/snoozed/cancelled, generic `target_type`+`target_id`, optional
   `application_id` FK, autonomy-level snapshot, summary/context JSON, decided_by/at + note,
   `snoozed_until`) and append-only `ApprovalDecision`. Migration `c3a0912b7d01`
   (`down_revision = b2fe40980eea`); apply + full downgrade + re-apply verified on fresh SQLite.
2. **Service** — `services/approval.py`: `ApprovalService` (candidate-scoped, actor derived from the
   owned candidate, ownership re-checked in service). `request_approval` is idempotent (one open
   approval per candidate/kind/target). `decide` enforces the state machine
   (pending|snoozed → approved/rejected/cancelled; pending → snoozed with future `until`); terminal
   states reject further decisions with `ValidationError`. Every decision written to
   `approval_decisions` (append-only) and mirrored to `audit_events`.
3. **Config + API** — `AUTONOMY_LEVEL` (default 2 = prepare + approve). Router `api/v1/approvals.py`
   under `/candidates/{candidate_id}`: list/get, approve/reject/snooze/cancel, and
   `POST /candidates/{cid}/applications/{application_id}/approval-request` (builds context from the
   prepared application). All routes depend on `get_owned_candidate` + `handle_domain_error`.
4. **Tests** — `tests/unit/test_approval_service.py` (9): idempotent request, state transitions,
   snooze validation, terminal-state guard, ownership-hiding, decisions recorded, list filters and
   counts. `tests/integration/api/test_approval_workflow.py` (4): request flow (idempotent, listing),
   approve→reject 400 on terminal, decisions readable, snooze/cancel, cross-user 404.

### Files Changed (WS-9)

**New:** `src/backend/models/approval.py`, `src/backend/schemas/approval.py`,
`src/backend/repositories/approval.py`, `src/backend/services/approval.py`,
`src/backend/api/v1/approvals.py`,
`migrations/versions/c3a0912b7d01_add_approval_workflow_foundation.py`,
`tests/unit/test_approval_service.py`, `tests/integration/api/test_approval_workflow.py`.

**Modified:** `src/backend/models/__init__.py` (exports), `src/backend/models/candidate.py`
(`approvals` relationship), `src/backend/core/config.py` (autonomy level), `src/backend/api/deps.py`
(`get_approval_service`), `src/backend/app/main.py` (router), `PROGRESS.md`.

### Tests Executed & Exact Results

| Gate | Command | Result |
|------|---------|--------|
| Backend tests | `.venv\Scripts\python.exe -m pytest` | **200 passed** (was 187 in WS-8) |
| Backend lint | `.venv\Scripts\python.exe -m ruff check src/backend tests` | All checks passed |
| Backend types | `.venv\Scripts\python.exe -m mypy src/backend` | Success: no issues in 122 files |
| Migration | `alembic upgrade head` / `downgrade base` / `upgrade head` | apply + full downgrade + re-apply OK on fresh DB |

### Commit Status / Next Step

- WS-9 committed + pushed: `cc3f570` `feat: implement human approval workflow`; `HEAD == origin/main`,
  working tree clean.
- Next: **WS-10 — Phase 5 Permitted Application Automation** (policy check, workflow state machine,
  challenge handoff, duplicate-submission prevention, audit).

---

## Current Workstream: WS-10 — Phase 7 Permitted Application Automation (backend)

**Project / Phase:** AI Career Agent (ai-career-agent) — Phase 7 completion: application automation
runtime. Builds on application preparation (WS-8) and the human approval workflow (WS-9).

### What Was Implemented

1. **Models + migration** — `models/automation_run.py`: `AutomationRun` + `AutomationRunStatus`
   (pending/running/submitted/paused_human_action/failed/cancelled) with a partial unique index
   `uq_automation_runs_open_app` on `application_id` (one non-terminal run per application — no double
   submission). Soft references (provider_id, challenge_id, workflow_id) never hold secrets. Migration
   `d4e5f6a7b8c1` (`down_revision = c3a0912b7d01`); apply + full downgrade + re-apply verified on fresh
   SQLite. `candidate.py`/`application.py` gained `automation_runs` relationships; exports added to
   `models/__init__.py`.
2. **Adapters** — `services/automation_adapter.py`: `ApplicationSubmitter` protocol +
   `SubmitOutcome`/`SubmissionPayload`; `RecordingSubmitter` (default, injectable) records a submission
   for a source with explicit permission — no network/browser automation. Real ATS adapters plug in
   behind the protocol and must keep the policy gates in the service.
3. **Service** — `services/application_automation.py` (`ApplicationAutomationService`): execution is
   gated on (a) candidate ownership (defense-in-depth re-check), (b) `automation_enabled` +
   `autonomy_level >= 2`, (c) `JobSource.terms_allow_automation` + enabled source, (d) an APPROVED
   approval for exactly this application (`get_approved_for_target`; still-pending blocks with a clear
   error), (e) no active run and no retry-pending failed run. Challenge outcomes (CAPTCHA/MFA/bot
   protection) pause the run (`paused_human_action`), auto-create an `AuthProvider` via
   `AuthProviderService.get_or_create_for_site` ("ATS automation: {company}") and hand off to
   `ChallengeService.ensure_open` (workflow created + paused once; challenge marked
   `human_action_required` without re-pausing). Retry is allowed for `paused_human_action` and
   retry-pending `failed` runs, blocked while the linked challenge is still in-flight
   (open/acknowledged/human_action_required), capped by `max_attempts` with exponential backoff
   (`next_retry_at = now + retry_base_seconds * 2**attempts`). Every transition is mirrored to
   `audit_events` (`automation.run_started`, `automation.run_submitted`,
   `automation.challenge_detected`, `automation.run_failed`, `application.submitted`, ...) and a
   successful submission flips the application to `submitted`.
4. **Config + API** — settings `automation_enabled`/`automation_max_attempts`/
   `automation_retry_base_seconds`. Router `api/v1/automation.py` under `/candidates/{candidate_id}`:
   `POST .../applications/{application_id}/execute`, `GET .../automation/runs` (status filter +
   pagination), `GET .../automation/runs/{run_id}`, `POST .../automation/runs/{run_id}/retry`,
   `GET .../automation/status`. Deps gained `get_application_automation_service`; router wired in
   `app/main.py`.
5. **Tests** — `tests/unit/test_automation_service.py` (14): approval required, blocked-while-pending,
   source-permission required, autonomy gate, happy-path submit (run + application status), cannot
   re-execute submitted application, challenge handoff pauses run, challenge-in-flight blocks retry,
   retry-after-resolve submits, retryable failure schedules backoff, attempt-budget exhaustion, failed
   retry-pending blocks new execute, cross-candidate 404, filtered list/summary.
   `tests/integration/api/test_application_automation.py` (3): execute requires approval then submits +
   status/list/detail/retry guards, challenge handoff via dependency override
   (`get_application_automation_service`), candidate-scoped 404.

### Files Changed (WS-10)

**New:** `src/backend/models/automation_run.py`, `src/backend/repositories/automation_run.py`,
`src/backend/services/automation_adapter.py`, `src/backend/services/application_automation.py`,
`src/backend/schemas/automation.py`, `src/backend/api/v1/automation.py`,
`migrations/versions/d4e5f6a7b8c1_add_application_automation_foundation.py`,
`tests/unit/test_automation_service.py`, `tests/integration/api/test_application_automation.py`.

**Modified:** `src/backend/models/__init__.py` (exports), `src/backend/models/candidate.py` +
`src/backend/models/application.py` (`automation_runs` relationships), `src/backend/core/config.py`
(automation settings), `src/backend/repositories/approval.py` (`get_approved_for_target`),
`src/backend/services/authentication_provider.py` (`get_or_create_for_site`), `src/backend/api/deps.py`
(`get_application_automation_service` + `AutomationRunRepository` import), `src/backend/app/main.py`
(router), `PROGRESS.md`.

### Tests Executed & Exact Results

| Gate | Command | Result |
|------|---------|--------|
| Backend tests | `.venv\Scripts\python.exe -m pytest` | **217 passed** (was 200 in WS-9) |
| Backend lint | `.venv\Scripts\python.exe -m ruff check src/backend tests` | All checks passed |
| Backend types | `.venv\Scripts\python.exe -m mypy src/backend` | Success: no issues in 128 files |
| Migration | `alembic upgrade head` / `downgrade base` / `upgrade head` | apply + full downgrade + re-apply OK on fresh DB |

Notable bugs fixed during WS-10: double-pausing the workflow in challenge handoff (`escalate` re-paused
an already-paused workflow → removed, challenge set to `human_action_required` directly); `retry` must
allow `paused_human_action` as a *source* (only pending/running/cancelled are blocked outright) and
must gate on the linked challenge being resolved; status columns load as `str` from `String(24)` so
messages use `{run.status}` not `.value`; `list_runs` total now respects the status filter
(`count_for_candidate` gained an optional status arg).

### Commit Status / Next Step

- WS-10 committed + pushed: `89da2fc` `feat: implement permitted application automation`; `HEAD ==
  origin/main`, working tree clean.
- Next: **WS-11 — Phase 8 Recruiter Contact Discovery**.

---

## Current Workstream: WS-11 — Phase 8 Recruiter Contact Discovery (backend)

**Project / Phase:** AI Career Agent (ai-career-agent) — Phase 8 (Recruiter Contact Discovery,
backend). Builds on job discovery (WS-6), job matching (WS-7), application prep (WS-8), approvals
(WS-9) and automation (WS-10).

### What Was Implemented

1. **Models + migration** — `models/recruiter_contact.py`: `ContactSource` (`contact_sources` — the
   public evidence page behind a discovery pass; source_type career_page/team_page/directory/
   professional_network/other_public, discovered_at) and `RecruiterContact` (`recruiter_contacts` —
   candidate-scoped, company-scoped record: full_name, role_title, public_profile_url (the evidence
   link), email (only ever a publicly listed, source-exposed address — **guessed emails are never
   stored**), confidence_score 0–100, contact_type verified/guessed, is_suppressed, verification_details
   JSON). Unique `(candidate_id, public_profile_url)` dedup key. Relationships wired on
   Candidate/Company/Job (+ContactSource). Migration `d5e6f7a8b9c2` (`down_revision = d4e5f6a7b8c1`);
   apply + full downgrade + re-apply verified on fresh SQLite.
2. **Confidence scorer** — `services/recruiter_confidence.py` (`AffiliationConfidenceScorer`,
   `is_recruiting_role` keyword matching): deterministic, explainable scoring
   (company-domain evidence +45, plainly recruiting role +20, linked public profile +20, name/role/
   evidence all present +10, publicly-listed email bonus +5, clamped 0–100). VERIFIED requires
   on-company-domain evidence AND a plainly recruiting role; `surfaced = score >= 70 AND VERIFIED`.
   Domain mismatch or missing domain never earns verified credit (privacy-first affiliation check).
3. **Directory adapter** — `services/recruiter_directory.py`: `DirectoryPerson` (with
   `email_publicly_listed` flag — may only be True when the public source explicitly exposed the
   address), `RecruiterDirectoryFetcher` protocol + `EmptyDirectoryFetcher` default + `make_directory_fetcher`. Discovery is network-free until a real public-directory adapter is plugged in (WS-6 adapter pattern).
4. **Service + repos** — `services/recruiter_discovery.py` (`RecruiterDiscoveryService`):
   `discover_for_job(job_id)` fetches, scores, dedupes by profile URL, persists ContactSource + contact,
   suppresses anything not surfaced (stored but never listed/emailed), and audits
   (`recruiter_contact.evaluated` per person incl. `email_guessed_blocked`, `recruiter_contacts.discovered`
   summary). `list_contacts(company_id/job_id/limit/offset)` returns only VERIFIED + unsuppressed
   contacts; `get_contact` candidate-scoped; ownership re-checked via `get_for_user_or_404`
   (defense-in-depth, 404 for cross-candidate). Repos in `repositories/recruiter_contact.py`
   (`RecruiterContactRepository` + `ContactSourceRepository`).
5. **API** — `api/v1/recruiter_contacts.py` under `/candidates/{candidate_id}`:
   `POST .../jobs/{job_id}/discover-contacts` (summary found/created/existing_skipped/hidden +
   evaluated contacts) and `GET .../recruiter-contacts` (surfaced only, filters/pagination);
   `get_recruiter_discovery_service` in `api/deps.py` (default empty fetcher), router in `app/main.py`.
6. **Tests** — `tests/unit/test_recruiter_confidence.py` (9): keyword matching, verified-on-domain
   surfaced, exact-70 boundary surfaced, below-threshold never surfaced, domain required for verified,
   recruiting-role required even on domain, clamp to 100, email-bonus boundary, unverifiable reasons.
   `tests/unit/test_recruiter_discovery.py` (7): empty run finds nothing, verified surfaced + guesses
   hidden, guessed email never stored (vs publicly-listed stored), dedupe on re-run, cross-candidate
   404 (discover/list/get), unknown job 404.
   `tests/integration/api/test_recruiter_contacts.py` (4): discover surfaces only verified, guessed
   email never returned, candidate scoping 404, unknown job discovery 404.

### Files Changed (WS-11)

**New:** `src/backend/models/recruiter_contact.py`, `src/backend/repositories/recruiter_contact.py`,
`src/backend/services/recruiter_confidence.py`, `src/backend/services/recruiter_directory.py`,
`src/backend/services/recruiter_discovery.py`, `src/backend/schemas/recruiter_contact.py`,
`src/backend/api/v1/recruiter_contacts.py`,
`migrations/versions/d5e6f7a8b9c2_add_recruiter_contact_foundation.py`,
`tests/unit/test_recruiter_confidence.py`, `tests/unit/test_recruiter_discovery.py`,
`tests/integration/api/test_recruiter_contacts.py`.

**Modified:** `src/backend/models/__init__.py` (exports), `src/backend/models/{candidate,company,job}.py`
(relationships), `src/backend/api/deps.py` (`get_recruiter_discovery_service`),
`src/backend/app/main.py` (router), `PROGRESS.md`.

### Tests Executed & Exact Results

| Gate | Command | Result |
|------|---------|--------|
| Backend tests | `.venv\Scripts\python.exe -m pytest` | **236 passed** (was 217 in WS-10) |
| Backend lint | `.venv\Scripts\python.exe -m ruff check src/backend tests` | All checks passed |
| Backend types | `.venv\Scripts\python.exe -m mypy src/backend` | Success: no issues in 135 files |
| Migration | `alembic upgrade head` / `downgrade base` / `upgrade head` | apply + full downgrade + re-apply OK on fresh DB |

Notable fixes during WS-11: `Relationship` optional annotations must use `Optional["X"]` (the
`"X" | None` form raises TypeError at class-body evaluation); `_build_persisted_contact` is async
(missing `await` crashed the loop); `_on_company_domain` requires an explicitly matching claimed domain
(missing/unrelated domains earn no verified credit), so a stranger candidate's `list_contacts` raises
NotFoundError rather than returning empty (consistent privacy behaviour).

### Commit Status / Next Step

- WS-11 committed + pushed: `970f449` `feat: implement recruiter contact discovery`; `HEAD == origin/main`,
  working tree clean.
- Next: **WS-12 — Phase 9 Outreach Engine**.

---

## Next Workstream

1. **WS-12 — Phase 9 Outreach Engine** — pending.
2. Then: Phase 12 Learning & Analytics, Phase 10 Notifications/Dashboard, Phase 11 24×7 Orchestration,
   Phase 13 Production Hardening, frontend dashboard completion, final QA.

## Next Workstream Status

- Approved: **auto-continue per mission directive** (finish the product end-to-end).
- Started: **NO** — WS-11 checkpoint committed (`970f449`) and verified; WS-12 begins next.
