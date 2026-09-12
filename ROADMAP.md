# AI Career Agent — Development Roadmap

This roadmap breaks the project into self-contained phases. Each phase defines objective, features, components, APIs, data changes, tests, security, acceptance criteria, dependencies, and estimated complexity.

## Legend

* **Complexity:** XS (trivial) → S → M → L → XL (large, multi-feature).
* **Security gate:** A required security review before the next phase.

---

## Phase 0 — Project Foundation

* **Objective:** Establish repository, documentation, architecture, and engineering baseline.
* **Features:**
  * Repository structure and `.gitignore`.
  * README, project plan, architecture, data model, security model, roadmap.
  * ADRs for major technology choices.
  * Development guidelines and contribution process.
  * Empty source directories and configuration templates.
* **Components:** Documentation only.
* **APIs:** None.
* **Database changes:** None.
* **Tests:** N/A.
* **Security:** No secrets committed; documentation captures threat model and constraints.
* **Acceptance criteria:**
  * Repository is public/ready.
  * All Phase 0 documentation reviewed and internally consistent.
  * No raw placeholder tokens (such as `<PLACEHOLDER>` or mustache-style placeholders) or credentials in committed files.
* **Dependencies:** Repository must exist.
* **Complexity:** M
* **Status:** This phase is the current deliverable.

---

## Phase 1 — Candidate Profile

* **Objective:** Allow the user to create, edit, and store a structured professional profile and resume versions.
* **Features:**
  * Profile CRUD (experience, skills, education, certifications, preferences).
  * Target roles and locations.
  * Salary expectations and notice period.
  * Multiple resume versions with metadata.
  * Resume parsing/upload foundation.
  * Profile completeness score.
* **Components:** `Candidate Profile Service`, `Resume Service`, frontend profile UI.
* **APIs:**
  * `POST /api/v1/profiles`
  * `GET /api/v1/profiles/{id}`
  * `PUT /api/v1/profiles/{id}`
  * `POST /api/v1/profiles/{id}/resumes`
  * `GET /api/v1/profiles/{id}/resumes`
  * > Implemented under `/api/v1/candidates[/{candidate_id}]` (profile CRUD) and `/api/v1/candidates/{candidate_id}/...` (skills, experience, education, certifications, resumes, preferences, profile). This roadmap page predates the `candidate`-based resource naming used by the code.
  * > Phase 1 hardening: service-layer ownership checks reuse `CandidateRepository.get_for_user_or_404` (404 for cross-user/non-existent candidates) as defense-in-depth beneath the HTTP dependency; `apply-parsed` requires explicit `confirm=true` (400 + no mutation otherwise) and tracks `ParsedResume.applied_fields` so re-applying never overwrites manual profile edits; skill merging stays case-insensitive and idempotent.
* **Database changes:** Add `candidates`, `candidate_skills`, `experiences`, `educations`, `certifications`, `resumes`, `resume_versions`.
* **Tests:**
  * Unit tests for profile model validation.
  * API contract tests.
  * Upload parsing smoke tests.
* **Security:**
  * PII encrypted at rest.
  * Access control: only owner can read/write.
  * Audit log on profile changes.
* **Acceptance criteria:**
  * User can create a profile with all required sections.
  * User can upload a resume and see parsed sections.
  * Profile completeness score reaches 100% when all sections are filled.
* **Dependencies:** Phase 0.
* **Complexity:** M
* **Status:** Backend and frontend implemented. The backend lives in `src/backend/`; the interactive UI lives in `src/frontend/` (Next.js). Frontend auth uses an HttpOnly `access_token` cookie via `/api/auth/*` route handlers; `proxy.ts` forwards `/api/v1/*` to the backend and injects the bearer token from the cookie.

---

## Phase 1.5 — Authentication & Challenge Management (foundation)

* **Objective:** Record, at a provider/site-neutral level, where the agent may need to authenticate and when a site requires human verification, without performing any automation.
* **Features:**
  * Auth provider CRUD (ATS, career site, job board, networking, email, other).
  * Auth state machine (`NOT_CONFIGURED → AUTHENTICATED → ...`) with escalation states.
  * Challenge detection/classification and durable challenge records (CAPTCHA, MFA/OTP, login, bot protection, rate limits).
  * Human-in-the-loop workflow runs: a challenge pauses the linked workflow; it resumes exactly once after human resolution.
  * Secrets/sessions/browser state stored only as opaque references (no secret values anywhere).
* **Components:** `services/authentication_state.py`, `services/challenge_detection.py`, `services/human_in_loop.py`, `services/authentication.py` (facade), provider-neutral `services/auth_adapter.py` protocol, API router, Alembic migration.
* **APIs:** `/api/v1/candidates/{candidate_id}/auth/*` — overview, providers + state, challenges (acknowledge/complete/cancel), workflow resume, browser sessions, secret references.
* **Database changes:** Add `auth_providers`, `auth_provider_states`, `challenges`, `workflow_runs`, `browser_sessions`, `secret_references`.
* **Tests:**
  * Unit: AuthStateMachine + WorkflowStateMachine transitions; challenge classification rules.
  * Integration: provider CRUD, initial state, idempotent challenge reporting, challenge ack→complete→workflow resume, cross-user 404s.
* **Security:**
  * No CAPTCHA/MFA/anti-bot bypass and no automatic resolution — human-in-the-loop only.
  * No secret values in DB, logs, tests, or API; `LocalSecretsProvider` always reports unavailable.
* **Acceptance criteria:**
  * Reporting a challenge opens at most one in-flight challenge per provider/type (partial unique index).
  * Completing a challenge resumes the paused workflow exactly once within the attempt/expiry budget.
  * Full suite: 100 tests passing; `ruff check` and `mypy` clean.
* **Dependencies:** Phase 1.
* **Complexity:** M
* **Status:** Implemented. See [`docs/architecture/authentication-and-challenges.md`](docs/architecture/authentication-and-challenges.md). Application automation is a **future phase**; this foundation only records state and coordinates pauses/resumes around human acts.

---

## Phase 2 — Job Discovery

* **Objective:** Discover job postings from legitimate, permitted sources and normalize/deduplicate them.
* **Features:**
  * Pluggable job-source adapters (company career sites, ATS platforms, APIs, job boards).
  * Robots.txt and term-of-service compliance check per source.
  * HTML normalization and structured extraction.
  * Deduplication by company + requisition id / URL / content hash.
  * Job freshness detection.
  * Scheduler-triggered discovery runs.
* **Components:** `Job Discovery Agent`, source adapters, scheduler.
* **APIs:**
  * `POST /api/v1/discoveries/run`
  * `GET /api/v1/jobs`
  * `GET /api/v1/jobs/{id}`
  * `GET /api/v1/sources`
* **Database changes:** Add `jobs`, `companies`, `job_sources`, `raw_job_extractions`, `agent_tasks`.
* **Tests:**
  * Unit tests for deduplication and normalization.
  * Adapter contract tests using recorded HTTP responses.
  * Scheduler trigger tests.
* **Security:**
  * Source URLs validated against allow-list.
  * Crawl rate limits configured per source.
  * No credential exchange with untrusted sources.
* **Acceptance criteria:**
  * System discovers jobs from at least one source per run.
  * Duplicate jobs are merged into a single record.
  * Expired postings are marked `EXPIRED`.
* **Dependencies:** Phase 1.
* **Complexity:** L
* **Status:** Implemented. 134 tests passing; `ruff check` and `mypy` clean.

---

## Phase 3 — Job Verification

* **Objective:** Verify that discovered jobs are real, currently open, and posted by legitimate companies.
* **Features:**
  * Company domain verification.
  * Official career-page URL verification.
  * Cross-check job still exists at source.
  * Suspicious-posting detection (grammar, unrealistic promises, missing details).
  * Risk score 0–100.
  * Reject or quarantine high-risk jobs.
* **Components:** `Verification Agent`, risk-scoring model/rules.
* **APIs:**
  * `POST /api/v1/jobs/{id}/verify`
  * `GET /api/v1/jobs/{id}/verification`
* **Database changes:** Add `job_verifications`, `company_verifications`.
* **Tests:**
  * Rule-based risk scoring tests.
  * Browser verification tests with mocked pages.
  * Edge cases: expired jobs, redirecting domains, missing postings.
* **Security:**
  * External pages parsed in isolated browser contexts.
  * Input sanitization before storage.
  * No execution of external scripts in backend.
* **Acceptance criteria:**
  * Fresh, legitimate jobs are marked `VERIFIED`.
  * Suspicious postings receive a risk score ≥ 70 and are not shown.
  * Verified jobs link back to an official domain.
* **Dependencies:** Phase 2.
* **Complexity:** M

---

## Phase 4 — AI Job Matching

* **Objective:** Compute an explainable match score between verified jobs and the candidate profile.
* **Features:**
  * Skill, experience, seniority, domain, stack, leadership, location, work-mode matching.
  * 0–100 match score with human-readable reasons.
  * Configurable weighting per candidate preference.
  * Bias guard: score explanations must map to factual profile data.
* **Components:** `Matching Agent`, scoring rules, LLM-based structured analysis.
* **APIs:**
  * `POST /api/v1/jobs/{id}/match`
  * `GET /api/v1/matches`
  * `GET /api/v1/matches/{id}`
* **Database changes:** Add `job_matches`.
* **Tests:**
  * Evaluation dataset of jobs with expected score ranges.
  * Prompt regression tests.
  * Fact hallucination tests.
* **Security:**
  * Prompt injection protection (delimiter escaping, allow-list instructions).
  * No external job description can override system behavior.
* **Acceptance criteria:**
  * Match scores correlate with recruiter response evaluation dataset.
  * Every score is accompanied by at least three specific reasons.
  * Scoring latency < 5s per job.
* **Dependencies:** Phase 3.
* **Complexity:** L
* **Status:** Implemented (backend foundation). Deterministic, explainable scoring engine with ten
  transparent components (skills, role alignment, seniority, years experience, domain, industry,
  leadership, location, work mode, compensation); configurable weights (`MATCH_WEIGHTS`), threshold
  (`MATCH_THRESHOLD`), and rules version (`MATCH_RULES_VERSION`); job-text parsing treats descriptions
  as **untrusted input** (never overrides rules — prompt-injection invariant test); semantic skill
  matching is a pluggable protocol with a deterministic default; per-candidate+job results are
  persisted idempotently (`job_matches`), exposed under
  `/api/v1/candidates/{candidate_id}/jobs/{job_id}/match`,
  `/api/v1/candidates/{candidate_id}/matching/evaluate`, and
  `/api/v1/candidates/{candidate_id}/matches`. Runnable headless later via
  `score_for_orchestrator`.

---

## Phase 5 — Resume & Application Preparation

* **Objective:** Recommend and tailor resume and prepare application materials without inventing facts.
* **Features:**
  * Select best resume version for a job.
  * Generate a fact-grounded tailored resume PDF.
  * Draft cover letter mapped to job description and profile.
  * Generate answers to common screening questions.
  * Flag questions that require manual input.
  * Maintain document version history.
* **Components:** `Resume Agent`, `Application Agent`, document generator.
* **APIs:**
  * `POST /api/v1/jobs/{id}/prepare`
  * `GET /api/v1/applications/{id}/documents`
  * `POST /api/v1/applications/{id}/documents/generate`
* **Database changes:** Add `applications`, `application_questions`, `application_answers`, `documents`.
* **Tests:**
  * Resume selection unit tests.
  * LLM output fact-checking tests.
  * Prompt tests for cover-letter generation.
* **Security:**
  * Document storage encrypted.
  * Generated output checked for hallucinations via structured validation.
* **Acceptance criteria:**
  * Generated resume contains only facts from profile.
  * Cover letter references specific job and candidate capabilities.
  * User can review and edit generated materials before submission.
* **Dependencies:** Phase 4.
* **Complexity:** L
* **Status:** Backend foundation implemented. Deterministic, fact-grounded preparation: one
  `Application` per (candidate, job) with best-resume selection (active-version + default + resume-type
  alignment scoring), screening questions classified auto vs `requires_review`, and versioned generated
  documents (cover letter, tailored resume, answers sheet) stored with encrypted content +
  `fact_sources` JSON traceability. A structured `FactGroundingValidator` rejects generated content that
  introduces invented companies, names, or qualifications, and the deterministic writer only echoes
  matched skills present in the profile (raw match strengths that repeat untrusted job text are never
  copied verbatim). Exposed under
  `/api/v1/candidates/{candidate_id}/applications/jobs/{job_id}/prepare`,
  `.../applications`, `.../applications/{application_id}`,
  `.../applications/{id}/documents[/generate|/{document_id}]`,
  `.../applications/{id}/questions/{question_id}/answer`, and `.../applications/{id}/status`.
  `prepare` requires an existing match (400 otherwise); re-preparing an active application is
  idempotent. PDF/export of the tailored resume and any LLM-backed drafting remain future increments.

---

## Phase 6 — Human Approval Workflow

* **Objective:** Implement explicit human-in-the-loop checkpoints before external actions.
* **Features:**
  * Approval request generation for application and outreach.
  * Dashboard approval UI with job summary, match score, draft materials.
  * Approve / Reject / Edit / Snooze actions.
  * Audit trail for every decision.
  * Configurable autonomy levels.
* **Components:** `Approval Service`, dashboard, notification engine.
* **APIs:**
  * `GET /api/v1/approvals`
  * `GET /api/v1/approvals/{id}`
  * `POST /api/v1/approvals/{id}/approve`
  * `POST /api/v1/approvals/{id}/reject`
* **Database changes:** Add `approvals`, `approval_decisions`, `audit_events`.
* **Tests:**
  * State-machine tests.
  * API authorization tests.
  * Notification tests.
* **Security:**
  * Approval endpoint protected by auth.
  * Tamper-proof audit log (append-only).
* **Acceptance criteria:**
  * Prepared application cannot proceed without approval.
  * Recruiter outreach cannot be sent without approval.
  * Audit log contains who decided what and when.
* **Dependencies:** Phase 5.
* **Complexity:** M

---

## Phase 7 — Permitted Application Automation

* **Objective:** Automate application submission on sites where automation is explicitly permitted.
* **Features:**
  * Pluggable ATS adapters using Playwright.
  * Site-policy check before automation.
  * Human checkpoint if automation is ambiguous.
  * Secure credential/session manager (reuses the Phase 1.5 reference-only secret model and `AuthProviderState.session_reference`).
  * CAPTCHA/MFA detection with immediate stop + notification (reuses the Phase 1.5 challenge records and paused-workflow resume).
* **Components:** `Application Automation Layer`, browser worker pool, credential vault.
* **APIs:**
  * `POST /api/v1/applications/{id}/execute`
  * `GET /api/v1/automation/status`
* **Database changes:** Add `automation_runs`, `browser_sessions`.
* **Tests:**
  * Mock ATS application tests.
  * CAPTCHA detection tests.
  * Failure and retry tests.
* **Security:**
  * Credentials stored in secrets manager, never code/repo.
  * Session isolation per run.
  * Browser runs in sandboxed container.
* **Acceptance criteria:**
  * System succeeds on a test ATS with explicit automation permission.
  * System stops and alerts user when CAPTCHA/MFA appears.
  * Failed runs are retried with exponential backoff.
* **Dependencies:** Phase 6.
* **Complexity:** XL

---

## Phase 8 — Recruiter / Professional Contact Discovery

* **Objective:** Discover legitimate, publicly available recruiting contacts associated with target companies.
* **Features:**
  * Public profile search (company career pages, team pages, verified directories).
  * Confidence scoring for contact affiliation.
  * Distinguish verified vs guessed contacts.
  * Never use guessed emails.
  * Privacy-safe discovery policies.
* **Components:** `Recruiter Discovery Agent`.
* **APIs:**
  * `POST /api/v1/jobs/{id}/discover-contacts`
  * `GET /api/v1/recruiter-contacts`
* **Database changes:** Add `recruiter_contacts`, `contact_sources`.
* **Tests:**
  * Confidence scoring tests.
  * Privacy boundary tests.
* **Security:**
  * No scraping of private contact databases.
  * Data retention limits for discovered contacts.
* **Acceptance criteria:**
  * Only contacts with confidence ≥ 70 are surfaced.
  * Each contact links to public source evidence.
* **Dependencies:** Phase 4 (can run in parallel with Phase 5 after matching).
* **Complexity:** M

---

## Phase 9 — Outreach Engine

* **Objective:** Prepare personalized recruiter and networking messages; require approval before sending.
* **Status:** DONE (WS-12) — deterministic fact-grounded writer; candidate-scoped messages/runs/versions;
  human-approval gate; verified-destination check; per-candidate daily cap; retry/backoff; response/suppression
  handling; openflow audit trail. Real senders are pluggable (`OutreachSender` — network-free `make_sender()` today).
* **Features:**
  * Draft recruiter emails from verified contacts.
  * Draft networking connection requests.
  * Tone and context personalization.
  * Rate limiting and daily send caps.
  * Approval workflow integration.
* **Components:** `Outreach Agent`, email client abstraction.
* **APIs:**
  * `POST /api/v1/candidates/{candidate_id}/outreach/drafts`
  * `POST /api/v1/candidates/{candidate_id}/outreach/follow-ups`
  * `POST /api/v1/candidates/{candidate_id}/outreach/messages/{id}/submit`
  * `POST /api/v1/candidates/{candidate_id}/outreach/messages/{id}/send`
* **Database changes:** Add `outreach_messages`, `outreach_message_versions`, `outreach_runs`.
* **Tests:**
  * Message personalization tests.
  * Rate-limit tests.
* **Security:**
  * No bulk spam; per-message approval by default.
  * Email credentials stored in secrets manager.
* **Acceptance criteria:**
  * Drafts are generated only for verified contacts.
  * Sending requires approval.
  * Daily send limit is enforced.
* **Dependencies:** Phase 6 and Phase 8.
* **Complexity:** M

---

## Phase 10 — Dashboard + Notifications

* **Objective:** Provide observability and timely alerts.
* **Features:**
  * Web dashboard: pipeline, match scores, activity log, audit trail.
  * Notification channels: in-app, email, optional SMS.
  * Alerts for new high-match jobs, approvals needed, errors/security events.
* **Components:** Dashboard UI, notification service.
* **APIs:**
  * `GET /api/v1/dashboard/summary`
  * `GET /api/v1/notifications`
  * `POST /api/v1/notifications/preferences`
* **Database changes:** Add `notifications`, notification preferences.
* **Tests:**
  * Dashboard aggregation tests.
  * Notification delivery tests.
* **Security:**
  * Users see only their own data.
  * Security alerts bypass muting.
* **Acceptance criteria:**
  * Dashboard loads in < 3s.
  * Approval notifications are sent within 60s.
* **Dependencies:** Phase 6.
* **Complexity:** M

---

## Phase 11 — 24×7 Cloud Deployment

* **Objective:** Run the scheduler and workers continuously in the cloud.
* **Features:**
  * Docker containerization.
  * Cloud scheduler with Celery beat.
  * Worker autoscaling (manual initially).
  * Health checks, monitoring, alerting.
  * Graceful recovery after restart.
* **Components:** Docker images, infrastructure manifests, CI/CD pipeline.
* **APIs:** Health/readiness endpoints.
* **Database changes:** Operational indexes on jobs, tasks, events.
* **Tests:**
  * Container build tests.
  * End-to-end smoke tests in staging.
* **Security:**
  * Secrets mounted from vault, never images.
  * Network segmentation).
  * TLS termination at ingress.
* **Acceptance criteria:**
  * Scheduler runs without the user's computer being on.
  * System recovers from simulated worker crash.
* **Dependencies:** Phase 6.
* **Complexity:** L

---

## Phase 12 — Learning / Optimization

* **Objective:** Improve matching and search criteria from outcomes.
* **Features:**
  * Analyze rejection patterns.
  * Recommend profile/resume improvements.
  * Optimize discovery sources.
  * A/B safe experimentation on prompts.
  * Feedback capture after interviews.
* **Components:** `Learning Agent`, analytics pipeline.
* **APIs:**
  * `POST /api/v1/feedback`
  * `GET /api/v1/recommendations`
* **Database changes:** Add `feedbacks`, `recommendations`, analytics views.
* **Tests:**
  * Learning recommendation tests.
  * Bias/fairness checks.
* **Security:**
  * Recommendations only suggest, never automatically edit facts.
* **Acceptance criteria:**
  * Recommendations are explainable and user-approved.
  * No factual candidate data changes without approval.
* **Dependencies:** Phase 9 and Phase 10.
* **Complexity:** L

---

## Phase 13 — Production Hardening

* **Objective:** Make the system production-ready and compliant.
* **Features:**
  * Full security audit.
  * Penetration testing of browser automation.
  * Data retention and deletion policies automated.
  * Backup and disaster recovery.
  * Runbook and incident response.
* **Components:** Security/compliance documentation, operational runbooks.
* **APIs:** Data-export and deletion endpoints.
* **Database changes:** Soft-delete rules, retention metadata.
* **Tests:**
  * Security regression suite.
  * Load tests.
* **Security:**
  * External security review.
  * BASS/compliance checklist.
* **Acceptance criteria:**
  * All high/critical vulnerabilities remediated.
  * User can export or delete all personal data.
  * Runbooks cover common incidents.
* **Dependencies:** Phases 11 and 12.
* **Complexity:** L

---

## What Phase 1 Will Implement

Phase 1 focuses on the **Candidate Profile**. This means:

* Database schema for candidates, skills, experience, education, certifications, resumes.
* REST API for full profile CRUD.
* Frontend screens to create and edit the profile.
* Resume upload and parsing foundation.
* Profile completeness calculation.
* Security: encrypted PII, owner-based access control, audit log seed.
* Tests: unit, API, and UI smoke tests.

No job discovery or automation is built in Phase 1.

> **Addendum:** the **Authentication & Challenge Management foundation**
> (above, Phase 1.5) has been completed in the backend. It introduces the
> provider/auth-state/challenge/human-in-the-loop entities without enabling any
> automation — site interaction remains fully manual.
