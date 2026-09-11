"use client";

import { useState } from "react";

import { apiPut } from "@/lib/api";
import { useCandidate } from "@/lib/hooks";
import { WORK_MODES } from "@/lib/constants";
import type { CareerPreferences, CandidateRead } from "@/lib/types";
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

interface FormState {
  target_roles: string;
  target_industries: string;
  target_companies: string;
  excluded_companies: string;
  preferred_locations: string;
  work_mode: "" | NonNullable<CareerPreferences["work_mode"]>;
  min_compensation: string;
  target_compensation: string;
  max_compensation: string;
  compensation_currency: string;
  employment_type: string;
  seniority: string;
  travel_preference: string;
  relocation_preference: string;
  notice_period_days: string;
}

function fromRead(c: CareerPreferences): FormState {
  return {
    target_roles: (c.target_roles ?? []).join("\n"),
    target_industries: (c.target_industries ?? []).join("\n"),
    target_companies: (c.target_companies ?? []).join("\n"),
    excluded_companies: (c.excluded_companies ?? []).join("\n"),
    preferred_locations: (c.preferred_locations ?? []).join("\n"),
    work_mode: c.work_mode ?? "",
    min_compensation: c.min_compensation?.toString() ?? "",
    target_compensation: c.target_compensation?.toString() ?? "",
    max_compensation: c.max_compensation?.toString() ?? "",
    compensation_currency: c.compensation_currency ?? "",
    employment_type: c.employment_type ?? "",
    seniority: c.seniority ?? "",
    travel_preference: c.travel_preference ?? "",
    relocation_preference: c.relocation_preference ?? "",
    notice_period_days: c.notice_period_days?.toString() ?? "",
  };
}

function toPayload(f: FormState): CareerPreferences {
  return {
    target_roles: lines(f.target_roles),
    target_industries: lines(f.target_industries),
    target_companies: lines(f.target_companies),
    excluded_companies: lines(f.excluded_companies),
    preferred_locations: lines(f.preferred_locations),
    work_mode: f.work_mode === "" ? null : f.work_mode,
    min_compensation: num(f.min_compensation),
    target_compensation: num(f.target_compensation),
    max_compensation: num(f.max_compensation),
    compensation_currency: f.compensation_currency || null,
    employment_type: f.employment_type || null,
    seniority: f.seniority || null,
    travel_preference: f.travel_preference || null,
    relocation_preference: f.relocation_preference || null,
    notice_period_days: num(f.notice_period_days),
  };
}

function lines(value: string): string[] {
  return value
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
}

function num(value: string): number | null {
  return value === "" ? null : Number(value);
}

export function PreferencesForm() {
  const { candidate, loading, error, refresh } = useCandidate();
  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // Reset the form once the candidate finishes loading (derived-state reset).
  if (!loading && form === null) {
    const prefs = candidate ? (candidate.career_preferences as CareerPreferences) : {};
    setForm(fromRead(prefs));
  }

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!candidate || !form) return;
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await apiPut<CandidateRead>(
        `/api/v1/candidates/${candidate.id}/preferences`,
        toPayload(form),
      );
      setForm(fromRead(updated.career_preferences as CareerPreferences));
      await refresh();
      setSaved(true);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save preferences");
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
    return <Alert tone="error">{error}</Alert>;
  }
  if (!candidate) {
    return <EmptyState>Create your profile before setting preferences.</EmptyState>;
  }
  if (!form) return null;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title="Career preferences"
          description="Used later as inputs to matching. All fields are optional."
        />
        <CardBody>
          <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
            <Field label="Target roles (one per line)">
              <Textarea rows={3} value={form.target_roles} onChange={(e) => set("target_roles", e.target.value)} />
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Field label="Target industries (one per line)">
              <Textarea rows={3} value={form.target_industries} onChange={(e) => set("target_industries", e.target.value)} />
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Field label="Target companies (one per line)">
              <Textarea rows={3} value={form.target_companies} onChange={(e) => set("target_companies", e.target.value)} />
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Field label="Excluded companies (one per line)">
              <Textarea rows={2} value={form.excluded_companies} onChange={(e) => set("excluded_companies", e.target.value)} />
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Field label="Preferred locations (one per line)">
              <Textarea rows={3} value={form.preferred_locations} onChange={(e) => set("preferred_locations", e.target.value)} />
            </Field>
          </div>
          <Field label="Work mode">
            <Select value={form.work_mode} onChange={(e) => set("work_mode", e.target.value as never)}>
              <option value="">Not specified</option>
              {WORK_MODES.map((w) => (
                <option key={w.value} value={w.value}>
                  {w.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Compensation currency">
            <Input value={form.compensation_currency} onChange={(e) => set("compensation_currency", e.target.value)} placeholder="USD" />
          </Field>
          <Field label="Minimum compensation">
            <Input type="number" min={0} value={form.min_compensation} onChange={(e) => set("min_compensation", e.target.value)} />
          </Field>
          <Field label="Target compensation">
            <Input type="number" min={0} value={form.target_compensation} onChange={(e) => set("target_compensation", e.target.value)} />
          </Field>
          <Field label="Maximum compensation">
            <Input type="number" min={0} value={form.max_compensation} onChange={(e) => set("max_compensation", e.target.value)} />
          </Field>
          <Field label="Employment type">
            <Input value={form.employment_type} onChange={(e) => set("employment_type", e.target.value)} placeholder="Full-time" />
          </Field>
          <Field label="Seniority">
            <Input value={form.seniority} onChange={(e) => set("seniority", e.target.value)} placeholder="Principal/Director" />
          </Field>
          <Field label="Travel preference">
            <Input value={form.travel_preference} onChange={(e) => set("travel_preference", e.target.value)} />
          </Field>
          <Field label="Relocation preference">
            <Input value={form.relocation_preference} onChange={(e) => set("relocation_preference", e.target.value)} />
          </Field>
          <Field label="Notice period (days)">
            <Input type="number" min={0} value={form.notice_period_days} onChange={(e) => set("notice_period_days", e.target.value)} />
          </Field>
          <div className="flex items-center gap-3 sm:col-span-2">
            <Button type="submit" loading={saving}>
              Save preferences
            </Button>
            {saved ? <span className="text-sm text-green-700">Saved.</span> : null}
          </div>
          </form>
        </CardBody>
      </Card>
      {saveError ? <Alert tone="error">{saveError}</Alert> : null}
    </div>
  );
}