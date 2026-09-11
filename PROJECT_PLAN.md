# AI Career Agent — Project Plan

## 1. Problem Statement

Finding the next career opportunity is time-consuming, repetitive, and easy to miss. Job seekers must continuously monitor multiple sources, evaluate fit, tailor materials, and track applications. Existing automation often crosses ethical and legal boundaries by spamming recruiters, bypassing website protections, or faking candidate information.

## 2. Objective

Build a responsible, 24×7 AI career agent that:

* Discovers relevant, legitimate opportunities.
* Verifies company and job authenticity.
* Matches jobs against a structured, user-owned profile.
* Prepares personalized, factually accurate applications.
* Requires explicit approval before external actions.
* Tracks progress and learns from outcomes.

## 3. Target User

**Vijay Shrivastava** — a senior technology leader with deep telecom/OSS-BSS software experience, technical management background, and expertise in Java/Spring Boot microservices, cloud platforms, DevOps, and AI-enabled engineering. The system must be configurable for any candidate profile.

No personal facts are hard-coded. The profile is loaded through configuration/database at runtime and is editable by the user.

## 4. Core Functional Areas

1. **Candidate Profile Service** — structured professional profile, resume versions, preferences.
2. **Job Discovery Engine** — multi-source discovery with deduplication.
3. **Job Verification Engine** — company/domain/job verification and risk scoring.
4. **AI Job Matching Engine** — explainable 0–100 match score.
5. **Resume Personalization Engine** — select and tailor resume without inventing facts.
6. **Application Preparation Engine** — generate answers, cover letters, and application data.
7. **Application Automation Layer** — browser automation where permitted, with human checkpoints.
8. **Recruiter/Contact Discovery** — identify publicly available recruiting contacts.
9. **Outreach Engine** — draft personalized messages, require approval before sending.
10. **Application Tracking** — full lifecycle state machine.
11. **Feedback/Learning Engine** — analyze outcomes and recommend improvements.
12. **Notification System** — timely alerts for high-match jobs and required actions.
13. **Dashboard** — visibility into activity, pipeline, and audit trail.
14. **Authentication & Challenge Management (foundation)** — records where the agent may need to authenticate and when a site requires human verification; human-in-the-loop challenge resolution. No automation and no secret storage. See [`docs/architecture/authentication-and-challenges.md`](docs/architecture/authentication-and-challenges.md).

## 5. Product Model

### Autonomy Levels

| Level | Name | Description |
|-------|------|-------------|
| 1 | Recommend only | The agent highlights jobs and stops. |
| 2 | Prepare + approve *(default)* | The agent prepares applications and recruiter outreach, then waits for human approval. |
| 3 | Execute permitted actions | The agent automatically applies on sites that explicitly allow automation and sends pre-approved outreach, still logging every action. |

The default level is **2**. The user can change the level per source, per company, or globally.

### Human-in-the-Loop Actions

* Submitting an application.
* Sending any external message (email, networking request).
* Changing factual candidate information.
* Changing target roles/salary preferences.
* High-cost actions (e.g., applying beyond a daily limit).

## 6. MVP Definition

The first usable MVP (Phase 1–6) must prove:

```text
Job discovery → Verification → Matching → Match score → Resume recommendation → Application preparation → Human approval → Tracking
```

Concrete MVP capabilities:

* Create and edit candidate profile.
* Discover jobs from at least one permitted source.
* Verify company domain and job freshness.
* Calculate and explain a match score.
* Recommend the best resume version.
* Generate a draft cover letter and application answers.
* Present a human approval screen.
* Track lifecycle states.
* Send notifications.

**Out of scope for MVP:** automatic submission, recruiter scraping, email sending, cloud production deployment.

## 7. Success Metrics

* **Match quality:** High-match jobs (score ≥ 80) have positive recruiter response correlation.
* **Efficiency:** Reduction in manual time spent on discovery and preparation.
* **Safety:** Zero unauthorized submissions, zero spam, zero credential exposure.
* **Transparency:** Every match score and recommendation is explainable.
* **Uptime:** Scheduler and queue operate 24×7 in the cloud.

## 8. Constraints & Non-Goals

### Constraints

* Must respect website Terms of Service and robots.txt.
* Must not bypass CAPTCHA, MFA, rate limits, or anti-bot measures.
* Must not fabricate experience, skills, or qualifications.
* Must not guess or use unverified private contact information.
* Must not store plaintext passwords or secrets.

### Non-Goals

* Becoming a mass-spam tool.
* Guaranteed job placement.
* Circumventing hiring-platform policies.
* Handling illegal or discriminatory job postings.

## 9. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Website policy changes blocking automation | Medium | High | Pioneer manual workflows; use official APIs first; graceful degradation. |
| LLM hallucinations in generated materials | Medium | High | Structured output, fact-checking prompts, human approval, version history. |
| PII/resume data breach | Low | Very high | Encryption, least-privilege access, secrets manager, audit logs, secure deletion. |
| Job-source rate limiting | High | Medium | Exponential backoff, queue priorities, source rotation, respectful crawl rates. |
| False positives in verification | Medium | High | Confidence thresholds, manual review queue, multiple signals. |

## 10. Stakeholders & Approvals

* **Product owner / candidate:** Vijay Shrivastava
* **Engineering:** Vijay Shrivastava (initially)
* **Compliance / legal review:** Required before enabling Level 3 automation or public recruiter outreach.

## 11. Documentation Map

* [`ARCHITECTURE.md`](ARCHITECTURE.md) — system components and data flows.
* [`AGENT_ARCHITECTURE.md`](AGENT_ARCHITECTURE.md) — agent design and orchestration.
* [`DATA_MODEL.md`](DATA_MODEL.md) — database design.
* [`SECURITY.md`](SECURITY.md) — security architecture.
* [`ROADMAP.md`](ROADMAP.md) — phased delivery plan.
* [`DEVELOPMENT_GUIDELINES.md`](DEVELOPMENT_GUIDELINES.md) — engineering standards.
* [`CONTRIBUTING.md`](CONTRIBUTING.md) — contribution process.
* `docs/adr/` — architecture decision records.
* `docs/architecture/authentication-and-challenges.md` — Authentication & Challenge Management foundation design.
