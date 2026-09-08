# ADR-001: Python + FastAPI Backend

## Status

Proposed

## Context

The backend needs to serve a REST API, orchestrate asynchronous agents, interact with the database, run browser automation, and call LLM services. The developer is comfortable with JVM ecosystems (Java/Spring Boot) but the project is a solo MVP where velocity and AI-library maturity matter.

## Decision

Use **Python 3.12+** with **FastAPI** as the primary backend framework.

## Alternatives Considered

* **Java + Spring Boot:** Excellent for large teams and strict typing, but heavier boilerplate and slower iteration for a solo MVP.
* **Node.js + Express/NestJS:** Good for full-stack TypeScript, but Python has stronger libraries for LLM orchestration, data parsing, and browser automation.
* **Go:** Great performance, but smaller ecosystem for LLM and browser tooling.

## Advantages

* Rich ecosystem for AI/LLM (LangChain, LangGraph, OpenAI SDK, etc.).
* FastAPI provides async request handling and automatic OpenAPI docs.
* Pydantic enables strict input validation.
* Celery integrates naturally for background workers.
* Playwright has first-class Python support.

## Disadvantages

* Dynamic typing requires discipline; mitigated by type hints, Pydantic, and strict linting.
* Python concurrency is weaker than Go/Java for CPU-bound tasks; mitigated by async I/O and worker processes.
* Runtime errors can surface later; mitigated by comprehensive tests.

## Migration / Scaling Considerations

* Start as a monolith. If a service boundary emerges (e.g., heavy browser farm), extract it behind a well-defined API.
* Keep business logic in `services/` so framework changes are isolated.
