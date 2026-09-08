# Threat Model

## Scope

This threat model covers the AI Career Agent system, its data flows, external integrations, and user interactions.

## Threat Actors

| Actor | Motive | Capability |
|-------|--------|------------|
| External attacker | Steal PII/resumes, abuse automation | Network, phishing, prompt injection |
| Malicious job source | Inject instructions, deliver malware links | Controls job description or site |
| Insider / admin | Access candidate data improperly | Legitimate credentials |
| User error | Accidentally approve bad application | Authenticated user |

## STRIDE Analysis

| Threat ID | Category | Description | Mitigation |
|-----------|----------|-------------|------------|
| T01 | Spoofing | Attacker impersonates user. | OAuth2/OIDC, MFA, short-lived tokens. |
| T02 | Tampering | Modified job description changes agent behavior. | Strict schema parsing, prompt injection guards. |
| T03 | Repudiation | User denies approving an application. | Append-only audit log with signed decision records. |
| T04 | Information Disclosure | Resume or PII leaked. | Encryption at rest, signed URLs, least privilege. |
| T05 | Denial of Service | Abuse discovery or LLM endpoints. | Rate limits, budgets, queue back-pressure. |
| T06 | Elevation of Privilege | Agent script gains system access. | Container sandbox, restricted network egress. |
| T07 | Abuse | System used for spam or unauthorized applications. | Human approval, send caps, source allow-list. |

## Trust Boundaries

See [`../../SECURITY.md`](../../SECURITY.md). The main boundaries are:

1. External internet → DMZ (gateway/browser workers).
2. DMZ → Trusted backend/database.
3. Backend ↔ secrets vault.
4. User input → validated API payloads.

## Attack Scenarios

### Prompt Injection via Job Description

A job description contains instructions telling the LLM to ignore previous rules. The system mitigates this through delimiter separation, schema validation, and explicit system instructions to ignore embedded commands.

### Credential Theft from Browser Session

A compromised source page attempts to steal stored credentials. Mitigation: isolated browser sessions, no password autofill, no credential persistence, secure vault access only from backend.

### Unauthorized Application Submission

A bug or malicious agent attempts to apply without approval. Mitigation: approval service gates external actions; audit log records every decision.

## Review Cadence

Update this model after major architecture changes or at least once per quarter.
