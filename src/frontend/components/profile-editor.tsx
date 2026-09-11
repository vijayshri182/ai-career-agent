"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { apiPost, apiPut } from "@/lib/api";
import { useCandidate } from "@/lib/hooks";
import { WORK_MODES } from "@/lib/constants";
import type { CandidateCreate, CandidateRead, CandidateUpdate } from "@/lib/types";
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  Field,
  Input,
  Select,
  Spinner,
  Textarea,
} from "@/components/ui";

interface FormState extends CandidateCreate {
  current_location_raw: string;
}

function empty(): FormState {
  return {
    current_location_raw: "",
  };
}

function fromCandidate(c: CandidateRead): FormState {
  return {
    full_name: c.full_name ?? "",
    email: c.email ?? "",
    phone: c.phone ?? "",
    headline: c.headline ?? "",
    summary: c.summary ?? "",
    current_role: c.current_role ?? "",
    target_role: c.target_role ?? "",
    total_experience_years: c.total_experience_years ?? undefined,
    work_authorization: c.work_authorization ?? "",
    work_mode_preference: c.work_mode_preference ?? undefined,
    notice_period_days: c.notice_period_days ?? undefined,
    expected_compensation_amount: c.expected_compensation_amount ?? undefined,
    expected_compensation_currency: c.expected_compensation_currency ?? "",
    employment_type: c.employment_type ?? "",
    seniority: c.seniority ?? "",
    current_location_raw: c.current_location ? JSON.stringify(c.current_location) : "",
  };
}

export function ProfileEditor() {
  const router = useRouter();
  const { candidate, loading, error, refresh } = useCandidate();
  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // Reset the form once the candidate finishes loading (derived-state reset).
  if (!loading && form === null) {
    setForm(candidate ? fromCandidate(candidate) : empty());
  }

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form) return;
    setSaving(true);
    setSaveError(null);
    setSaved(false);
    try {
      const payload: CandidateUpdate | CandidateCreate = {
        full_name: form.full_name || null,
        email: form.email || null,
        phone: form.phone || null,
        headline: form.headline || null,
        summary: form.summary || null,
        current_role: form.current_role || null,
        target_role: form.target_role || null,
        total_experience_years: form.total_experience_years || null,
        current_location: parseLocation(form.current_location_raw),
        work_authorization: form.work_authorization || null,
        work_mode_preference: form.work_mode_preference ?? null,
        notice_period_days: form.notice_period_days || null,
        expected_compensation_amount: form.expected_compensation_amount || null,
        expected_compensation_currency: form.expected_compensation_currency || null,
        employment_type: form.employment_type || null,
        seniority: form.seniority || null,
      };
      if (candidate) {
        await apiPut<CandidateRead>(`/api/v1/candidates/${candidate.id}`, payload);
      } else {
        await apiPost<CandidateRead>("/api/v1/candidates", payload);
        router.push("/dashboard");
        router.refresh();
      }
      await refresh();
      setSaved(true);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save profile");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    );
  }

  if (error) {
    return (
      <Alert tone="error" title="Could not load profile">
        {error}
      </Alert>
    );
  }

  if (!form) return null;

  return (
    <div className="space-y-6">
      {saveError ? (
        <Alert tone="error" title="Failed to save" className="mb-4">
          {saveError}
        </Alert>
      ) : null}
      {saved ? <Alert tone="success">Profile saved.</Alert> : null}
      <form onSubmit={handleSubmit}>
        <Card>
          <CardHeader title="Basic information" />
          <CardBody className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Full name">
              <Input value={form.full_name ?? ""} onChange={(e) => set("full_name", e.target.value)} />
            </Field>
            <Field label="Email">
              <Input type="email" value={form.email ?? ""} onChange={(e) => set("email", e.target.value)} />
            </Field>
            <Field label="Phone">
              <Input value={form.phone ?? ""} onChange={(e) => set("phone", e.target.value)} />
            </Field>
            <Field label="Location (JSON)">
              <Input
                value={form.current_location_raw}
                onChange={(e) => set("current_location_raw", e.target.value)}
                placeholder='{"city":"Bengaluru","country":"India"}'
              />
            </Field>
            <Field label="Headline">
              <Input value={form.headline ?? ""} onChange={(e) => set("headline", e.target.value)} />
            </Field>
            <Field label="Work authorization">
              <Input
                value={form.work_authorization ?? ""}
                onChange={(e) => set("work_authorization", e.target.value)}
              />
            </Field>
            <Field label="Current role">
              <Input value={form.current_role ?? ""} onChange={(e) => set("current_role", e.target.value)} />
            </Field>
            <Field label="Target role">
              <Input value={form.target_role ?? ""} onChange={(e) => set("target_role", e.target.value)} />
            </Field>
            <Field label="Total experience (years)">
              <Input
                type="number"
                min={0}
                value={form.total_experience_years ?? ""}
                onChange={(e) =>
                  set("total_experience_years", e.target.value === "" ? undefined : Number(e.target.value))
                }
              />
            </Field>
            <Field label="Work mode preference">
              <Select
                value={form.work_mode_preference ?? ""}
                onChange={(e) =>
                  set("work_mode_preference", e.target.value === "" ? undefined : (e.target.value as never))
                }
              >
                <option value="">Not specified</option>
                {WORK_MODES.map((w) => (
                  <option key={w.value} value={w.value}>
                    {w.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Notice period (days)">
              <Input
                type="number"
                min={0}
                value={form.notice_period_days ?? ""}
                onChange={(e) =>
                  set("notice_period_days", e.target.value === "" ? undefined : Number(e.target.value))
                }
              />
            </Field>
            <Field label="Expected compensation (amount)">
              <Input
                type="number"
                min={0}
                value={form.expected_compensation_amount ?? ""}
                onChange={(e) =>
                  set(
                    "expected_compensation_amount",
                    e.target.value === "" ? undefined : Number(e.target.value),
                  )
                }
              />
            </Field>
            <Field label="Expected compensation (currency)">
              <Input
                value={form.expected_compensation_currency ?? ""}
                onChange={(e) => set("expected_compensation_currency", e.target.value)}
                placeholder="USD"
              />
            </Field>
            <Field label="Employment type">
              <Input value={form.employment_type ?? ""} onChange={(e) => set("employment_type", e.target.value)} />
            </Field>
            <Field label="Seniority">
              <Input value={form.seniority ?? ""} onChange={(e) => set("seniority", e.target.value)} />
            </Field>
          </CardBody>
        </Card>

        <Card className="mt-6">
          <CardHeader title="Summary" />
          <CardBody>
            <Textarea
              rows={5}
              value={form.summary ?? ""}
              onChange={(e) => set("summary", e.target.value)}
              placeholder="A short professional summary..."
            />
          </CardBody>
        </Card>

        <div className="mt-6 flex items-center gap-3">
          <Button type="submit" loading={saving}>
            {candidate ? "Save changes" : "Create profile"}
          </Button>
          {form.current_location_raw && !parseLocation(form.current_location_raw) ? (
            <span className="text-sm text-amber-600">Location is not valid JSON and will be cleared.</span>
          ) : null}
        </div>
      </form>
      {!candidate ? (
        <EmptyState>
          You do not have a candidate profile yet. Fill in the form and press{" "}
          <span className="font-medium text-zinc-700">Create profile</span> to begin.
        </EmptyState>
      ) : null}
    </div>
  );
}

function parseLocation(raw: string): Record<string, unknown> | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  try {
    const parsed = JSON.parse(trimmed) as unknown;
    if (typeof parsed === "object" && parsed !== null) return parsed as Record<string, unknown>;
    return null;
  } catch {
    return null;
  }
}