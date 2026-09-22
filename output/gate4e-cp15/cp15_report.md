# CP15 — Controlled Matching Eligibility & Read-Only Evaluation

## Scope

CP15 implements and validates the controlled Gate 4E -> ACA eligibility boundary and a
strictly read-only matching evaluation:

1. **Ingestion integration (read side only):** reads the ACA-owned ingestion rows
   persisted by the CP13 ingestion service from the CP14 handoff fixture.
2. **Eligibility classification:** a deterministic, conservative policy produces an
   explicit eligibility decision for every ingestion record
   (`Gate4eEligibilityService`).
3. **Read-only matching evaluation:** only policy-eligible records are handed to the
   existing matching engine (`JobMatchScorer` / `JobTextParser`) through
   `Gate4eReadOnlyMatchEvaluator`. Nothing is persisted, scored for ranking, or
   re-implemented.
4. **Deterministic audit/report:** the offline evaluation emits a normalized,
   byte-identical-across-runs report.

CP15 does NOT implement notifications, dashboards, recruiter signals, approvals,
outreach, applications, Gmail/LinkedIn operations, or any outbound communication.

## Input

- **CP14 handoff fixture:** `tests/fixtures/gate4e_cp10_official_postings.json` — the
  persisted Gate 4E CP10 artifact (5 real alerts).
- **Persisted-state reconstruction:** the CP13 ingestion outcome is rebuilt exactly
  (in memory, no DB) from the fixture, plus the same deterministic policy-path probes
  the CP15 test suite uses (`UNRESOLVED`, `BOGUS`, missing status) — 8 records total
  (alerts 1-5, 11-13).
- **Offline evaluation script:** `scripts/gate4e_cp15_evaluation.py`.

## Eligibility policy

Policy version `1` (conservative by default; controlled opt-in for PARTIAL-with-URL).

| Record class (alerts) | Conservative result | Controlled opt-in (`allow_partial_with_url=True`) |
|---|---|---|
| VERIFIED (Capgemini, #3) | ELIGIBLE (`ELIGIBLE_VERIFIED`) | ELIGIBLE (`ELIGIBLE_VERIFIED`) |
| PARTIAL with URL (Optum, #5) | EXCLUDED (`EXCLUDED_PARTIAL_WITH_URL_POLICY_PENDING`) | ELIGIBLE (`ELIGIBLE_PARTIAL_WITH_URL_CONTROLLED`); stays PARTIAL, never becomes VERIFIED |
| PARTIAL without URL (#1, #2, #4) | EXCLUDED, quarantined (`EXCLUDED_PARTIAL_NO_URL_QUARANTINED`) | same; no URL fabricated |
| UNRESOLVED (#11) | EXCLUDED, quarantined (`EXCLUDED_UNRESOLVED_QUARANTINED`) | same |
| REJECTED_INVALID (#12 BOGUS, #13 missing status) | EXCLUDED (`EXCLUDED_REJECTED_INVALID`) | same |
| Quarantined DISCOVERED records | Never matched (job_id `None`, `matching_invoked` = 0) | same |

Result counts (offline evaluation): conservative = 1 eligible / 7 excluded / 1
evaluated; controlled = 2 eligible / 6 excluded / 2 evaluated. Verification status is
never reinterpreted: PARTIAL is never treated as VERIFIED, missing fields are never
treated as negative facts.

## Matching evaluation

- **Read-only:** `Gate4eReadOnlyMatchEvaluator` uses the production `JobMatchScorer`
  (rules version `3.0.0`) and `JobTextParser` but only the pure, stateless surface in
  `backend.services.matching`. It does NOT invoke `JobMatchingService` (which would
  persist `JobMatch` rows and trigger notifiers). No DB engine or session is created;
  the offline evaluation uses in-memory repositories with identical async read-only
  interfaces.
- **Matcher baseline hash:** `7CBAF15627C44D57EBD7B49AB1D99479BA96A491D70B42002B16AD0C4CF3BB41`.
- **No matcher modification during CP15:** `src/backend/services/matching.py` was
  verified with the hash above (unchanged). This matcher — including its pre-existing,
  accepted Notification-feature hook — is the working-tree baseline pinned by BOTH the
  CP14 test (`EXPECTED_MATCHER_SHA256`, line 41) and the CP15 test (`MATCHER_SHA256`,
  line 48). The baseline audit confirmed the Notification edit predates CP15 (CP14
  pinned the identical hash first); it is preserved, not reverted.
- **No duplication:** CP15 files import only `JobMatchScorer`, `JobTextParser`,
  `CandidateProfile`, `CandidateSkillProfile`, `CandidateExperienceProfile` from
  `backend.services.matching`, and assert no scoring constants are re-declared.

## Determinism

The offline evaluation (`scripts/gate4e_cp15_evaluation.py`) was executed twice with
identical inputs (`--input tests/fixtures/gate4e_cp10_official_postings.json`). Both
runs exited `0` and produced byte-identical JSON (SHA-256
`85C3575C82A9AB3ED0437044C5D11781CD4F268154392D8A6AD36D1306E0DF92`). Runtime
timestamps are normalized away and every list is sorted before serialization; record
identities (ingestion identity, posting key) use the same deterministic SHA-256 scheme
as CP13/CP14.

## Tests

- **CP15 focused:** `tests/integration/test_gate4e_cp15_eligibility.py` — **38 passed
  in 9.22s** (20 test functions incl. parametrized no-network/no-import matrix,
  real-fixture ingestion through the CP13 boundary, eligibility policy cases,
  read-only/no-write assertions, and `test_matcher_sha256_unchanged`).
- **Full suite:** `python -m pytest -q` — **346 passed in 117.83s (0:01:57), zero
  failures.**
- No unrelated tests were modified to achieve these results.

## Security / boundary checks

Explicitly confirmed by the offline evaluation guards and the CP15 test matrix:

- **No Gmail writes / sends:** no imap/smtp imports or calls; Gmail message IDs are
  preserved as passive identity data only.
- **No LinkedIn scraping/fetch:** linkedIn URLs are preserved as opaque evidence only;
  no LinkedIn tokens or fetch calls.
- **No outbound communication:** scan of CP15 module + script source for network/IO
  surfaces (`httpx`, `requests`, `aiohttp`, `urllib`, `socket`, `websocket`,
  `subprocess`, `webbrowser`, ...) found zero hits.
- **No applications / outreach / approvals / recruiter signals:** no such imports or
  calls in CP15 scope.
- **No external network dependency:** offline, in-memory, JSON-only evaluation.
- **No credentials/secrets exposed:** the script hardcodes no secrets; the fallback
  fixture data contains no credentials.

## Acceptance

| # | Acceptance condition | Result |
|---|---|---|
| 1 | VERIFIED records are eligible for (read-only) matching | PASS |
| 2 | PARTIAL-with-URL follows the CP15 policy and is never treated as VERIFIED | PASS |
| 3 | PARTIAL-without-URL is excluded/quarantined; no URL fabricated | PASS |
| 4 | UNRESOLVED is excluded/quarantined | PASS |
| 5 | REJECTED_INVALID is excluded | PASS |
| 6 | No fake/derived URL is generated | PASS |
| 7 | Evidence/provenance/identity fields remain intact (verbatim JSON preserved) | PASS |
| 8 | Matching evaluation is read-only (zero rows written) | PASS |
| 9 | No outreach/recruiter/approval/Gmail/LinkedIn/network operation occurs | PASS |
| 10 | Output is deterministic (byte-identical across two runs) | PASS |
| 11 | `matching.py` remains at the accepted baseline hash (unchanged) | PASS |
| 12 | CP15 focused tests pass | PASS (38 passed) |
| 13 | Full test suite passes with no regressions | PASS (346 passed) |

## Known limitations

- The evaluation reconstructs the CP13-persisted ingestion store in memory rather
  than querying a live database; this is the same offline-deterministic approach used
  by the CP14 handoff script and keeps CP15 network/DB free. Live-DB behavior is
  exercised by the CP15 integration tests against the in-memory SQLite session.
- `matching.py` differs from the last commit `HEAD` due to the accepted, pre-existing
  Notification-feature hook (uncommitted working-tree baseline pinned by CP14 and CP15
  tests). This is an intentional baseline, not a CP15 change.
- Candidate/job profile used by the read-only evaluator in the offline script is a
  fixed deterministic stub; ranking/score values are not acceptance criteria for CP15
  (the report omits scores/rankings per CP15 scope).
- Pre-existing project ruff/mypy configuration shows a non-blocking note
  (`pyproject.toml: unused section(s): module = ['backend.api.*']`); it predates CP15
  and is unrelated debt.

## Final status

**PASS**

All mandatory CP15 acceptance conditions are satisfied: eligibility policy verified
for every record class, read-only evaluation confirmed with zero writes, matcher
baseline hash preserved, deterministic output proven across two identical runs, CP15
focused tests (38) and the full suite (346) both fully green.