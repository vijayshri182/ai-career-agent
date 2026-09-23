# Verification Evidence

A curated record of verified guarantees across the master plan. All evidence was
collected from the running system (PostgreSQL 16 via `psql` or the in-process test
suite on SQLite) and is reproducible with the commands shown.

## Backend matrices both supported

* Final full pytest suite: **477 tests green** on SQLite (in-memory) in prod/test modes
  (`pytest tests -o addopts=“--strict-markers”`, pytest 9.1.1, exit 0).
* `ruff check src tests` — clean.
* `mypy src` — clean (181 files, strict).

## PostgreSQL (16.11) — Alembic chain and roundtrip

* Dev DB `ai_career_agent`, throwaway test DB `ai_career_agent_test`; both at migration
  head `f6e5d4c3b2a1`; `alembic upgrade head` + `downgrade base` roundtrip passes
  (PG-guarded `DROP TYPE` in the 3 earliest migrations keeps the 20 native enum types clean).
* Native PG enums store UPPERCASE names (challenges, companies); string-backed enums
  store lowercase values (automation_runs, outreach_runs, gate4e, etc.). Index predicates
  match the stored literal case — verified via the enum-audit script.

## Persisted Gate 4E end-to-end (both backends)

Replay of the same artifact produces identical SQLite-vs-PG results (temp script
`validate_persisted_gate4e.py`):

| Metric | SQLite | PG |
|--------|--------|-----|
| Ingestion record totals | 5 | 5 (ACCEPTED_VERIFIED=1, ACCEPTED_PARTIAL=1, QUARANTINED_PARTIAL_NO_URL=3) |
| Jobs created | 2 | 2 |
| Replayed duplicates | 5 idempotent | 5 idempotent (counts unchanged) |
| Signals generated | 3 | 3 |
| Signal quality checks | 9 | 9 |
| Approval + outreach prep | ok | ok |
| Outreach runs / messages sent | 0 / 0 | 0 / 0 (recording sender, no network) |
| Audit events | 15 | 15 |

## Matcher integrity

`src/backend/services/matching.py` SHA-256:
`7CBAF15627C44D57EBD7B49AB1D99479BA96A491D70B42002B16AD0C4CF3BB41` — unchanged.

## Failure recovery (crash safety on PG)

Rows: `outreach_runs` at-most-one-open-run per message is enforced by partial unique
index `uq_outreach_runs_open_message` (status IN pending/running). Live proof
(transaction rolled back; DB left pristine, `runs = 0` afterward):

```sql
INSERT INTO outreach_messages (...) VALUES (...);              -- INSERT 0 1
INSERT INTO outreach_runs (..., status) VALUES (..., 'pending'); -- INSERT 0 1
INSERT INTO outreach_runs (..., status) VALUES (..., 'running'); -- ERROR:
--   duplicate key value violates unique constraint "uq_outreach_runs_open_message"
```

Companion guards verified on PG: `uq_automation_runs_open_app`
(pending/running/paused_human_action), `uq_challenges_open_provider_type`,
`uq_companies_domain_verified`, `uq_recruiter_signals_candidate_identity`,
`uq_gate4e_ingestion_candidate_identity`, `uq_jobs_candidate_url`,
`uq_job_matches_candidate_job`.

Retry/backoff/budget semantics (bounded `max_attempts`, `next_retry_at` backoff,
retry-pending blocks new execution, in-flight challenge blocks retry) are covered by
`test_automation_service.py`, `test_approval_service.py`,
`tests/integration/api/test_application_automation.py`, `test_application_prep.py`,
and the outreach API/flow suites.

## Job-source strategy (Adzuna)

* Credentials are env-only (`ADZUNA_APP_ID`/`ADZUNA_APP_KEY`); missing creds raise a
  clear error and make zero network calls; mode routing via `RoutingAdapter`
  (`crawl_config["mode"] == "adzuna"`); 6 unit tests use a mock transport.
* Ingestion never fabricates URLs (`QUARANTINED_PARTIAL_NO_URL`), identity-based replay
  is idempotent, partial sources never auto-verify.

## Security review highlights

* Candidate ownership enforced via `get_owned_candidate` → 404 for cross-user and
  non-existent candidates (identical observable responses) on every candidate-scoped route.
* CORS locked to `http://localhost:3000` with `allow_credentials=True`.
* No raw SQL in `src` (all parameterized SQLAlchemy); no secrets/tokens/PII in log lines.
* Passwords bcrypt-hashed; emails SHA-256-hashed at rest + Fernet-encrypted; JWT signed
  HS256 with configured `SECRET_KEY` and expiry.
* New boot guard: settings refuse `APP_ENV=production` with a placeholder/unset
  `SECRET_KEY` (`tests/unit/test_settings_guard.py`).

## Scheduler / AI / outbound posture

* `DISCOVERY_ENABLED=false` by default; scheduler only starts on explicit opt-in
  (`test_scheduler_off.py`: default-off assertion, inert-until-started, lifespan starts
  no scheduler when disabled).
* Zero AI calls and zero AI SDKs: `openai`, `langchain*`, `langgraph*`, `pgvector`,
  `tiktoken` removed from `pyproject.toml` dependencies and absent from the venv.
  The boundary is enforced by tests (`test_ai_boundary.py`: no AI SDKs in runtime deps,
  no AI imports anywhere in `src`). Matching/normalization/prep are deterministic; Adzuna
  is the only real external fetch and is credential-gated.
* Outreach send path is plugged to `RecordingSender` (outbound messages = 0); approvals
  required by default; verified-destination + daily-cap + suppression checks enforced.

## Performance sanity (index parity)

* Model-declared indexes vs real PG schema audited (temp script `audit_index_parity.py`):
  only two gaps existed — `outreach_messages.parent_id` was indexed under the non-canonical
  name `ix_outreach_messages_parent`, and `outreach_runs.status` had no index.
* Migration `f6e5d4c3b2a1` renames to `ix_outreach_messages_parent_id` and adds
  `ix_outreach_runs_status`; `alembic downgrade -1` + `upgrade head` roundtrip passes; both
  PG DBs now report `ALL DECLARED INDEXES PRESENT`.
* Candidate-scoped read paths (dashboard summary, audit trail) issue bounded queries — no
  N+1 patterns in the repos inspected.

## Observability

* Candidate-scoped, read-only audit trail API:
  `GET /api/v1/candidates/{candidate_id}/audit-events?event_type=&limit=&offset=`
  (`schemas/audit.py`, `services/audit.py`, `api/v1/audit.py`); ownership enforced via
  `get_owned_candidate` and re-checked in the service; covered by
  `tests/integration/api/test_audit.py` (list/filter/paging, cross-user 404, auth 401).
* Structured JSON logging applied at bootstrap (`backend/core/logging_utils.py`); the
  scheduler emits structured events (`tests/unit/test_logging.py`).## Phases 17-20: deterministic release validation (Sep/Oct 2026)

### Deterministic-only runtime (ADR-011)

* ADR-011 (docs/adr/adr-011-deterministic-only-runtime.md) is **Accepted** and supersedes
  ADR-005: the runtime is deterministic; any AI is bounded assistance whose output is
  untrusted and schema-validated; all authorization/outbound/scheduler/state transitions
  are deterministic and require explicit human approval. ADR-005 is marked Superseded;
  ADR-002/ADR-003 and the ADR index are aligned (pgvector and Redis/Celery are not part of
  the runtime; the scheduler is in-process and **OFF by default**).
* The remaining scope (Phases 3/11/13, dashboard UI, site submission) plus the Phase 17-20
  completion plan are recorded in ROADMAP.md / PROGRESS.md.

### API surface pinned by contract test

* `src/backend/app/main.py` now mounts the (previously unwired) v1 routers
  `dashboard_router` and `notifications_router`; the routers resolve their services from
  the DI container and are feature-flag gated (403 when disabled).
* New contract suite `tests/integration/api/test_app_route_surface.py` (5 tests) pins the
  documented surface against `app.openapi()` (99 paths): health/ready, auth register/login,
  sources (`/job-sources`), contacts discovery, discovery runs, automation, and the
  `POST /jobs/{job_id}/discover-contacts` route. It also asserts no invented
  `/candidates/{candidate_id}/agent-tasks` route exists.
* One invented row ("Agent tasks") was removed from docs/api/api-overview.md.

### Clean-environment PostgreSQL validation

* `scripts/clean_environment.ps1` drops and recreates both dev and test databases, then
  runs `alembic upgrade head` from **empty**: chain `87990926037c (base)` -> ... ->
  `f6e5d4c3b2a1 (head)`, 15 migrations, **single head, linear history**. Both DBs upgraded
  cleanly; dev DB has 41 tables (incl. gate4e_ingestion_records, gate4e_quarantine_records,
  recruiter_signals, applications, outreach_messages, audit_events, notifications).
* Downgrade/upgrade roundtrip at the head passes (`downgrade -1` f6e5d4c3b2a1 ->
  d16a7c9e52b0 and back); no stray/stale migration files ship.
* `audit_index_parity.py` (temp, not committed): `ALL DECLARED INDEXES PRESENT` on both
  fresh DBs; key uniqueness constraints live (uq_outreach_runs_open_message,
  uq_automation_runs_open_app, uq_challenges_open_provider_type,
  uq_companies_domain_verified, uq_recruiter_signals_candidate_identity,
  uq_gate4e_ingestion_candidate_identity, uq_outreach_message_versions_number).
* App smoke on a fresh DB: `uvicorn backend.app.main:app` on 127.0.0.1:8017 ->
  `/health` ok, `/ready` ready, `/api/openapi.json` 99 paths (superUser flags off).

### Security, supply-chain and boundary final audit

* Secret hygiene: `git ls-files` shows no `.env`, key, credential or app-password file
  tracked (only `.env.example`; `.env` is gitignored); no high-entropy secrets in
  tests/fixtures/scripts; no raw SQL; CORS locked to localhost:3000; ownership enforced on
  all candidate-scoped routes; prod `SECRET_KEY` boot guard active.
* Prompt-injection / code-execution: no `eval`/`exec`/`os.system`/`subprocess`/`shell=True`
  in `src`; `recruiter_signal_generation._FORBIDDEN_IMPORTS` AST guard blocks code
  generation/analysis imports; `test_matching.py::test_prompt_injection_in_description_changes_nothing`
  pins prompt-injection invariance.
* Outbound: `make_sender()` returns the network-free `RecordingSender`; the only
  `_sender.send(...)` call site is `OutreachService.send` (services/outreach.py:849), and
  that path requires an approved OUTREACH_SEND approval, verified destination and within
  the daily cap (approval required by default; autonomy-level gate; no auto-send). The
  ingestion/matching/signal/prep pipelines never send.
* Dependency cleanup (pyproject.toml): removed unused `python-jose` (never imported; code
  uses PyJWT), plus its `ecdsa`/`rsa`/`pyasn1` tree; declared `PyJWT>=2.8,<3.0` directly
  (HS256 only). Unused `celery`, `redis`, `playwright`, `sentry-sdk` moved to an optional
  `[infra]` extra (declared for future use; not installed by default). `dev` extra now
  includes the SQLite driver + PyYAML so `pip install -e ".[dev]"` runs the full suite.
  Removed the earlier CVE-2025-71176 (tmpdir) exposure by raising pytest to 9.0.3+.
* `pip-audit`: **No known vulnerabilities found** (exit 0) after the cleanup; the only skip
  is the local package itself (not on PyPI).

### Final regression (post-cleanup environment)

* `pytest tests -o addopts=--strict-markers`: **477 passed, exit 0**.
* `ruff check src tests`: clean. `mypy src`: no issues (181 files, strict).
