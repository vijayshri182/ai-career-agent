# System Architecture Diagram

```mermaid
flowchart TB
    User([User])
    Dashboard[Web Dashboard<br/>Next.js + React]
    Gateway[API Gateway<br/>FastAPI]
    Orchestrator[Agent Orchestrator]

    subgraph Agents
        ProfileAgent[Profile Agent]
        DiscoveryAgent[Job Discovery Agent]
        VerificationAgent[Job Verification Agent]
        MatchingAgent[Job Matching Agent]
        ResumeAgent[Resume Agent]
        ApplicationAgent[Application Agent]
        RecruiterAgent[Recruiter Discovery Agent]
        OutreachAgent[Outreach Agent]
        TrackingAgent[Tracking Agent]
        LearningAgent[Learning Agent]
    end

    subgraph Tools
        HTTP[HTTP Client]
        Playwright[Playwright Browser]
        Email[Email Client]
        Sources[Job Sources / Career Sites]
    end

    subgraph Data
        Postgres[(PostgreSQL)]
        Vector[(pgvector)]
        Redis[(Redis Queue/Cache)]
        Store[Object Store]
        Audit[Audit Logs]
    end

    LLM[LLM Abstraction Layer]

    User --> Dashboard
    Dashboard --> Gateway
    Gateway --> Orchestrator
    Orchestrator --> Agents
    Agents --> Tools
    Agents --> Data
    Agents <--> LLM
    DiscoveryAgent --> Sources
    ApplicationAgent --> Playwright
    OutreachAgent --> Email
```

## Interaction Summary

1. The user interacts with the Next.js dashboard.
2. The dashboard calls the FastAPI gateway.
3. The gateway routes to services or triggers the orchestrator.
4. The orchestrator dispatches agents to Celery workers.
5. Agents use tools (HTTP, Playwright, email) and data stores.
6. The LLM abstraction layer supports structured generation and analysis.
7. Audit logs capture every security-relevant decision.
