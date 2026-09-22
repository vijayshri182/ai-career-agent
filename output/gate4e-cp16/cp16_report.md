# CP16 Completion Report — Recruiter Signal Domain Model

- **Project**: AI Career Agent `C:\Vijay_GitHub\ai-career-agent`
- **Task**: CP16 of the planned gate model — Establish the recruiter signal **domain model and persistence foundation**.
- **Status**: PASS
- **Date**: 2026-09-21

## Scope

CP16 delivers only the data/model foundation required for recruiter signals.
It **does not generate** signals, does not discover or score recruiters, does
not create outreach, and does not contact anyone. Signal generation remains a
future phase (CP17) that will build on this model.

## Existing Domain Reused

- `RecruiterContact` + `ContactSource` (already present in
  `src/backend/models/recruiter_contact.py`) are the canonical recruiter
  person/entity. **No second recruiter-profile entity was created.**
- `Company`, `Job`, `AuditEvent` are reused by reference (FK columns only).
- `CandidateRepository`, `JobRepository`, `CompanyRepository`,
  `RecruiterContactRepository`, `AuditRepository` are reused for ownership and
  audit.

## New Domain Objects

`src/backend/models/recruiter_signal.py`:

- **`RecruiterSignalType`** (controlled, evidence-oriented vocabulary):
  `RECRUITER_ASSOCIATED`, `RECRUITER_ROLE_RELEVANT`,
  `RECRUITER_CONTACT_AVAILABLE`, `RECRUITER_OUTREACH_CANDIDATE`.
  No predictive/evaluative labels (`BEST_RECRUITER`, `TOP_RECRUITER`,
  `HIGH_RESPONSE`, etc.) exist.
- **`RecruiterSignalStatus`** (lifecycle): `DISCOVERED`, `EVIDENCE_PENDING`,
  `READY_FOR_REVIEW`, `APPROVED`, `REJECTED`, `EXPIRED`.
- **`RecruiterSignal`** table `recruiter_signals`:
  - candidate-owned (`candidate_id` FK)
  - job-scoped (`job_id` FK, required)
  - `recruiter_contact_id` FK nullable (unknown recruiter stays NULL)
  - `company_id` FK nullable (context, never assumed)
  - `signal_type`, `status`, `signal_identity` (dedup key), `source`,
    `source_reference`, `evidence_json`, `provenance_json`
  - unique `(candidate_id, signal_identity)`
    (`uq_recruiter_signals_candidate_identity`)

Supporting artifacts:

- `src/backend/repositories/recruiter_signal.py` —
  `RecruiterSignalRepository` (get-for-candidate, find-by-identity, list with
  filters, count).
- `src/backend/services/recruiter_signal.py` — `RecruiterSignalService`
  (create/replay, explicit status transitions, read paths, ownership checks,
  audit logging, coherence validation).
- `src/backend/schemas/recruiter_signal.py` — `RecruiterSignalCreate`,
  `RecruiterSignalRead`, `RecruiterSignalStatusUpdate`,
  `RecruiterSignalListResponse`.
- Migration `migrations/versions/d16a7c9e52b0_add_recruiter_signal_foundation.py`
  (`down_revision = c13b4e5f6a7d`, verified head; upgrade + downgrade executed
  successfully against SQLite).
- `src/backend/models/__init__.py` — models registered for
  `SQLModel.metadata.create_all` (additive change only).

## Recruiter Profile Semantics

- Unknown recruiter identity is represented as `recruiter_contact_id = NULL`;
  no fabricated person data is ever written.
- Absence of evidence is **not** recorded as a negative fact — it simply
  remains NULL.
- `evidence_json` stores exactly what the source said; nothing is generated or
  embellished.

## Signal Types

Each type describes only what evidence showed:

| Type | Meaning |
| --- | --- |
| `RECRUITER_ASSOCIATED` | A known recruiting contact is associated with this job/company context (contact optional). |
| `RECRUITER_ROLE_RELEVANT` | Evidence shows a recruiting role relevant to the posting's company; no specific person identified. |
| `RECRUITER_CONTACT_AVAILABLE` | A public, usable contact element for a known recruiter is available (contact required). |
| `RECRUITER_OUTREACH_CANDIDATE` | Flagged for future **human review** as an outreach consideration; carries no authorization (contact required). |

Coherence is enforced at creation: role-relevant may not reference a contact;
contact-available and outreach-candidate require one.

## Signal Lifecycle

- New signals are created in `DISCOVERED`. `APPROVED` is **never** assigned
  implicitly and no path sets it at creation.
- Explicit transitions (service-enforced):
  - `DISCOVERED` -> `EVIDENCE_PENDING`, `READY_FOR_REVIEW`, `REJECTED`, `EXPIRED`
  - `EVIDENCE_PENDING` -> `READY_FOR_REVIEW`, `REJECTED`, `EXPIRED`
  - `READY_FOR_REVIEW` -> `APPROVED`, `REJECTED`, `EXPIRED`
  - `APPROVED` -> `EXPIRED`
  - `REJECTED` -> `EXPIRED`
  - `EXPIRED` -> (terminal)
- Invalid transitions raise `ValidationError`; identical status is a no-op.
- Human approval remains a separate boundary (Approval workflow, future phase).

## Deterministic Identity

- `signal_identity` = SHA-256 over canonical JSON of durable anchors:
  `candidate_id`, `job_id`, `recruiter_contact_id` (NULL-safe),
  `signal_type`, `source`, `source_reference`.
- Independent of mutable display text, timestamps, `company_id` context, and
  `evidence_json`/`provenance_json` content.
- Replaying identical evidence is a **no-op** (returns the existing row);
  dedupe is enforced in the service and at the database via the unique
  constraint.

## Provenance

Each signal retains: `source` (producer id), `source_reference` (reference
within producer records), `evidence_json` (lossless source statements),
`provenance_json` (producer/version metadata). Audit events
(`RECRUITER_SIGNAL_CREATED`, `RECRUITER_SIGNAL_STATUS_CHANGED`) are written for
mutations.

## Persistence

- New table `recruiter_signals` via migration `d16a7c9e52b0` (chained after
  `c13b4e5f6a7d`, confirmed as current head with `alembic heads`).
- Migration is deterministic and reversible; `upgrade head` (full 14-migration
  chain) and `downgrade c13b4e5f6a7d` executed cleanly on SQLite.
- Indexes limited to FK paths and the unique dedup key (matching access
  patterns).

## Security / Boundary

- No imports of `httpx`, `requests`, `urllib`, `socket`, `ssl`, `playwright`,
  `selenium`, `aiohttp`, `asyncio`, outreach, recruiter-discovery, or SMTP
  modules anywhere in the CP16 surface (verified with AST-based tests).
- No credentials/URLs stored; external evidence is treated as untrusted data.
- All candidate-scoped operations enforce ownership
  (`CandidateRepository.get_for_user_or_404`); foreign/nonexistent candidates
  are indistinguishable and raise `NotFoundError` without side effects.
- No API endpoints or CLI entry points added; no outbound I/O exists.

## Tests

- `tests/integration/test_gate4e_cp16_recruiter_signal.py` — **34 tests**:
  creation defaults and vocabulary, unknown-fields-are-NULL, coherence rules,
  owned-job/contact/company validation, audit logging, deterministic
  identity + replay no-op, identity differentiation (contact/type/job),
  lifecycle transitions (incl. explicit-only APPROVED, no terminal cycles,
  same-status no-op), read paths, filters, ordering, counts, cross-candidate
  ownership rejection, and the security/offline AST boundary tests.
- Focused run: 34 passed.
- Full suite: **380 passed** in 73.96s (baseline before CP16: 346; +34).
  Two consecutive full-suite runs produced identical green results.
- `ruff check` (CP16 files + models/__init__.py): clean.
- `mypy` (strict) on CP16 model/repo/service/schema: clean.

## Matcher Integrity

- `src/services/matching.py` SHA-256:
  `7CBAF15627C44D57EBD7B49AB1D99479BA96A491D70B42002B16AD0C4CF3BB41`
  — **unchanged** (byte-identical to the accepted CP14/CP15 baseline).
- No changes to `matching.py`, Approval, Notification, Dashboard,
  Gate4E ingestion behavior, or any CP13/14/15 test.

## Acceptance

1. Recruiter signal domain model + persistence exist. — **PASS**
2. Recruiter person/entity is the existing `RecruiterContact`; no duplicate
   recruiter-profile entity created. — **PASS**
3. `RecruiterSignal.recruiter_contact_id` nullable reference. — **PASS**
4. No signal-generation path exists in CP16 (foundation only). — **PASS**
5. No autonomous outreach/contacting path exists anywhere in CP16. — **PASS**
6. Controlled, validated, evidence-oriented `signal_type` vocabulary
   (no best/rank/prediction labels). — **PASS**
7. Recruiter semantics: unknown stays NULL; absence is not a negative fact;
   no fabrication. — **PASS**
8. Deterministic dedup identity; replay is a no-op; idempotent. — **PASS**
9. Explicit lifecycle with documented transitions. — **PASS**
10. Lifecycle has terminal states and no cycles. — **PASS**
11. `APPROVED` is human-decision only; never implicit; creation never
    auto-approves. — **PASS**
12. Provenance preserved (source, source_reference, evidence_json,
    provenance_json) + audit trail. — **PASS**
13. Evidence treated as untrusted data; no credentials stored. — **PASS**
14. Deterministic, reversible migration; Alembic head verified and executed. — **PASS**
15. Candidate-scoped ownership enforced; foreign candidates rejected. — **PASS**
16. ~34 focused tests added; full suite green (380), no regressions. — **PASS**
17. Matcher baseline hash unchanged; CP14/15 behavior and tests untouched. — **PASS**

## Known Limitations

- No public API endpoints were added; none are genuinely required for the
  domain-model foundation. The service/repository layer is the intended
  integration surface for future phases.
- `RecruiterSignal` declares FK columns only (no SQLModel `Relationship`
  back_populates), keeping changes to pre-existing model files limited to the
  additive `models/__init__.py` registration.
- `company_id` is stored as context but intentionally excluded from
  `signal_identity` (a company is derivable from the job and is not a durable
  identity anchor).
- Status transitions are enforced in the service layer (consistent with the
  existing codebase), not via DB-level CHECK constraints.
- The migration was verified on SQLite only; Postgres deployment will run the
  same deterministic migration.

## Final Status

**PASS** — CP16 completes the recruiter signal domain model foundation with no
matcher or existing-behavior changes, no outbound/network surface, deterministic
identity and replay safety, explicit human-only approval semantics, and a green
full suite (380 passed).