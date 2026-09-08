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
| Profiles | `/profiles` | Candidate profile and resume versions. |
| Jobs | `/jobs` | Discovered and verified jobs. |
| Matches | `/matches` | Match scores and explanations. |
| Applications | `/applications` | Application preparation and lifecycle. |
| Approvals | `/approvals` | Human approval requests and decisions. |
| Outreach | `/outreach` | Recruiter outreach drafts and sends. |
| Contacts | `/recruiter-contacts` | Discovered recruiting contacts. |
| Dashboard | `/dashboard` | Summary and analytics. |
| Notifications | `/notifications` | User notifications. |
| Agent tasks | `/agent-tasks` | Trigger and inspect agent runs. |

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

FastAPI auto-generates OpenAPI docs at `/docs` and `/openapi.json` once the application is implemented.

## Rate Limits

* Authenticated: 100 requests/minute per user.
* Public health: 10 requests/minute per IP.

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
