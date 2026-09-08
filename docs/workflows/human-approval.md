# Human Approval Workflow

## Goal

Ensure the user explicitly authorizes any external action before it is executed.

## Default Autonomy Level

**Level 2 — Prepare + Human Approval.**

## Flow

```mermaid
sequenceDiagram
    participant AA as Application / Outreach Agent
    participant AS as Approval Service
    participant DB as Database
    participant NS as Notification Service
    participant U as User Dashboard

    AA->>AS: request_approval(entity, draft, action)
    AS->>DB: create Approval PENDING
    AS->>NS: notify user
    U->>AS: GET approvals
    AS-->>U: pending items + context
    U->>AS: decide (approve / reject / edit / snooze)
    AS->>DB: update Approval + append AuditEvent
    alt approved
        AS-->>AA: resume workflow
    else rejected/snoozed
        AS-->>AA: cancel / defer
    end
```

## Approval Context

Each approval request includes:

* Job title, company, location.
* Match score and reasons.
* Draft resume/cover letter/answers or message.
* Recommended action.
* Deadline (optional).

## Decisions

* **Approve** — continue workflow.
* **Reject** — mark entity rejected and stop.
* **Edit** — allow user to modify materials; create new approval request.
* **Snooze** — defer decision and remind later.

## Audit

Every decision writes to `AuditEvent` with actor, timestamp, and outcome.
