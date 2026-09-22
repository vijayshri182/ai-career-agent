# ADR-005: LangChain / LangGraph for LLM Abstraction

## Status

Deferred (not implemented)

## Context

The system will use LLMs for matching, resume tailoring, cover-letter generation, and learning. The chosen provider may change based on cost, quality, or regional availability.

## Current Implementation (v0.1.0)

All intelligence is **deterministic** and network-free:

* Job normalization uses rule/heuristic parsers.
* Matching is a weighted, rule-based scorer (`backend/services/matching.py`).
* Skill normalization uses a curated synonym graph.
* Application-prep and outreach drafting use template/human-input content only.

No LLM provider SDK (OpenAI, Anthropic, Google, LangChain, LangGraph, embeddings) is
imported or called at runtime, and no AI SDKs are present in the project dependencies.
This guarantees zero outbound AI calls; the AI boundary is enforced at the dependency
level.

## Decision

Use **LangChain** (and later **LangGraph** for multi-step agent workflows) as the LLM abstraction layer.

## Alternatives Considered

* **Direct provider SDKs (OpenAI, Anthropic, Google):** Tight coupling; switching providers requires code changes.
* **LiteLLM:** Lightweight abstraction; evaluated but LangChain offers richer prompt/chain/tool management.
* **Custom wrapper:** Would add maintenance burden.

## Advantages

* Provider-agnostic model switching via environment config.
* Structured output parsing with Pydantic.
* Prompt templates and version management.
* Easy integration with vector stores and tools.
* LangGraph supports explicit state-machine agent flows.

## Disadvantages

* LangChain can be overly complex for simple use cases.
* Version upgrades sometimes introduce breaking changes.
* Must carefully control prompt injection and chain behavior.

## Migration / Scaling Considerations

* Wrap LangChain usage in internal `llm/` modules so provider switches are localized.
* Cache expensive LLM calls by content hash.
* Monitor token usage and cost per agent run.
