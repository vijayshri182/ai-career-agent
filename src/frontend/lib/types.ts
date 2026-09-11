/**
 * TypeScript contract mirroring the Phase 1 backend schemas
 * (src/backend/schemas) and enum models. Field order follows the backend.
 * Dates and datetimes are serialized by FastAPI as ISO-8601 strings.
 */

export type UUID = string;
export type ISODate = string; // YYYY-MM-DD
export type ISODateTime = string; // RFC 3339

/* ------------------------------------------------------------------ */
/* auth                                                                */
/* ------------------------------------------------------------------ */

export interface UserRegister {
  email: string;
  password: string;
}

export interface UserLogin {
  email: string;
  password: string;
}

export interface Token {
  access_token: string;
  token_type: string;
}

export interface UserRead {
  id: UUID;
  email: string;
  is_active: boolean;
}

/* ------------------------------------------------------------------ */
/* candidate profile enums                                             */
/* ------------------------------------------------------------------ */

export type ProfileStatus = "active" | "paused" | "deleted";
export type WorkMode = "remote" | "hybrid" | "onsite";
export type SkillCategory =
  | "programming"
  | "framework"
  | "cloud"
  | "devops"
  | "database"
  | "messaging"
  | "telecom"
  | "oss_bss"
  | "architecture"
  | "ai_genai"
  | "management"
  | "tools"
  | "other";
export type Proficiency = "beginner" | "intermediate" | "advanced" | "expert";

/* ------------------------------------------------------------------ */
/* candidate                                                           */
/* ------------------------------------------------------------------ */

export interface Compensation {
  amount?: number | null;
  currency?: string | null;
}

export interface CandidateCreate {
  full_name?: string | null;
  email?: string | null;
  phone?: string | null;
  headline?: string | null;
  summary?: string | null;
  current_role?: string | null;
  target_role?: string | null;
  total_experience_years?: number | null;
  current_location?: Record<string, unknown> | null;
  work_authorization?: string | null;
  work_mode_preference?: WorkMode | null;
  notice_period_days?: number | null;
  expected_compensation_amount?: number | null;
  expected_compensation_currency?: string | null;
  employment_type?: string | null;
  seniority?: string | null;
}

export interface CandidateUpdate {
  full_name?: string | null;
  email?: string | null;
  phone?: string | null;
  headline?: string | null;
  summary?: string | null;
  current_role?: string | null;
  target_role?: string | null;
  total_experience_years?: number | null;
  current_location?: Record<string, unknown> | null;
  work_authorization?: string | null;
  work_mode_preference?: WorkMode | null;
  notice_period_days?: number | null;
  expected_compensation_amount?: number | null;
  expected_compensation_currency?: string | null;
  employment_type?: string | null;
  seniority?: string | null;
  status?: ProfileStatus | null;
}

export interface CandidateRead {
  id: UUID;
  user_id: UUID;
  full_name: string | null;
  email: string | null;
  phone: string | null;
  headline: string | null;
  summary: string | null;
  current_role: string | null;
  target_role: string | null;
  total_experience_years: number | null;
  current_location: Record<string, unknown> | null;
  work_authorization: string | null;
  work_mode_preference: WorkMode | null;
  notice_period_days: number | null;
  expected_compensation_amount: number | null;
  expected_compensation_currency: string | null;
  employment_type: string | null;
  seniority: string | null;
  career_preferences: Record<string, unknown>;
  status: ProfileStatus;
}

export interface CareerPreferences {
  target_roles?: string[];
  target_industries?: string[];
  target_companies?: string[];
  excluded_companies?: string[];
  preferred_locations?: string[];
  work_mode?: WorkMode | null;
  min_compensation?: number | null;
  target_compensation?: number | null;
  max_compensation?: number | null;
  compensation_currency?: string | null;
  employment_type?: string | null;
  seniority?: string | null;
  travel_preference?: string | null;
  relocation_preference?: string | null;
  notice_period_days?: number | null;
}

/* ------------------------------------------------------------------ */
/* skills                                                              */
/* ------------------------------------------------------------------ */

export interface SkillCreate {
  name: string;
  category?: SkillCategory;
  proficiency?: Proficiency;
  years_experience?: number | null;
  last_used_year?: number | null;
  is_primary?: boolean;
}

export interface SkillUpdate {
  name?: string | null;
  category?: SkillCategory | null;
  proficiency?: Proficiency | null;
  years_experience?: number | null;
  last_used_year?: number | null;
  is_primary?: boolean | null;
}

export interface SkillRead {
  id: UUID;
  candidate_id: UUID;
  name: string;
  category: SkillCategory;
  proficiency: Proficiency;
  years_experience: number | null;
  last_used_year: number | null;
  is_primary: boolean;
}

/* ------------------------------------------------------------------ */
/* experience                                                          */
/* ------------------------------------------------------------------ */

export interface ExperienceCreate {
  company_name: string;
  title: string;
  location?: string | null;
  start_date: ISODate;
  end_date?: ISODate | null;
  is_current?: boolean;
  description?: string | null;
  responsibilities?: string[];
  achievements?: string[];
  technologies?: string[];
  domain?: string | null;
  leadership_responsibilities?: string[];
  team_size?: number | null;
  display_order?: number;
}

export interface ExperienceUpdate {
  company_name?: string | null;
  title?: string | null;
  location?: string | null;
  start_date?: ISODate | null;
  end_date?: ISODate | null;
  is_current?: boolean | null;
  description?: string | null;
  responsibilities?: string[] | null;
  achievements?: string[] | null;
  technologies?: string[] | null;
  domain?: string | null;
  leadership_responsibilities?: string[] | null;
  team_size?: number | null;
  display_order?: number | null;
}

export interface ExperienceRead {
  id: UUID;
  candidate_id: UUID;
  company_name: string;
  title: string;
  location: string | null;
  start_date: ISODate;
  end_date: ISODate | null;
  is_current: boolean;
  description: string | null;
  responsibilities: string[];
  achievements: string[];
  technologies: string[];
  domain: string | null;
  leadership_responsibilities: string[];
  team_size: number | null;
  display_order: number;
}

/* ------------------------------------------------------------------ */
/* education                                                           */
/* ------------------------------------------------------------------ */

export interface EducationCreate {
  institution: string;
  degree: string;
  field_of_study?: string | null;
  start_date?: ISODate | null;
  end_date?: ISODate | null;
  grade?: string | null;
  description?: string | null;
  display_order?: number;
}

export interface EducationUpdate {
  institution?: string | null;
  degree?: string | null;
  field_of_study?: string | null;
  start_date?: ISODate | null;
  end_date?: ISODate | null;
  grade?: string | null;
  description?: string | null;
  display_order?: number | null;
}

export interface EducationRead {
  id: UUID;
  candidate_id: UUID;
  institution: string;
  degree: string;
  field_of_study: string | null;
  start_date: ISODate | null;
  end_date: ISODate | null;
  grade: string | null;
  description: string | null;
  display_order: number;
}

/* ------------------------------------------------------------------ */
/* certifications                                                      */
/* ------------------------------------------------------------------ */

export interface CertificationCreate {
  name: string;
  issuing_organization?: string | null;
  issue_date?: ISODate | null;
  expiry_date?: ISODate | null;
  credential_id?: string | null;
  credential_url?: string | null;
  display_order?: number;
}

export interface CertificationUpdate {
  name?: string | null;
  issuing_organization?: string | null;
  issue_date?: ISODate | null;
  expiry_date?: ISODate | null;
  credential_id?: string | null;
  credential_url?: string | null;
  display_order?: number | null;
}

export interface CertificationRead {
  id: UUID;
  candidate_id: UUID;
  name: string;
  issuing_organization: string | null;
  issue_date: ISODate | null;
  expiry_date: ISODate | null;
  credential_id: string | null;
  credential_url: string | null;
  display_order: number;
}

/* ------------------------------------------------------------------ */
/* resumes                                                             */
/* ------------------------------------------------------------------ */

export type ResumeType = "general" | "targeted" | "custom";
export type ResumeStatus =
  | "draft"
  | "active"
  | "archived"
  | "ready"
  | "needs_attention";

export interface ResumeCreate {
  name: string;
  resume_type?: ResumeType;
  target_role?: string | null;
  is_default?: boolean;
}

export interface ResumeUpdate {
  name?: string | null;
  resume_type?: ResumeType | null;
  target_role?: string | null;
  is_default?: boolean | null;
  status?: ResumeStatus | null;
}

export interface ResumeVersionRead {
  id: UUID;
  resume_id: UUID;
  version_number: number;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  parsed_status: string;
  parsed_at: ISODateTime | null;
  created_at: ISODateTime;
}

export interface ResumeRead {
  id: UUID;
  candidate_id: UUID;
  name: string;
  resume_type: ResumeType;
  target_role: string | null;
  is_default: boolean;
  status: ResumeStatus;
  active_version_id: UUID | null;
  active_version: ResumeVersionRead | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface ParsedResumeRead {
  id: UUID;
  resume_version_id: UUID;
  extracted_data: Record<string, unknown>;
  status: string;
  confidence_score: number | null;
  created_at: ISODateTime;
}

/* ------------------------------------------------------------------ */
/* profile aggregation                                                 */
/* ------------------------------------------------------------------ */

export interface ProfileCompletenessItem {
  name: string;
  present: boolean;
  weight: number;
  score: number;
}

export interface ProfileCompleteness {
  total: number;
  maximum: number;
  percentage: number;
  items: ProfileCompletenessItem[];
}

export interface ProfileRead {
  candidate: CandidateRead;
  skills: SkillRead[];
  experiences: ExperienceRead[];
  educations: EducationRead[];
  certifications: CertificationRead[];
  resumes: ResumeRead[];
  completeness: ProfileCompleteness;
}

/* ------------------------------------------------------------------ */
/* authentication & challenge foundation                               */
/* ------------------------------------------------------------------ */

export type AuthenticationMethod =
  | "none"
  | "session"
  | "oauth"
  | "oidc"
  | "password"
  | "api_key"
  | "unknown";

export type AuthProviderType =
  | "ats"
  | "career_site"
  | "job_board"
  | "networking"
  | "email"
  | "other";

export type AuthState =
  | "not_required"
  | "not_configured"
  | "authenticated"
  | "session_expired"
  | "authentication_required"
  | "mfa_required"
  | "captcha_required"
  | "access_blocked"
  | "rate_limited"
  | "human_action_required"
  | "error";

export interface ProviderCreate {
  name: string;
  provider_type?: AuthProviderType;
  base_url?: string | null;
  authentication_method?: AuthenticationMethod;
  is_enabled?: boolean;
  notes?: string | null;
  metadata?: Record<string, unknown>;
}

export interface ProviderUpdate {
  name?: string | null;
  provider_type?: AuthProviderType | null;
  base_url?: string | null;
  authentication_method?: AuthenticationMethod | null;
  is_enabled?: boolean | null;
  notes?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface ProviderRead {
  id: UUID;
  candidate_id: UUID;
  name: string;
  provider_type: AuthProviderType;
  base_url: string | null;
  authentication_method: AuthenticationMethod;
  is_enabled: boolean;
  notes: string | null;
  metadata_json: Record<string, unknown>;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface ProviderStateRead {
  id: UUID;
  provider_id: UUID;
  status: AuthState;
  session_reference: string | null;
  checked_at: ISODateTime;
  authenticated_at: ISODateTime | null;
  state_metadata: Record<string, unknown>;
}

export interface AuthStateReport {
  status: AuthState;
  metadata?: Record<string, unknown>;
  session_reference?: string | null;
}

export interface ProviderOverviewRead {
  id: UUID;
  name: string;
  provider_type: string;
  authentication_method: string;
  is_enabled: boolean;
  auth_status: string;
  authenticated_at: ISODateTime | null;
  last_checked: ISODateTime;
  session_reference: string | null;
}

export type ChallengeType =
  | "captcha"
  | "mfa"
  | "otp"
  | "login_required"
  | "session_expired"
  | "bot_protection"
  | "access_denied"
  | "rate_limit"
  | "unknown_human_verification";

export type ChallengeStatus =
  | "open"
  | "acknowledged"
  | "human_action_required"
  | "resolved"
  | "cancelled"
  | "timed_out"
  | "failed";

export type ChallengeSeverity = "low" | "medium" | "high" | "critical";

export type ChallengeResolution =
  | "human"
  | "superseded"
  | "system"
  | "unresolved";

export interface ChallengeRead {
  id: UUID;
  candidate_id: UUID;
  provider_id: UUID;
  workflow_id: UUID | null;
  challenge_type: ChallengeType;
  status: ChallengeStatus;
  severity: ChallengeSeverity;
  human_required: boolean;
  description: string | null;
  context_metadata: Record<string, unknown>;
  detected_at: ISODateTime;
  acknowledged_at: ISODateTime | null;
  expires_at: ISODateTime | null;
  resolved_at: ISODateTime | null;
  cancelled_at: ISODateTime | null;
  timed_out_at: ISODateTime | null;
  resolution_method: ChallengeResolution | null;
  retry_count: number;
  max_retries: number;
}

export interface ChallengeSummaryRead {
  id: UUID;
  provider_id: UUID;
  challenge_type: ChallengeType;
  status: ChallengeStatus;
  severity: ChallengeSeverity;
  human_required: boolean;
  detected_at: ISODateTime;
  expires_at: ISODateTime | null;
}

export interface ChallengeCompleteInput {
  resolution_method?: ChallengeResolution;
  notes?: string | null;
}

export interface ChallengeCancelInput {
  reason?: string | null;
}

export interface AuthOverview {
  provider_count: number;
  open_challenge_count: number;
  providers: ProviderOverviewRead[];
  open_challenges: ChallengeSummaryRead[];
}

export type WorkflowStatus =
  | "running"
  | "paused_human_action"
  | "resumed"
  | "completed"
  | "cancelled"
  | "timed_out"
  | "failed";

export interface WorkflowRunRead {
  id: UUID;
  candidate_id: UUID;
  provider_id: UUID;
  workflow_type: string;
  status: WorkflowStatus;
  resume_token: UUID;
  attempt_count: number;
  max_attempts: number;
  context_metadata: Record<string, unknown>;
  started_at: ISODateTime;
  paused_at: ISODateTime | null;
  resumed_at: ISODateTime | null;
  finished_at: ISODateTime | null;
  expires_at: ISODateTime;
}

export type BrowserSessionStatus = "active" | "expired" | "closed" | "suspended" | "unknown";

export interface BrowserSessionCreate {
  provider_id: UUID;
  storage_reference?: string | null;
  external_session_id?: string | null;
}

export interface BrowserSessionRead {
  id: UUID;
  candidate_id: UUID;
  provider_id: UUID;
  status: BrowserSessionStatus;
  storage_reference: string | null;
  external_session_id: string | null;
  last_seen_at: ISODateTime | null;
  closed_at: ISODateTime | null;
  created_at: ISODateTime;
}

export type SecretType =
  | "password"
  | "api_key"
  | "oauth_token"
  | "refresh_token"
  | "session_cookie"
  | "mfa_shared_secret"
  | "unknown";

export type SecretStatus = "active" | "rotated" | "revoked" | "missing";

export interface SecretReferenceRegister {
  provider_id: UUID;
  secret_type: SecretType;
  external_reference: string;
  notes?: string | null;
}

export interface SecretReferenceRead {
  id: UUID;
  candidate_id: UUID;
  provider_id: UUID;
  secret_type: SecretType;
  external_reference: string;
  status: SecretStatus;
  rotated_at: ISODateTime | null;
  last_used_at: ISODateTime | null;
  notes: string | null;
  is_local_dev_placeholder: boolean;
  created_at: ISODateTime;
}