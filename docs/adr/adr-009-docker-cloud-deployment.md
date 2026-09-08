# ADR-009: Docker + Cloud Container Service for Deployment

## Status

Proposed

## Context

The agent must run 24×7 in the cloud. The deployment target should be portable, cost-effective for an MVP, and easy to scale.

## Decision

Containerize with **Docker** and deploy to a cloud container service (e.g., AWS ECS Fargate, GCP Cloud Run, Azure Container Apps, or a Kubernetes cluster).

## Alternatives Considered

* **Vercel / serverless functions:** Good for frontend and API but not for long-running Celery workers or Playwright browsers.
* **Self-managed VPS:** Cheap but requires maintenance and lacks auto-recovery.
* **Kubernetes from day one:** Too complex for a solo MVP; acceptable later.

## Advantages

* Docker ensures consistency between local dev and production.
* Cloud container services provide auto-healing, scaling, and managed load balancing.
* No lock-in to a single cloud if containers remain standard.

## Disadvantages

* Cloud costs can grow; must monitor and use cost controls.
* Playwright containers need significant memory/CPU.

## Migration / Scaling Considerations

* Start with one container for API + Beat and one for workers; scale horizontally as needed.
* Move to Kubernetes if multi-service complexity justifies it.
* Use infrastructure-as-code (Terraform/Pulumi) from Phase 11.
