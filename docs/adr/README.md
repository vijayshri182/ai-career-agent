# Architecture Decision Records

This directory records major architecture and technology decisions for the AI Career Agent project.

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-001](adr-001-python-fastapi-backend.md) | Python + FastAPI for the backend | Proposed |
| [ADR-002](adr-002-postgresql-pgvector.md) | PostgreSQL + pgvector for primary data | Proposed |
| [ADR-003](adr-003-redis-celery-queue.md) | Redis + Celery for queue and scheduling | Proposed |
| [ADR-004](adr-004-playwright-browser.md) | Playwright for browser automation | Proposed |
| [ADR-005](adr-005-langchain-llm-abstraction.md) | LangChain / LangGraph for LLM abstraction | Proposed |
| [ADR-006](adr-006-oauth-oidc-authentication.md) | OAuth2 / OIDC for authentication | Proposed |
| [ADR-007](adr-007-nextjs-frontend.md) | Next.js for the frontend | Proposed |
| [ADR-008](adr-008-agent-orchestrator.md) | Agent orchestrator + event-driven workflows | Proposed |
| [ADR-009](adr-009-docker-cloud-deployment.md) | Docker + cloud container service for deployment | Proposed |

## New ADRs

Create a new ADR for any decision that:

* Adds a new major dependency or service.
* Changes the boundary between agents, services, or layers.
* Alters security, trust, or compliance posture.

Use the existing files as a template.
