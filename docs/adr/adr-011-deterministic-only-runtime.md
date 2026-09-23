# ADR-011: Deterministic-Only Runtime

## Status

**Accepted** — 22-Sep-2026

> Supersedes [ADR-005 — LangChain / LangGraph for LLM Abstraction](adr-005-langchain-llm-abstraction.md)

## Context

Earlier ADRs (ADR-002, ADR-005, ADR-003) contemplated LLM-based matching, vector
search (pgvector), and external queue/broker infrastructure. Those capabilities were
evaluated but are **not** implemented, and the project does not run or call any
external model service at runtime.

This ADR records the decision that governs the runtime for the foreseeable future:
the application is a **deterministic-only runtime**. Every decision that affects
candidate data, ownership, eligibility, approvals, applications, outreach, scheduling,
or security policy is made by deterministic, auditable, tested code — never by an
external or stochastic component.

## Current Implementation (v1.0)

* All intelligence is deterministic, network-free, and rule/heuristic based
  (job normalization, weighted rule-based matching, curated skill synonym graph,
  template/human-input application-prep and outreach drafting).
* No LLM provider SDK (OpenAI, Anthropic, Google, LangChain, LangGraph, embeddings)
  is imported or called at runtime; **no AI SDKs exist in `pyproject.toml`
  dependencies** (enforced by tests).
* PostgreSQL is the primary store; `pgvector` is not installed in the database, no
  embedding columns exist, and the dependency has been removed from the project.
* Scheduling is an **in-process scheduler that is OFF by default**
  (`DISCOVERY_ENABLED` defaults to `false`); it is inert until explicitly activated.
* The only outbound action-capable component is a `RecordingSender` used by the
  explicit, human-approved send path; discovery, matching, signal generation,
  quality, and prep produce **zero** outbound messages.
* A tamper-resistant audit trail records security- and decision-relevant events;
  a candidate-scoped audit read API exists.

## Decision

The runtime is **deterministic-only**. AI/LLM use, if ever introduced, is **bounded
assistance** and must remain inside the boundaries below.

### Deterministic runtime authority

Deterministic code is the sole authority over:

* Candidate eligibility, ownership, and data access.
* Job/application decisions, suppression rules, and overrides.
* Approval workflows and state transitions.
* Security policy, authentication, and authorization.
* Scheduling activation and outbound sends.

### Bounded assistance

If a model is ever used, it operates only as assistance: input transformation,
summarization, or draft text for human review. It never makes decisions.

### AI output is untrusted

Model output is always treated as unvalidated data:

* Parsed through strict, fail-closed schemas with unexpected keys rejected.
* Bound to deterministic fact sets (profile, job, company data) for reference.
* Never executed as code, commands, or links followed automatically.
* Never used to alter policy, bypass checks, forge state, or trigger actions.

### Deterministic policy enforcement

Every policy (eligibility gates, matched-status, quality, ownership, deduplication,
at-most-once run guards, rate/budget caps) is enforced by deterministic code paths
with unit/integration coverage. Model output cannot weaken enforcement.

### Explicit human approval

Actions with account-level impact (applications, outreach sends) require explicit,
recorded human approval. The system never impersonates the user on a website, never
auto-resolves challenges, and never resumes paused workflows except via recorded
completion.

### No AI-controlled authorization or outbound

Neither the scheduler, the discovery/matching pipeline, nor approval flows may be
enabled, disabled, scoped, or triggered by model output. The only invocation of the
recording sender is through the explicit, approved send path.

### Candidate ownership enforcement

All candidate-scoped reads/writes enforce ownership; cross-user access is denied.
AI/bounded components are not exempted.

### Auditability

Every decision-relevant event is recorded in the audit trail with actor, action,
entity, outcome, and timestamp. Deterministic decisions can be traced to code +
inputs; any future model-assisted step must record the model, inputs, prompt, and
post-validation exactly as the deterministic path would.

### Scheduler safety

Scheduler runs are opt-in (OFF by default). Activation is a separate operational
approval; each run is bounded by idempotency, at-most-once guards, and retry/backoff.

### Prompt-injection boundary

All external content (job descriptions, company descriptions, recruiter content,
imported documents, source API data) is processed as untrusted data. It can never
execute commands, change authorization or ownership, approve actions, override
policy, activate the scheduler, or trigger outbound.

### Reproducibility

Deterministic, dependency-pinned, tested code means identical inputs produce
identical outputs and results are reproducible in any environment, including clean
installations, without external services.

## Alternatives Considered

* **LLM-augmented matching with human review:** Rejected for now — adds runtime
  network calls, cost, prompt-injection surface, and non-determinism without proven
  benefit for the MVP.
* **Vector search / RAG:** Rejected (again) — no embedding infrastructure; rule-based
  matching covers current needs and is testable/reproducible. `pgvector` dependency
  removed.
* **External queue / scheduler (Celery, Redis):** Rejected for v1.0 — an in-process
  scheduler that is OFF by default and a directly-called pipeline suffice; avoids
  operational infrastructure.
* **Agentic / autonomous execution frameworks (LangGraph, agent orchestrators):**
  Rejected — they conflict with deterministic policy enforcement and auditability.

## Advantages

* Reproducible, unit-testable behavior; no stochastic risk.
* No external model calls at runtime; no per-call cost or latency.
* Small attack surface (no prompt-injection or model-output execution paths).
* No reliance on third-party AI availability or pricing.
* Meets data-privacy posture: no PII is sent to any third party.

## Disadvantages

* Limitation on open-ended language generation (tailored prose, free-text
  reasoning) until a bounded-assistance capability is added under this ADR.
* Deterministic systems require manual maintenance of rules, synonyms, and templates.

## Migration / Scaling Considerations / Relationship to Other ADRs

* If bounded model assistance is ever introduced, it MUST be implemented outside the
  enforcement code paths, introduced behind a strict interface, subject to this ADR's
  boundaries, and released via a new ADR that updates or extends this one.
* Relationship to ADRs:
  * **[ADR-005](adr-005-langchain-llm-abstraction.md)** — superseded by this ADR.
  * **[ADR-002](adr-002-postgresql-pgvector.md)** — PostgreSQL portion remains
    Accepted; pgvector/embeddings remain deferred and the dependency is removed.
  * **[ADR-003](adr-003-redis-celery-queue.md)** — Redis/Celery remain deferred;
    v1.0 uses the in-process scheduler (OFF by default) and direct pipeline calls.