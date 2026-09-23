# API Overview

The backend exposes a REST API consumed by the dashboard and external triggers.

## Base URL

```text
/api/v1
```

## Authentication

All endpoints require a valid OAuth2 bearer token except public health checks.

## Content Type

```text
Content-Type: application/json
```

## Resource Areas

| Area | Prefix | Description |
|------|--------|-------------|
| Auth | `/auth` | Register, login, `me`. |
| Candidates | `/candidates/{candidate_id}` | Profile, skills, experience, education, certifications. |
| Resumes | `/candidates/{candidate_id}/resumes` | Resume containers, versions, parsing. |
| Sources | `/candidates/{candidate_id}/sources` | Job sources / discovery config. |
| Jobs | `/candidates/{candidate_id}/jobs` | Discovered jobs. |
| Matching | `/candidates/{candidate_id}/matching` | Match evaluation, lists, explanations. |
| Applications | `/candidates/{candidate_id}/applications` | Preparation and lifecycle. |
| Approvals | `/candidates/{candidate_id}/approvals` | Human approval requests and decisions. |
| Audit | `/candidates/{candidate_id}/audit-events` | Candidate-scoped audit trail read API. |
| Outreach | `/candidates/{candidate_id}/outreach` | Recruiter outreach drafts, submits, sends. |
| Contacts | `/candidates/{candidate_id}/recruiter-contacts` | Discovered recruiting contacts. |
| Dashboard | `/candidates/{candidate_id}/dashboard` | Summary and analytics. |
| Notifications | `/candidates/{candidate_id}/notifications` | User notifications and preferences. |
| Automation | `/candidates/{candidate_id}/automation` | Recorded application-automation runs (submission is a future phase). |
| Discovery runs | `/candidates/{candidate_id}/discovery-runs` | Trigger and list discovery runs (agent-task outcomes). |

Caveat: every candidate-scoped route resolves ownership through `get_owned_candidate`,
so cross-user or non-existent candidates are indistinguishable (404).

## Response Envelope

```json
{
  "success": true,
  "data": {},
  "meta": {
    "page": 1,
    "page_size": 20,
    "total": 100
  },
  "error": null
}
```

## Error Format

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input",
    "details": []
  }
}
```

## OpenAPI

FastAPI auto-generates OpenAPI docs at `/api/docs` and `/api/openapi.json`.

## Rate Limits

Not currently enforced at the middleware level. The planned model is
authenticated 100 requests/minute per user and a tight per-IP cap on public
health endpoints; revisit before production exposure.

## Status Codes

* `200 OK` — success.
* `201 Created` — resource created.
* `202 Accepted` — async task accepted.
* `400 Bad Request` — validation error.
* `401 Unauthorized` — missing/invalid token.
* `403 Forbidden` — insufficient permissions.
* `404 Not Found` — resource does not exist.
* `409 Conflict` — duplicate or invalid state transition.
* `429 Too Many Requests` — rate limit.
* `500 Internal Server Error` — server error (logged, not detailed to client).
