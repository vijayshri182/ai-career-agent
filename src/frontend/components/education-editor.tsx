"use client";

import { useState } from "react";

import { apiDelete, apiPost, apiPut } from "@/lib/api";
import { useCandidate, useList } from "@/lib/hooks";
import type { EducationCreate, EducationRead } from "@/lib/types";
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  Field,
  Input,
  Spinner,
  Textarea,
} from "@/components/ui";

interface FormState {
  institution: string;
  degree: string;
  field_of_study: string;
  start_date: string;
  end_date: string;
  grade: string;
  description: string;
  display_order: string;
}

const BLANK: FormState = {
  institution: "",
  degree: "",
  field_of_study: "",
  start_date: "",
  end_date: "",
  grade: "",
  description: "",
  display_order: "0",
};

function toForm(e: EducationRead): FormState {
  return {
    institution: e.institution,
    degree: e.degree,
    field_of_study: e.field_of_study ?? "",
    start_date: e.start_date ?? "",
    end_date: e.end_date ?? "",
    grade: e.grade ?? "",
    description: e.description ?? "",
    display_order: e.display_order.toString(),
  };
}

function toPayload(f: FormState): EducationCreate {
  return {
    institution: f.institution.trim(),
    degree: f.degree.trim(),
    field_of_study: f.field_of_study || null,
    start_date: f.start_date || null,
    end_date: f.end_date || null,
    grade: f.grade || null,
    description: f.description || null,
    display_order: f.display_order ? Number(f.display_order) : 0,
  };
}

export function EducationEditor() {
  const { candidate, loading: candidateLoading } = useCandidate();
  const candidateId = candidate?.id ?? null;
  const { items, loading, error, reload } = useList<EducationRead>(
    candidateId ? `/api/v1/candidates/${candidateId}/education` : null,
  );

  const [form, setForm] = useState<FormState>(BLANK);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function startEdit(item: EducationRead) {
    setEditingId(item.id);
    setForm(toForm(item));
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
        await apiPut(`/api/v1/candidates/${candidateId}/education/${editingId}`, payload);
      } else {
        await apiPost(`/api/v1/candidates/${candidateId}/education`, payload);
      }
      reset();
      await reload();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save education");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(item: EducationRead) {
    if (!candidateId) return;
    if (!window.confirm(`Delete ${item.degree} at ${item.institution}?`)) return;
    await apiDelete(`/api/v1/candidates/${candidateId}/education/${item.id}`);
    await reload();
  }

  if (candidateLoading) return <Spinner />;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader title={editingId ? "Edit education" : "Add education"} />
        <CardBody>
          <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Institution">
              <Input required value={form.institution} onChange={(e) => set("institution", e.target.value)} />
            </Field>
            <Field label="Degree">
              <Input required value={form.degree} onChange={(e) => set("degree", e.target.value)} />
            </Field>
            <Field label="Field of study">
              <Input value={form.field_of_study} onChange={(e) => set("field_of_study", e.target.value)} />
            </Field>
            <Field label="Grade">
              <Input value={form.grade} onChange={(e) => set("grade", e.target.value)} />
            </Field>
            <Field label="Start date">
              <Input type="date" value={form.start_date} onChange={(e) => set("start_date", e.target.value)} />
            </Field>
            <Field label="End date">
              <Input type="date" value={form.end_date} onChange={(e) => set("end_date", e.target.value)} />
            </Field>
            <div className="sm:col-span-2">
              <Field label="Description">
                <Textarea rows={3} value={form.description} onChange={(e) => set("description", e.target.value)} />
              </Field>
            </div>
            <div className="flex items-center gap-2">
              <Button type="submit" loading={saving}>
                {editingId ? "Save changes" : "Add education"}
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
        <EmptyState>No education entries yet.</EmptyState>
      ) : (
        <Card>
          <CardHeader title={`Education (${items.length})`} />
          <CardBody>
            <ul className="divide-y divide-zinc-100">
              {items.map((item) => (
                <li key={item.id} className="flex items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-zinc-900">
                      {item.degree}
                      {item.field_of_study ? (
                        <span className="font-normal text-zinc-500">, {item.field_of_study}</span>
                      ) : null}
                    </p>
                    <p className="mt-0.5 text-xs text-zinc-500">
                      {item.institution}
                      {item.start_date ? ` · ${item.start_date}${item.end_date ? ` – ${item.end_date}` : ""}` : ""}
                      {item.grade ? ` · ${item.grade}` : ""}
                    </p>
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