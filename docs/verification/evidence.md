# Verification Evidence

A curated record of verified guarantees across the master plan. All evidence was
collected from the running system (PostgreSQL 16 via `psql` or the in-process test
suite on SQLite) and is reproducible with the commands shown.

## Backend matrices both supported

* Full pytest suite: **439 tests green** on SQLite (in-memory) in prod/test modes — `pytest -q`.
* `ruff check src tests` — clean.
* `mypy src` — clean (181 files, strict).

## PostgreSQL (16.11) — Alembic chain and roundtrip

* Dev DB `ai_career_agent`, throwaway test DB `ai_career_agent_test`; both at migration
  head `d16a7c9e52b0`; `alembic upgrade head` + `downgrade base` roundtrip passes
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
  `tiktoken` removed from `pyproject.toml` dependencies and uninstalled from the venv.
  Matching/normalization/prep are deterministic; Adzuna is the only real external fetch
  and is credential-gated.
* Outreach send path is plugged to `RecordingSender` (outbound messages = 0); approvals
  required by default; verified-destination + daily-cap + suppression checks enforced.