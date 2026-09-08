# Minimum Viable Product (MVP)

## Objective

Validate the core workflow manually before adding automation.

## MVP Capabilities

```text
Discover → Verify → Match → Prepare → Approve → Track
```

### Included

1. **Candidate profile** — create and edit profile, skills, experience, preferences, resume versions.
2. **Job discovery** — at least one permitted source ingesting jobs.
3. **Job verification** — company/domain check and risk score.
4. **AI matching** — explainable 0–100 score.
5. **Resume recommendation** — select best resume version.
6. **Application preparation** — draft cover letter and answers.
7. **Human approval** — dashboard approval screen.
8. **Tracking** — lifecycle state machine and notifications.

### Excluded from MVP

* Automatic application submission.
* Recruiter contact discovery.
* Automated outreach / email sending.
* 24×7 cloud production deployment.
* Advanced learning/optimization.

## MVP Acceptance Criteria

* User can create a complete candidate profile.
* System discovers jobs and shows only verified, low-risk postings.
* Each job shows a match score and clear reasons.
* User can review prepared application materials before any action.
* Approval workflow blocks external actions until user decides.
* Dashboard shows pipeline and notifications.

## Why This MVP?

Proving the manual workflow first ensures:

* Quality of AI-generated materials.
* User trust in the approval model.
* Correct security and privacy boundaries.
* Foundation for safe, incremental automation.
