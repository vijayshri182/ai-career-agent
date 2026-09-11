# Project Progress — Handoff Document

> Authoritative handoff for future ChatGPT/OpenCode sessions. Preserve history;
> do not delete completed workstreams. Never invent or guess status.

## Repo / Git Reference (captured at last check)

| Field | Value |
|-------|-------|
| Repository | `vijayshri182/ai-career-agent` (`git@github.com:vijayshri182/ai-career-agent.git`) |
| Current branch | `main` |
| HEAD SHA | `73b5506` (`feat: add authentication and challenge management foundation`) |
| HEAD == origin/main | **Yes** (identical after `git fetch origin main`) |
| HEAD == origin/master | N/A — remote default branch is `main`; no `origin/master` ref exists |
| Upstream | `main` tracks `origin/main`, even (no ahead/behind) |

---

## Workstream History (preserved, oldest → newest)

| # | Workstream | Result | Committed? |
|---|-----------|--------|-----------|
| WS-0 | Phase 0 — project foundation, architecture, ADRs, docs | Complete | `fd4de13` `chore: initialize AI career agent architecture and project plan` |
| WS-1 | Phase 1 — candidate profile backend (models, migration, REST API, services, tests) | Complete, 37 tests | `eee3e2a` `feat: implement candidate profile foundation` |
| WS-2 | Phase 1 — HTTP-layer ownership dependency (`get_owned_candidate`) + parse/apply-parsed workflow | Complete | `8a67306` `docs: update project progress` (doc), `fe8aa29` incl. in Phase 1 completion |
| WS-3 | Phase 1 — hardening: service-layer ownership, safe re-apply, explicit confirmation | Complete, 49 tests | `fe8aa29` `feat: complete phase 1 candidate profile foundation` |
| WS-4 | Phase 1 — authentication & challenge management foundation (provider-neutral auth state, challenges, workflows, secret references) | Complete | `73b5506` `feat: add authentication and challenge management foundation` |
| WS-5 | Phase 1 — Next.js frontend (all profile/resume/connections UI, HttpOnly-cookie auth, `/api/v1` proxy) + backend integration fixes | Complete; smoke-tested | **NOT committed** (current working tree; pending commit/push) |

---

## Current Workstream: WS-5 — Phase 1 Frontend (Next.js) + Integration Fixes

**Project / Phase:** AI Career Agent (ai-career-agent) — Phase 1 (Candidate Profile, frontend).
**Workstream:** Complete interactive frontend for all Phase 1 features, plus runtime integration fixes
found by smoke-testing the running stack.

### What Was Implemented

1. **Frontend scaffold** in `src/frontend/` — Next.js 16 (App Router, Turbopack), React 19,
   TypeScript, Tailwind CSS v4. `npm run lint`, `npx tsc --noEmit`, `npm run build` all clean.
2. **Auth with HttpOnly cookies** — `/api/auth/{register,login}` route handlers exchange credentials
   for the backend token and set it as an HttpOnly `access_token` cookie (7 days, SameSite=lax,
   `Secure` in production). `GET|POST /api/auth/me` reads/logs out the session. Token never reaches the
   browser. `logout()` fixed to `POST /api/auth/me`.
3. **`proxy.ts`** — Next.js 16 replaced the deprecated `middleware` convention with `proxy`. It forwards
   `/api/v1/*` to the backend, injects `Authorization: Bearer <token>` from the cookie, guards protected
   pages (redirect to `/login`), and redirects authenticated users away from `/login`/`/register`.
   Security fix vs earlier middleware: response headers no longer echo back request headers
   (prevented `Authorization` leakage to the browser).
4. **Pages** — landing, login, register, dashboard (profile-completeness + quick links), profile +
   sub-pages (skills, experience, education, certifications, preferences), resumes, connections. Layout
   kept bare; pages use the `AppShell` wrapper.
5. **Components / hooks** — `ui.tsx`, `nav.tsx`, `app-shell.tsx`, `auth-form.tsx`, `profile-editor.tsx`,
   `skills/experience/education/certifications-editor.tsx`, `preferences-form.tsx`, `resumes-panel.tsx`,
   `connections-panel.tsx`; typed `lib/{api,config,auth-server,types,constants,hooks}.ts`.
6. **Backend integration fixes** (from live runtime smoke test):
   - `ResumeRepository.list_active` now `selectinload(Resume.versions)` — previously `GET
     /candidates/{id}/resumes` raised `MissingGreenlet` on async lazy-load of `active_version`
     (resume listing 500). Fixed + regression test added.
   - `tests/unit/test_project_standards.py` scans for `{{ }}` placeholder tokens; added `.next/` to the
     exclude set so frontend build artifacts are not flagged.

### Files Changed (WS-5, uncommitted)

**Untracked (new) `src/frontend/`:** full Next.js app (all pages/components/lib/`proxy.ts`), plus
`package.json`, `package-lock.json`, `tsconfig.json`, `next.config.ts`, `postcss.config.mjs`,
`eslint.config.mjs`, `public/`, `.gitignore`, `README.md`, `AGENTS.md`, `CLAUDE.md`.

**Modified:** `src/backend/repositories/resume.py` (eager-load `versions`),
`tests/integration/api/test_candidate_flow.py` (new regression test),
`tests/unit/test_project_standards.py` (exclude `.next`), `README.md`, `PROGRESS.md`.

**Deleted:** `src/frontend/.gitkeep` (replaced by the real scaffold).

### Tests Executed & Exact Results

| Gate | Command | Result |
|------|---------|--------|
| Backend tests | `.venv\Scripts\python.exe -m pytest` | **100 passed** (was 49; +auth/challenge tests in WS-4, +1 regression here) |
| Backend lint | `.venv\Scripts\python.exe -m ruff check .` | All checks passed |
| Backend types | `.venv\Scripts\python.exe -m mypy src` | Success: no issues in 76 files |
| Frontend types | `npx tsc --noEmit` (in `src/frontend`) | Clean |
| Frontend lint | `npm run lint` | Clean |
| Frontend build | `npm run build` | Succeeded, 18 routes + `ƒ Proxy (Middleware)`; no middleware deprecation warning |

### Runtime Smoke Test (live, backend uvicorn + `next start`)

Verified end-to-end through the Next.js proxy against the real backend (SQLite scratch DB):
register → cookie issued (HttpOnly) → `/api/auth/me` with cookie → create candidate (POST JSON body
preserved through proxy) → `/candidates/me` → add skill → profile completeness → resumes upload
(multipart body preserved) → list resumes → logout → `/api/auth/me` returns 401 → unauthenticated
`/dashboard` redirects to `/login`. **All checks passed.**

> Note: `next start` runs with `NODE_ENV=production` so cookies carry the `Secure` attribute; browsers
> send Secure cookies to `http://localhost` (and it is required over real HTTPS), while plain-HTTP API
> test clients (httpx/curl) refuse them — the smoke script forwards the cookie header manually. In
> `npm run dev` cookies are not `Secure` and plain-HTTP local testing works directly.

### Commit Status / Next Step

- WS-5 feature + docs: **NOT committed** — commit (e.g. `feat: add phase 1 frontend`), push `origin/main`,
  verify `HEAD == origin/main` and clean tree.

### Known Risks / Issues

1. The proxy/rewrite path is validated for JSON and multipart bodies against the live backend; other
   media types are assumed safe (rewrite preserves the raw request).
2. `API_BASE_URL` must be set when building/deploying the frontend to point at the backend origin
   (route handlers and `proxy.ts` both read it); default is `http://localhost:8000`.
3. Phase 2–13 and any runtime deployment (HTTPS, Docker, Postgres) remain out of scope.

---

## Next Workstream

1. **Commit + push WS-5** (current working tree) and verify clean tree / `HEAD == origin/main`.
2. **Phase 2 — Job Discovery** — not started, not approved.

## Next Workstream Status

- Approved: **YES for commit/push of WS-5** (Phase 1 completion checkpoint per plan).
- Started: **NO** (Phase 2 not started until WS-5 is committed and verified).
