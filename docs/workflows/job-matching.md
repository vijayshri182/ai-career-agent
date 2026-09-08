# Job Matching Workflow

## Goal

Calculate an explainable match score between a verified job and the candidate profile.

## Flow

```mermaid
sequenceDiagram
    participant S as Scheduler
    participant MA as Matching Agent
    participant Rules as Rule Engine
    participant LLM as LLM Layer
    participant DB as Database

    S->>MA: match_verified_jobs()
    MA->>DB: load candidate profile
    MA->>DB: load verified jobs
    loop Each job
        MA->>Rules: pre_score(job, profile)
        Rules-->>MA: base_score + gaps
        MA->>LLM: structured semantic analysis
        LLM-->>MA: score + reason list
        MA->>MA: combine and normalize to 0-100
        MA->>DB: store JobMatch
    end
```

## Match Dimensions

| Dimension | Weight (initial) | Example signals |
|-----------|-----------------|-----------------|
| Skills | 30% | Java, Spring Boot, Kubernetes, AWS |
| Experience | 20% | Years in relevant roles |
| Seniority / Leadership | 15% | Engineering management, team leadership |
| Domain | 15% | Telecom, OSS/BSS, CPQ/PIM |
| Location / Work mode | 10% | Remote, preferred cities |
| AI / Emerging tech | 10% | GenAI, AI-enabled SDLC |

Weights are user-configurable.

## Explainability

Each match includes a list of reasons:

* Strong Java/Spring Boot match.
* Strong engineering leadership match.
* Strong telecom domain match.
* Location compatible.
* AI experience relevant.

## Caching

Match results are cached by `(job_content_hash, profile_hash)` to avoid repeated LLM calls.

## Outputs

* `JobMatch` record.
* In-app notification if score ≥ configured threshold.
