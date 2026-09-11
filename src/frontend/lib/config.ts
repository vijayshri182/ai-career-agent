/**
 * Backend base URL (server-side). Defaults to the local FastAPI dev server.
 * Override with `API_BASE_URL` in `.env.local`.
 */

export const API_BASE = process.env.API_BASE_URL ?? "http://localhost:8000";