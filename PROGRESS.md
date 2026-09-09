# Project Progress — Handoff Document

> Authoritative handoff for future ChatGPT/OpenCode sessions. Preserve history;
> do not delete completed workstreams. Never invent or guess status.

## Repo / Git Reference (captured at last check)

| Field | Value |
|-------|-------|
| Repository | `vijayshri182/ai-career-agent` (`git@github.com:vijayshri182/ai-career-agent.git`) |
| Current branch | `main` |
| HEAD SHA | `eee3e2a5fc28490a39937ac5db63414514e73654` |
| HEAD == origin/main | **Yes** (identical after `git fetch origin main`) |
| HEAD == origin/master | N/A — remote default branch is `main`; no `origin/master` ref exists |
| Upstream | `main` tracks `origin/main`, even (no ahead/behind) |

---

## Workstream History (preserved, oldest → newest)

| # | Workstream | Result | Committed? |
|---|-----------|--------|-----------|
| WS-0 | Phase 0 — project foundation, architecture, ADRs, docs | Complete | `fd4de13` `chore: initialize AI career agent architecture and project plan` |
| WS-1 | Phase 1 — candidate profile backend (models, migration, REST API, services, tests) | Complete, 37 tests | `eee3e2a` `feat: implement candidate profile foundation` |
| WS-2 | Phase 1 — HTTP-layer ownership dependency (`get_owned_candidate`) + parse/apply-parsed workflow | Complete | **NOT committed** (pending approval, see WS-3) |
| WS-3 | Phase 1 — hardening: service-layer ownership, safe re-apply, explicit confirmation | Complete, 49 tests | Feature **NOT committed**; `PROGRESS.md` committed separately as `docs: update project progress` |

> WS-2 and WS-3 live together in the current uncommitted working tree. WS-3 is the
> current workstream described below.

---

## Current Workstream: WS-3 — Phase 1 Hardening

**Project / Phase:** AI Career Agent (ai-career-agent) — Phase 1 (Candidate Profile).
**Workstream:** Three approved hardening items superseding WS-2's HTTP-layer work.

### What Was Implemented

1. **Service-layer ownership enforcement** (defense-in-depth beneath HTTP dependency).
   - `SkillService`, `ExperienceService`, `EducationService`, `CertificationService` now take a
     `CandidateRepository` and call `get_for_user_or_404(candidate_id, user_id)` in every
     candidate-scoped method (`list`, `get`, `add`, `update`, `delete`); the checked `get` is reused
     by `update`/`delete` so the rule runs once.
   - `ResumeService` asserts ownership in `list_resumes`, `get_resume`, `create_resume`,
     `upload_resume`; other methods inherit it via `get_resume`/`get_parsed_resume`.
   - 404 convention preserved (all paths raise `NotFoundError`; HTTP `get_owned_candidate` still runs first).
   - `list`/`get`/`get_resume`/`get_parsed_resume` signatures gained a required `user_id`.
2. **Safe re-apply (no stale-overwrite of manual edits).**
   - New `ParsedResume.applied_fields: list[str]` (JSON column) records which candidate profile fields
     a parsed resume has already applied (`full_name`, `email`, `phone`, `summary`).
   - On apply, only fields NOT in `applied_fields` are written; manual edits survive a second apply.
   - Re-apply is idempotent: no candidate write when nothing is pending, skills still deduplicated.
   - Re-parse resets `applied_fields=[]` and `status="pending"`.
3. **Explicit confirmation for mutation.**
   - `ApplyParsedResumeRequest.confirm` default changed `True` → `bool | None = None`.
   - Route requires `confirm is True`; `confirm=false` → 400, omitted → 400, and the service is never
     called in either case (zero mutation).
   - Confirmation is passed as query param `?confirm=true` (existing convention).

### Files Changed (WS-3, uncommitted)

**Modified:**
- `src/backend/models/resume.py`
- `src/backend/schemas/resume.py`
- `src/backend/services/skill.py`, `experience.py`, `education.py`, `certification.py`, `resume.py`
- `src/backend/api/deps.py`
- `src/backend/api/v1/skills.py`, `experience.py`, `education.py`, `certifications.py`, `resumes.py`
- `tests/integration/api/test_apply_parsed.py` (also WS-2)
- `tests/integration/api/test_candidate_flow.py`
- `ROADMAP.md` (Phase 1 hardening note)

**Untracked (new):**
- `migrations/versions/c4f8a19b2d71_add_applied_fields_to_parsed_resumes.py`
- `tests/integration/test_service_ownership.py`
- `tests/unit/test_resume_apply_skills.py`

> **WS-2 committed list kept for context (uncommitted, in same working tree):** `api/deps.py`,
> `api/v1/{certifications,education,experience,resumes,skills}.py`, `services/resume.py`, `ROADMAP.md`,
> `tests/integration/api/test_ownership.py`, `tests/integration/api/test_apply_parsed.py`.

### Migration Details

- Genuinely required: one new nullable JSON column `applied_fields` on `parsed_resumes`.
- Hand-written `add_column`/`drop_column` Alembic migration (`87990926037c` → `c4f8a19b2d71`),
  matching the SQLModel `Column(JSON, default=list)` declaration.
- Validated end-to-end with `alembic upgrade head` against a scratch SQLite database.
- Tests use `SQLModel.metadata.create_all` (in-memory SQLite) and need no migration run.

### Tests Executed & Exact Results

| Gate | Command | Result |
|------|---------|--------|
| Tests | `.venv\Scripts\python.exe -m pytest` | **49 passed** (was 37 pre-WS-3) |
| Whitespace | `git diff --check` | Clean |
| Lint | `ruff check src tests ROADMAP.md` | All checks passed |
| Types | `.venv\Scripts\python.exe -m mypy src` | Success: no issues in 51 files |
| Migration | `alembic upgrade head` (scratch SQLite) | `87990926037c -> c4f8a19b2d71`, ran cleanly |

New/updated tests:
- `test_service_ownership.py` — direct service calls on another user's candidate raise
  `NotFoundError` for every operation across all five services; foreign rows untouched; owner positive-control; non-existent candidate path.
- `test_resume_apply_skills.py` — white-box skill dedup within one extraction and across repeated applies; empty extraction no-op.
- `test_apply_parsed.py` — confirm=false and omitted-confirm both 400 with zero mutation (profile + parsed status asserted unchanged); manual-edit-preserved-on-reapply; existing apply tests now send `confirm=true`.
- `test_candidate_flow.py` — apply-parsed call now sends `confirm=true`.

### Commit Status

- Feature implementation (WS-2 + WS-3): **NOT committed** — explicitly instructed to stop after
  implementation/review and await approval before committing.
- `PROGRESS.md`: committed separately as **`docs: update project progress`** (this handoff doc).

### Working-Tree Status

- **Staged:** none.
- **Modified (tracked, uncommitted): 15 files** — ROADMAP.md; api/deps.py; api/v1/{certifications,education,experience,resumes,skills}.py; models/resume.py; schemas/resume.py; services/{certification,education,experience,resume,skill}.py; tests/integration/api/test_candidate_flow.py.
- **Untracked: 5 files** — the migration and the 4 new test modules listed above.
- **Unstaged, uncommitted only** — no partial feature commits exist.

### Important Architecture / Design Decisions

- Ownership reused exactly one existing rule: `CandidateRepository.get_for_user_or_404`
  (404 for both cross-user and non-existent candidates) — no duplicated authorization logic.
- HTTP dependency (`get_owned_candidate`) kept as the outer guard; service checks are the innermost
  guard so even non-HTTP callers (tests, future workers) cannot cross candidates. This is intentionally redundant (defense-in-depth).
- Safe re-apply built from the existing model (JSON-typed list field on `ParsedResume`) — skills remain
  merge-only, case-insensitive, de-duplicated (`strip().lower()`).
- Confirmation implemented without new dependencies: schema default removed; strict `is not True` check
  in the route; failure returns 400 before any service call (no mutation).

### Deviations from Approved Plan

- None functional. Minor: the exact `confirm` transport is a query parameter (`?confirm=true`), matching
  the pre-existing test convention rather than a JSON body — API surface unchanged otherwise.

### Known Risks / Issues

1. Redundant ownership check across HTTP dep + services is intentional; future consolidation optional.
2. Pre-existing rows after migration have `applied_fields = NULL`; code normalizes with `or []`, so the
   first post-migration apply behaves like a fresh apply.
3. Feature checkpoint uncommitted — any subsequent doc-only commit (incl. this one) leaves the feature in
   the working tree; a `git reset` would lose WS-2/WS-3 work. Feature commit is the immediate next step once approved.

### Explicitly Out-of-Scope (WS-3)

- Phase 2–13 implementation. Frontend (Next.js). New dependencies. Database schema/migration beyond the
  single `applied_fields` column. Application code changes for the sake of this handoff doc.

---

## Next Workstream

1. **Commit WS-2 + WS-3 feature checkpoint** (single feature commit covering the current working tree)
   — **pending user review/approval**, not yet approved, not started.
2. **Phase 2 — Job Discovery** — not started, not approved.

## Next Workstream Status

- Approved: **NO — requires review/approval.**
- Started: **NO.**