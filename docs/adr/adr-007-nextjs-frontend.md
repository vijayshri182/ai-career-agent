# ADR-007: Next.js for the Frontend

## Status

Proposed

## Context

The dashboard needs server-side rendering for fast initial loads, good SEO if public pages are added later, and a rich interactive UI for approvals and analytics.

## Decision

Use **Next.js** (App Router) with **TypeScript** and **Tailwind CSS**.

## Alternatives Considered

* **Plain React + Vite:** Simpler but loses SSR/SSG benefits.
* **Angular:** Strong but more opinionated and heavier for a solo developer.
* **Vue / Nuxt:** Good alternative; Next.js chosen for stronger job-market ecosystem and deployment options.

## Advantages

* Server components reduce client-side JavaScript.
* API routes can serve lightweight backend-for-frontend endpoints.
* Easy deployment to Vercel or any Node.js container host.
* TypeScript + Tailwind aligned with modern full-stack development.

## Disadvantages

* Next.jsApp Router has a learning curve.
* Server component caching can surprise; needs explicit revalidation.
* Larger bundle than a minimal React app.

## Migration / Scaling Considerations

* Frontend is decoupled from backend via REST API so it can be replaced later.
* Use SWR or React Query for client-side data fetching.
