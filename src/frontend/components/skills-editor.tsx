"use client";

import { useState } from "react";

import { apiDelete, apiPost, apiPut } from "@/lib/api";
import { useCandidate, useList } from "@/lib/hooks";
import { PROFICIENCIES, SKILL_CATEGORIES } from "@/lib/constants";
import type { SkillCreate, SkillRead } from "@/lib/types";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  Field,
  Input,
  Select,
  Spinner,
} from "@/components/ui";

type FormState = SkillCreate;

const BLANK: FormState = {
  name: "",
  category: "other",
  proficiency: "intermediate",
  years_experience: undefined,
  last_used_year: undefined,
  is_primary: false,
};

export function SkillsEditor() {
  const { candidate, loading: candidateLoading } = useCandidate();
  const candidateId = candidate?.id ?? null;
  const { items, loading, error, reload } = useList<SkillRead>(
    candidateId ? `/api/v1/candidates/${candidateId}/skills` : null,
  );

  const [form, setForm] = useState<FormState>(BLANK);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function startEdit(skill: SkillRead) {
    setEditingId(skill.id);
    setForm({
      name: skill.name,
      category: skill.category,
      proficiency: skill.proficiency,
      years_experience: skill.years_experience ?? undefined,
      last_used_year: skill.last_used_year ?? undefined,
      is_primary: skill.is_primary,
    });
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
      const payload: SkillCreate = {
        name: form.name.trim(),
        category: form.category,
        proficiency: form.proficiency,
        years_experience: form.years_experience,
        last_used_year: form.last_used_year,
        is_primary: form.is_primary,
      };
      if (editingId) {
        await apiPut(`/api/v1/candidates/${candidateId}/skills/${editingId}`, payload);
      } else {
        await apiPost(`/api/v1/candidates/${candidateId}/skills`, payload);
      }
      reset();
      await reload();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save skill");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(skill: SkillRead) {
    if (!candidateId) return;
    if (!window.confirm(`Delete skill "${skill.name}"?`)) return;
    await apiDelete(`/api/v1/candidates/${candidateId}/skills/${skill.id}`);
    await reload();
  }

  if (candidateLoading) return <Spinner />;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader title={editingId ? "Edit skill" : "Add skill"} />
        <CardBody>
          <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Name">
              <Input
                required
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                placeholder="e.g. Kubernetes"
              />
            </Field>
            <Field label="Category">
              <Select value={form.category} onChange={(e) => set("category", e.target.value as never)}>
                {SKILL_CATEGORIES.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Proficiency">
              <Select value={form.proficiency} onChange={(e) => set("proficiency", e.target.value as never)}>
                {PROFICIENCIES.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Years of experience">
              <Input
                type="number"
                min={0}
                value={form.years_experience ?? ""}
                onChange={(e) =>
                  set("years_experience", e.target.value === "" ? undefined : Number(e.target.value))
                }
              />
            </Field>
            <Field label="Last used (year)">
              <Input
                type="number"
                min={1990}
                max={2100}
                value={form.last_used_year ?? ""}
                onChange={(e) =>
                  set("last_used_year", e.target.value === "" ? undefined : Number(e.target.value))
                }
              />
            </Field>
            <label className="flex items-center gap-2 pt-6 text-sm font-medium text-zinc-700">
              <input
                type="checkbox"
                checked={form.is_primary}
                onChange={(e) => set("is_primary", e.target.checked)}
              />
              Primary skill
            </label>
            <div className="flex items-center gap-2 sm:col-span-2">
              <Button type="submit" loading={saving}>
                {editingId ? "Save changes" : "Add skill"}
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
        <EmptyState>No skills yet. Add your first skill above.</EmptyState>
      ) : (
        <Card>
          <CardHeader title={`Skills (${items.length})`} />
          <CardBody>
            <ul className="divide-y divide-zinc-100">
              {items.map((skill) => (
                <li key={skill.id} className="flex items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="truncate text-sm font-medium text-zinc-900">{skill.name}</p>
                      {skill.is_primary ? (
                        <span className="rounded bg-zinc-900 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
                          Primary
                        </span>
                      ) : null}
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-zinc-500">
                      <Badge value={skill.category} />
                      <Badge value={skill.proficiency} />
                      {skill.years_experience != null ? (
                        <span className="text-zinc-500">{skill.years_experience} yrs</span>
                      ) : null}
                      {skill.last_used_year != null ? (
                        <span className="text-zinc-500">last used {skill.last_used_year}</span>
                      ) : null}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Button type="button" variant="secondary" onClick={() => startEdit(skill)}>
                      Edit
                    </Button>
                    <Button type="button" variant="danger" onClick={() => void handleDelete(skill)}>
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