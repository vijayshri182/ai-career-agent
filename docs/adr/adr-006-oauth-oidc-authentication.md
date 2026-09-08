# ADR-006: OAuth2 / OIDC for Authentication

## Status

Proposed

## Context

The application stores sensitive candidate information. Storing passwords locally increases risk and operational burden.

## Decision

Use **OAuth2 / OpenID Connect** with a trusted identity provider (e.g., Auth0, Google, GitHub, or a corporate IdP).

## Alternatives Considered

* **Local username/password:** Requires secure storage, MFA, and password recovery; rejected.
* **Magic links:** Stateless but less convenient for frequent use.
* **SAML:** Useful for enterprise IdPs; can be added later.

## Advantages

* No plaintext passwords in the application.
* Built-in MFA and session security from the provider.
* Standard JWT access tokens for API authorization.

## Disadvantages

* Dependency on external identity provider availability.
* Need to handle token refresh and logout flows.

## Migration / Scaling Considerations

* Abstract auth behind FastAPI dependencies so provider changes are localized.
* Store session state in Redis with TTL.
* Add SAML support if enterprise use cases arise.
