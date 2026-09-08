# ADR-008: Agent Orchestrator + Event-Driven Workflows

## Status

Proposed

## Context

The system has many specialized AI agents. A central coordinator is needed to dispatch work, manage state, handle retries, and insert human approvals.

## Decision

Implement an **Agent Orchestrator** that stores workflow state in PostgreSQL and dispatches tasks to Celery workers. Agents communicate via shared state and events, not direct calls.

## Alternatives Considered

* **Fully autonomous multi-agent chat:** Hard to debug, non-deterministic, no clear approval checkpoints.
* **Direct service-to-service calls:** Tight coupling and poor resilience.
* **Dedicated workflow engine (Temporal):** Powerful but overkill for the MVP.

## Advantages

* Clear state machine and audit trail.
* Idempotency and retry handled centrally.
* Easy to pause for human approval without blocking workers.
* Agents can be developed and scaled independently.

## Disadvantages

* Adds a central component that must be reliable.
* Eventual consistency requires careful UI design.

## Migration / Scaling Considerations

* Orchestrator logic should stay thin; business rules live in agents/services.
* If workflow complexity grows significantly, evaluate Temporal or similar without changing agent contracts.
