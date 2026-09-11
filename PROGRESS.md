# Project Progress — Handoff Document

> Authoritative handoff for future ChatGPT/OpenCode sessions. Preserve history;
> do not delete completed workstreams. Never invent or guess status.

## Repo / Git Reference (captured at last check)

| Field | Value |
|-------|-------|
| Repository | `vijayshri182/ai-career-agent` (`git@github.com:vijayshri182/ai-career-agent.git`) |
| Current branch | `main` |
| HEAD SHA | `fa0acd1` (`feat: add phase 1 frontend`) |
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
| WS-6 | Phase 2 — Job Discovery (models, repos, services, adapters, API routers, scheduler, migration, tests) | Complete; pending commit | **NOT committed** (current working tree) |

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

- WS-6 feature + docs: **NOT committed** — commit (e.g. `feat: implement job discovery foundation`),
  push `origin/main`, verify `HEAD == origin/main` and clean tree.

### Known Risks / Issues

1. Phase 3+ (apply flow, enrichments, deployment, Postgres) remains out of scope.
2. The scheduler runs only when `settings.discovery_enabled` is true; background discovery against real
   external sources is not exercised by CI (tests use a stub adapter + MockTransport).
3. No real-world robots.txt corpus is loaded; parser is unit-tested against representative cases.

---

## Next Workstream

1. **Commit + push WS-6** (current working tree) and verify clean tree / `HEAD == origin/main`.
2. **Phase 3 — Applying** — not started, not approved.

## Next Workstream Status

- Approved: **YES for commit/push of WS-6** (Phase 2 completion checkpoint per plan).
- Started: **NO** (Phase 3 not started until WS-6 is committed and verified).
