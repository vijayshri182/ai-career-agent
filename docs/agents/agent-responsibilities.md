# Agent Responsibilities

This document summarizes each agent's responsibilities, inputs, outputs, memory, and trust boundaries.

## Profile Agent

* **Responsibility:** CRUD for candidate profile and resume versions.
* **Inputs:** User form data, uploaded documents.
* **Outputs:** Normalized `Candidate`, `Resume`, `ResumeVersion` records.
* **Memory:** Long-term profile in PostgreSQL.
* **Trust boundary:** User-owned data, encrypted at rest.

## Job Discovery Agent

* **Responsibility:** Discover and normalize jobs from configured sources.
* **Inputs:** Source configuration, last crawl state.
* **Outputs:** `Job` records with raw extraction metadata.
* **Memory:** Per-source crawl cursors and timestamps.
* **Trust boundary:** Treats all external HTML/JSON as untrusted.

## Job Verification Agent

* **Responsibility:** Verify job/company legitimacy and score risk.
* **Inputs:** `Job` record.
* **Outputs:** `JobVerification` with risk score.
* **Memory:** Verified company cache.
* **Trust boundary:** External domains resolved, content parsed in sandbox.

## Job Matching Agent

* **Responsibility:** Calculate explainable match score.
* **Inputs:** Verified `Job` and `Candidate` profile.
* **Outputs:** `JobMatch` with score and reasons.
* **Memory:** Cached match results keyed by hash.
* **Trust boundary:** External job descriptions are sanitized; reasons must map to profile facts.

## Resume Agent

* **Responsibility:** Select and tailor resume.
* **Inputs:** `Job`, candidate profile, available resume versions.
* **Outputs:** Tailored `Document` (resume PDF) and selection rationale.
* **Memory:** Resume version history.
* **Trust boundary:** Never invent facts; only rephrase/reorder existing content.

## Application Agent

* **Responsibility:** Prepare application materials and answers.
* **Inputs:** `Job`, `Candidate`, selected resume.
* **Outputs:** `Application`, `ApplicationAnswer`, `Document` records.
* **Memory:** Draft versions and human edits.
* **Trust boundary:** Creates approval request before external submission.

## Recruiter Discovery Agent

* **Responsibility:** Find publicly available recruiting contacts.
* **Inputs:** `Company`, optionally `Job`.
* **Outputs:** `RecruiterContact` with confidence score.
* **Memory:** Previously discovered contacts and evidence URLs.
* **Trust boundary:** Only public sources; guessed contacts hidden.

## Outreach Agent

* **Responsibility:** Draft personalized messages.
* **Inputs:** Verified `RecruiterContact`, `Job`, profile.
* **Outputs:** `Outreach` draft pending approval.
* **Memory:** Message history and daily send caps.
* **Trust boundary:** No message sent without approval.

## Tracking Agent

* **Responsibility:** Maintain lifecycle states.
* **Inputs:** Events from other agents or user actions.
* **Outputs:** State transitions and audit events.
* **Memory:** State machine in PostgreSQL.
* **Trust boundary:** Internal; validates transitions.

## Learning Agent

* **Responsibility:** Analyze outcomes and recommend improvements.
* **Inputs:** Application outcomes, feedback, match history.
* **Outputs:** `Recommendation` records.
* **Memory:** Aggregated analytics.
* **Trust boundary:** Recommendations are suggestions only; factual data unchanged without approval.
