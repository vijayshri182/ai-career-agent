/* ------------------------------------------------------------------ */
/* enums as labelled options (value matches backend lowercase enum)    */
/* ------------------------------------------------------------------ */

export const WORK_MODES = [
  { value: "remote" as const, label: "Remote" },
  { value: "hybrid" as const, label: "Hybrid" },
  { value: "onsite" as const, label: "On-site" },
];

export const SKILL_CATEGORIES = [
  { value: "programming" as const, label: "Programming" },
  { value: "framework" as const, label: "Framework" },
  { value: "cloud" as const, label: "Cloud" },
  { value: "devops" as const, label: "DevOps" },
  { value: "database" as const, label: "Database" },
  { value: "messaging" as const, label: "Messaging" },
  { value: "telecom" as const, label: "Telecom" },
  { value: "oss_bss" as const, label: "OSS/BSS" },
  { value: "architecture" as const, label: "Architecture" },
  { value: "ai_genai" as const, label: "AI/GenAI" },
  { value: "management" as const, label: "Management" },
  { value: "tools" as const, label: "Tools" },
  { value: "other" as const, label: "Other" },
];

export const PROFICIENCIES = [
  { value: "beginner" as const, label: "Beginner" },
  { value: "intermediate" as const, label: "Intermediate" },
  { value: "advanced" as const, label: "Advanced" },
  { value: "expert" as const, label: "Expert" },
];

export const AUTH_METHODS = [
  { value: "none" as const, label: "None" },
  { value: "session" as const, label: "Session" },
  { value: "oauth" as const, label: "OAuth" },
  { value: "oidc" as const, label: "OpenID Connect" },
  { value: "password" as const, label: "Password" },
  { value: "api_key" as const, label: "API Key" },
  { value: "unknown" as const, label: "Unknown" },
];

export const AUTH_PROVIDER_TYPES = [
  { value: "ats" as const, label: "ATS" },
  { value: "career_site" as const, label: "Career Site" },
  { value: "job_board" as const, label: "Job Board" },
  { value: "networking" as const, label: "Networking" },
  { value: "email" as const, label: "Email" },
  { value: "other" as const, label: "Other" },
];

export const AUTH_STATES = [
  { value: "not_required" as const, label: "Not Required" },
  { value: "not_configured" as const, label: "Not Configured" },
  { value: "authenticated" as const, label: "Authenticated" },
  { value: "session_expired" as const, label: "Session Expired" },
  { value: "authentication_required" as const, label: "Authentication Required" },
  { value: "mfa_required" as const, label: "MFA Required" },
  { value: "captcha_required" as const, label: "CAPTCHA Required" },
  { value: "access_blocked" as const, label: "Access Blocked" },
  { value: "rate_limited" as const, label: "Rate Limited" },
  { value: "human_action_required" as const, label: "Human Action Required" },
  { value: "error" as const, label: "Error" },
];

export const CHALLENGE_TYPES = [
  { value: "captcha" as const, label: "CAPTCHA" },
  { value: "mfa" as const, label: "MFA" },
  { value: "otp" as const, label: "OTP" },
  { value: "login_required" as const, label: "Login Required" },
  { value: "session_expired" as const, label: "Session Expired" },
  { value: "bot_protection" as const, label: "Bot Protection" },
  { value: "access_denied" as const, label: "Access Denied" },
  { value: "rate_limit" as const, label: "Rate Limit" },
  {
    value: "unknown_human_verification" as const,
    label: "Unknown Human Verification",
  },
];

export const CHALLENGE_STATUSES = [
  { value: "open" as const, label: "Open" },
  { value: "acknowledged" as const, label: "Acknowledged" },
  { value: "human_action_required" as const, label: "Human Action Required" },
  { value: "resolved" as const, label: "Resolved" },
  { value: "cancelled" as const, label: "Cancelled" },
  { value: "timed_out" as const, label: "Timed Out" },
  { value: "failed" as const, label: "Failed" },
];

export const SECRET_TYPES = [
  { value: "password" as const, label: "Password" },
  { value: "api_key" as const, label: "API Key" },
  { value: "oauth_token" as const, label: "OAuth Token" },
  { value: "refresh_token" as const, label: "Refresh Token" },
  { value: "session_cookie" as const, label: "Session Cookie" },
  { value: "mfa_shared_secret" as const, label: "MFA Shared Secret" },
  { value: "unknown" as const, label: "Unknown" },
];

export const STATUS_COLORS: Record<string, string> = {
  // auth states
  authenticated: "bg-green-100 text-green-800",
  not_configured: "bg-gray-100 text-gray-700",
  not_required: "bg-gray-100 text-gray-500",
  session_expired: "bg-amber-100 text-amber-800",
  authentication_required: "bg-amber-100 text-amber-800",
  mfa_required: "bg-orange-100 text-orange-800",
  captcha_required: "bg-orange-100 text-orange-800",
  access_blocked: "bg-red-100 text-red-800",
  rate_limited: "bg-yellow-100 text-yellow-800",
  human_action_required: "bg-red-100 text-red-800",
  error: "bg-red-100 text-red-700",
  // challenge statuses
  open: "bg-blue-100 text-blue-800",
  acknowledged: "bg-indigo-100 text-indigo-800",
  resolved: "bg-green-100 text-green-800",
  cancelled: "bg-gray-100 text-gray-600",
  timed_out: "bg-amber-100 text-amber-700",
  failed: "bg-red-100 text-red-700",
  // challenge severity
  low: "bg-gray-100 text-gray-600",
  medium: "bg-yellow-100 text-yellow-800",
  high: "bg-orange-100 text-orange-800",
  critical: "bg-red-100 text-red-800",
};
