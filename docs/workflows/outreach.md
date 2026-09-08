# Outreach Workflow

## Goal

Prepare personalized recruiter and networking messages and send them only after explicit approval.

## Flow

```mermaid
sequenceDiagram
    participant OA as Outreach Agent
    participant Draft as Message Drafter
    participant RL as Rate Limiter
    participant AS as Approval Service
    participant Email as Email Client
    participant DB as Database

    OA->>Draft: generate(contact, job, profile)
    Draft-->>OA: personalized message
    OA->>RL: check daily cap
    RL-->>OA: allowed / blocked
    OA->>AS: request approval
    AS-->>OA: approved
    OA->>Email: send message
    Email-->>OA: status
    OA->>DB: store Outreach SENT / FAILED
```

## Inputs

* Verified `RecruiterContact`.
* `Job` and `Candidate` profile.

## Outputs

* `Outreach` record, initially `DRAFT` then `APPROVAL_REQUIRED`.

## Rate Limiting

* Daily send cap per user (default low, e.g., 5–10).
* Minimum interval between sends.
* Per-source limits respected.

## Approval

Outreach defaults to human approval. Level 3 autonomy may send pre-approved templates only on verified contacts.
