# ADR-002: PostgreSQL + pgvector as Primary Data Store

## Status

Accepted for PostgreSQL; pgvector deferred (dependency removed; see ADR-011)

## Context

The system needs a relational store for profiles, jobs, applications, approvals, and audit events. It also needs vector search for semantic job/profile matching and RAG.

## Current Implementation (v0.1.0)

PostgreSQL 16 is the primary store (migrations at `migrations/`, head
`f6e5d4c3b2a1`). Vector search is **not** active and is out of scope: the `pgvector`
extension is not used, no embedding columns exist, matching is deterministic
rule-based scoring, and the `pgvector` dependency has been removed from the project
dependencies. See [ADR-011 — Deterministic-Only Runtime](adr-011-deterministic-only-runtime.md)
for the governing runtime decision.

## Decision

Use **PostgreSQL 15+** with the **pgvector** extension as the primary data and vector store initially.

## Alternatives Considered

* **PostgreSQL + separate Pinecone/Weaviate:** Adds another managed service and integration to maintain.
* **MongoDB:** Flexible schema but weaker transaction support and consistency guarantees for core workflows.
* **SQLite:** Too limited for concurrent workers and cloud deployment.

## Advantages

* Single database for relational and vector data reduces operational complexity.
* ACID transactions for state-machine transitions.
* Mature tooling, backups, and hosting options.
* Scales well into the medium term.

## Disadvantages

* pgvector may not match dedicated vector DBs at very high embedding volumes; can be migrated later.
* Requires careful index tuning (`ivfflat` / `hnsw`).

## Migration / Scaling Considerations

* If vector volume exceeds PostgreSQL comfort, migrate embeddings to a dedicated vector database while keeping relational data in PostgreSQL.
* Abstract vector operations behind a repository interface to make migration straightforward.
