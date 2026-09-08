# Application Preparation Workflow

## Goal

Prepare a tailored application package (resume, cover letter, answers) for a high-match job while preserving factual accuracy.

## Flow

```mermaid
flowchart TB
    J[Verified + High-match Job]
    RS[Resume Agent selects best resume]
    RT[Generate tailored resume]
    CL[Generate cover letter]
    AQ[Detect & answer screening questions]
    HI[Flag human-input questions]
    APP[Create Application record]
    AP[Create Approval Request]

    J --> RS --> RT --> APP
    J --> CL --> APP
    J --> AQ --> HI --> APP
    APP --> AP
```

## Inputs

* `Job` and `JobMatch`.
* `Candidate` profile and `Resume` versions.

## Outputs

* `Application` with status `PREPARED`.
* `Document` records for resume and cover letter.
* `ApplicationAnswer` records.
* `Approval` request for the user.

## Constraints

* Generated resume cannot contain experience not in `Experience` or `CandidateSkill`.
* Cover letter must reference actual job and candidate capabilities.
* Answers must be derived from profile facts; uncertain questions flagged for human input.

## Versioning

Every generated document is stored as a `Document` record. Human edits create new versions rather than overwriting originals.
