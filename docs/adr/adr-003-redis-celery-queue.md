# ADR-003: Redis + Celery for Queue and Scheduling

## Status

Deferred (not required in v1.0; in-process scheduler, OFF by default)

## Context

The agent workflows are asynchronous and must run 24×7. We need a task queue, distributed locking, retries, and a scheduler for periodic discovery/matching runs.

## Current Implementation (v1.0)

No Redis or Celery is deployed or required. Scheduling is an **in-process
scheduler** that is **OFF by default** (`DISCOVERY_ENABLED` defaults to `false`)
and `inert until started`; activation is a separate operational approval. The
discovery/matching pipeline runs as direct, awaited service calls with idempotency
and at-most-once guards. See [ADR-011 — Deterministic-Only Runtime](adr-011-deterministic-only-runtime.md).

## Decision

Use **Redis** as the broker and result backend, with **Celery** workers and **Celery Beat** for scheduling.

## Alternatives Considered

* **RQ:** Simpler but less mature retry and scheduling features.
* **Celery + RabbitMQ:** RabbitMQ is more robust but adds operational overhead.
* **AWS SQS / GCP PubSub:** Cloud-specific; would reduce portability.
* **Temporal / Windmill:** Powerful workflow engines but overkill for the MVP.

## Advantages

* Celery is battle-tested, well-documented, and integrates with Python.
* Redis is already needed for caching and sessions, so reusing it simplifies ops.
* Built-in retries, rate limiting, and dead-letter handling.
* Celery Beat handles periodic scheduling.

## Disadvantages

* Celery configuration can be complex (acks, visibility timeouts).
* Redis as a result backend can grow; results should have TTLs.
* Not ideal for very long-running workflows; agents should be idempotent and resumable.

## Migration / Scaling Considerations

* Worker pools can scale horizontally by adding containers.
* If workflow complexity grows, evaluate Temporal or Argo Workflows.
* Result backend can be switched to PostgreSQL if Redis memory becomes a concern.
