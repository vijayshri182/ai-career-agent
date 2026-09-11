"use client";

import { useState } from "react";

import { apiDelete, apiPost, apiPut } from "@/lib/api";
import { useCandidate, useList } from "@/lib/hooks";
import type { ExperienceCreate, ExperienceRead } from "@/lib/types";
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  Field,
  Input,
  Label,
  Spinner,
  Textarea,
  Badge,
} from "@/components/ui";

interface FormState {
  company_name: string;
  title: string;
  location: string;
  start_date: string;
  end_date: string;
  is_current: boolean;
  description: string;
  responsibilities: string;
  achievements: string;
  technologies: string;
  domain: string;
  leadership_responsibilities: string;
  team_size: string;
  display_order: string;
}

const BLANK: FormState = {
  company_name: "",
  title: "",
  location: "",
  start_date: "",
  end_date: "",
  is_current: false,
  description: "",
  responsibilities: "",
  achievements: "",
  technologies: "",
  domain: "",
  leadership_responsibilities: "",
  team_size: "",
  display_order: "0",
};

function toForm(e: ExperienceRead): FormState {
  return {
    company_name: e.company_name,
    title: e.title,
    location: e.location ?? "",
    start_date: e.start_date,
    end_date: e.end_date ?? "",
    is_current: e.is_current,
    description: e.description ?? "",
    responsibilities: e.responsibilities.join("\n"),
    achievements: e.achievements.join("\n"),
    technologies: e.technologies.join("\n"),
    domain: e.domain ?? "",
    leadership_responsibilities: e.leadership_responsibilities.join("\n"),
    team_size: e.team_size?.toString() ?? "",
    display_order: e.display_order.toString(),
  };
}

function toPayload(f: FormState): ExperienceCreate {
  return {
    company_name: f.company_name.trim(),
    title: f.title.trim(),
    location: f.location || null,
    start_date: f.start_date,
    end_date: f.is_current ? null : f.end_date || null,
    is_current: f.is_current,
    description: f.description || null,
    responsibilities: lines(f.responsibilities),
    achievements: lines(f.achievements),
    technologies: lines(f.technologies),
    domain: f.domain || null,
    leadership_responsibilities: lines(f.leadership_responsibilities),
    team_size: f.team_size ? Number(f.team_size) : null,
    display_order: f.display_order ? Number(f.display_order) : 0,
  };
}

function lines(value: string): string[] {
  return value
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
}

export function ExperienceEditor() {
  const { candidate, loading: candidateLoading } = useCandidate();
  const candidateId = candidate?.id ?? null;
  const { items, loading, error, reload } = useList<ExperienceRead>(
    candidateId ? `/api/v1/candidates/${candidateId}/experience` : null,
  );

  const [form, setForm] = useState<FormState>(BLANK);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function startEdit(item: ExperienceRead) {
    setEditingId(item.id);
    const f = toForm(item);
    if (item.is_current) f.end_date = "";
    setForm(f);
  }

  function reset() {
    setEditingId(null);
    setForm(BLANK);
    setSaveError(null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!candidateId) return;
    setSaving(true);
    setSaveError(null);
    try {
      const payload = toPayload(form);
      if (editingId) {
        await apiPut(`/api/v1/candidates/${candidateId}/experience/${editingId}`, payload);
      } else {
        await apiPost(`/api/v1/candidates/${candidateId}/experience`, payload);
      }
      reset();
      await reload();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save experience");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(item: ExperienceRead) {
    if (!candidateId) return;
    if (!window.confirm(`Delete ${item.title} at ${item.company_name}?`)) return;
    await apiDelete(`/api/v1/candidates/${candidateId}/experience/${item.id}`);
    await reload();
  }

  if (candidateLoading) return <Spinner />;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader title={editingId ? "Edit experience" : "Add experience"} />
        <CardBody>
          <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Company">
              <Input required value={form.company_name} onChange={(e) => set("company_name", e.target.value)} />
            </Field>
            <Field label="Title">
              <Input required value={form.title} onChange={(e) => set("title", e.target.value)} />
            </Field>
            <Field label="Location">
              <Input value={form.location} onChange={(e) => set("location", e.target.value)} />
            </Field>
            <Field label="Domain">
              <Input value={form.domain} onChange={(e) => set("domain", e.target.value)} placeholder="e.g. OSS/BSS" />
            </Field>
            <Field label="Start date">
              <Input type="date" required value={form.start_date} onChange={(e) => set("start_date", e.target.value)} />
            </Field>
            <div>
              <Label>End date</Label>
              <Input type="date" disabled={form.is_current} value={form.end_date} onChange={(e) => set("end_date", e.target.value)} />
            </div>
            <label className="flex items-center gap-2 pt-6 text-sm font-medium text-zinc-700">
              <input type="checkbox" checked={form.is_current} onChange={(e) => set("is_current", e.target.checked)} />
              Current role
            </label>
            <div className="sm:col-span-2">
              <Field label="Team size">
                <Input
                  type="number"
                  min={0}
                  value={form.team_size}
                  onChange={(e) => set("team_size", e.target.value)}
                />
              </Field>
            </div>
            <div className="sm:col-span-2">
              <Field label="Description">
                <Textarea rows={3} value={form.description} onChange={(e) => set("description", e.target.value)} />
              </Field>
            </div>
            <div className="sm:col-span-2">
              <Field label="Responsibilities (one per line)">
                <Textarea rows={4} value={form.responsibilities} onChange={(e) => set("responsibilities", e.target.value)} />
              </Field>
            </div>
            <div className="sm:col-span-2">
              <Field label="Achievements (one per line)">
                <Textarea rows={3} value={form.achievements} onChange={(e) => set("achievements", e.target.value)} />
              </Field>
            </div>
            <div className="sm:col-span-2">
              <Field label="Technologies (one per line)">
                <Textarea rows={3} value={form.technologies} onChange={(e) => set("technologies", e.target.value)} />
              </Field>
            </div>
            <div className="sm:col-span-2">
              <Field label="Leadership responsibilities (one per line)">
                <Textarea
                  rows={3}
                  value={form.leadership_responsibilities}
                  onChange={(e) => set("leadership_responsibilities", e.target.value)}
                />
              </Field>
            </div>
            <div className="flex items-center gap-2 sm:col-span-2">
              <Button type="submit" loading={saving}>
                {editingId ? "Save changes" : "Add experience"}
              </Button>
              {editingId ? (
                <Button type="button" variant="secondary" onClick={reset}>
                  Cancel
                </Button>
              ) : null}
            </div>
          </form>
          {saveError ? (
            <Alert tone="error" className="mt-4">
              {saveError}
            </Alert>
          ) : null}
        </CardBody>
      </Card>

      {loading ? (
        <div className="flex justify-center py-10">
          <Spinner />
        </div>
      ) : error ? (
        <Alert tone="error">{error}</Alert>
      ) : items.length === 0 ? (
        <EmptyState>No experience yet. Add your first role above.</EmptyState>
      ) : (
        <Card>
          <CardHeader title={`Experience (${items.length})`} />
          <CardBody>
            <ul className="divide-y divide-zinc-100">
              {items.map((item) => (
                <li key={item.id} className="flex items-start justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-zinc-900">
                      {item.title} <span className="font-normal text-zinc-500">at {item.company_name}</span>
                    </p>
                    <p className="mt-0.5 text-xs text-zinc-500">
                      {item.start_date}
                      {item.is_current ? " – present" : item.end_date ? ` – ${item.end_date}` : ""}
                      {item.location ? ` · ${item.location}` : ""}
                    </p>
                    {item.technologies.length > 0 ? (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {item.technologies.map((tech) => (
                          <Badge key={tech} value={tech} />
                        ))}
                      </div>
                    ) : null}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Button type="button" variant="secondary" onClick={() => startEdit(item)}>
                      Edit
                    </Button>
                    <Button type="button" variant="danger" onClick={() => void handleDelete(item)}>
                      Delete
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      )}
    </div>
  );
}