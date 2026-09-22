# ADR-002: PostgreSQL + pgvector as Primary Data Store

## Status

Accepted for PostgreSQL; pgvector deferred

## Context

The system needs a relational store for profiles, jobs, applications, approvals, and audit events. It also needs vector search for semantic job/profile matching and RAG.

## Current Implementation (v0.1.0)

PostgreSQL 16 is the primary store (migrations at `migrations/`). Vector search is
**not** active: the `pgvector` extension is not used, no embedding columns exist, and
matching is deterministic rule-based scoring. If semantic matching is added later, the
pgvector decision below applies; until then embeddings are out of scope.

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
