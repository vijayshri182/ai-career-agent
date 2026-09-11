"use client";

import { useState } from "react";

import { apiDelete, apiPost, apiPut } from "@/lib/api";
import { useCandidate, useList } from "@/lib/hooks";
import type { CertificationCreate, CertificationRead } from "@/lib/types";
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
} from "@/components/ui";

interface FormState {
  name: string;
  issuing_organization: string;
  issue_date: string;
  expiry_date: string;
  credential_id: string;
  credential_url: string;
  display_order: string;
}

const BLANK: FormState = {
  name: "",
  issuing_organization: "",
  issue_date: "",
  expiry_date: "",
  credential_id: "",
  credential_url: "",
  display_order: "0",
};

function toForm(c: CertificationRead): FormState {
  return {
    name: c.name,
    issuing_organization: c.issuing_organization ?? "",
    issue_date: c.issue_date ?? "",
    expiry_date: c.expiry_date ?? "",
    credential_id: c.credential_id ?? "",
    credential_url: c.credential_url ?? "",
    display_order: c.display_order.toString(),
  };
}

function toPayload(f: FormState): CertificationCreate {
  return {
    name: f.name.trim(),
    issuing_organization: f.issuing_organization || null,
    issue_date: f.issue_date || null,
    expiry_date: f.expiry_date || null,
    credential_id: f.credential_id || null,
    credential_url: f.credential_url || null,
    display_order: f.display_order ? Number(f.display_order) : 0,
  };
}

export function CertificationsEditor() {
  const { candidate, loading: candidateLoading } = useCandidate();
  const candidateId = candidate?.id ?? null;
  const { items, loading, error, reload } = useList<CertificationRead>(
    candidateId ? `/api/v1/candidates/${candidateId}/certifications` : null,
  );

  const [form, setForm] = useState<FormState>(BLANK);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function startEdit(item: CertificationRead) {
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
        await apiPut(`/api/v1/candidates/${candidateId}/certifications/${editingId}`, payload);
      } else {
        await apiPost(`/api/v1/candidates/${candidateId}/certifications`, payload);
      }
      reset();
      await reload();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save certification");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(item: CertificationRead) {
    if (!candidateId) return;
    if (!window.confirm(`Delete certification "${item.name}"?`)) return;
    await apiDelete(`/api/v1/candidates/${candidateId}/certifications/${item.id}`);
    await reload();
  }

  if (candidateLoading) return <Spinner />;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader title={editingId ? "Edit certification" : "Add certification"} />
        <CardBody>
          <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Name">
              <Input required value={form.name} onChange={(e) => set("name", e.target.value)} />
            </Field>
            <Field label="Issuing organization">
              <Input value={form.issuing_organization} onChange={(e) => set("issuing_organization", e.target.value)} />
            </Field>
            <Field label="Issue date">
              <Input type="date" value={form.issue_date} onChange={(e) => set("issue_date", e.target.value)} />
            </Field>
            <Field label="Expiry date">
              <Input type="date" value={form.expiry_date} onChange={(e) => set("expiry_date", e.target.value)} />
            </Field>
            <Field label="Credential ID">
              <Input value={form.credential_id} onChange={(e) => set("credential_id", e.target.value)} />
            </Field>
            <Field label="Credential URL">
              <Input type="url" value={form.credential_url} onChange={(e) => set("credential_url", e.target.value)} />
            </Field>
            <div className="flex items-center gap-2">
              <Button type="submit" loading={saving}>
                {editingId ? "Save changes" : "Add certification"}
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
        <EmptyState>No certifications yet.</EmptyState>
      ) : (
        <Card>
          <CardHeader title={`Certifications (${items.length})`} />
          <CardBody>
            <ul className="divide-y divide-zinc-100">
              {items.map((item) => (
                <li key={item.id} className="flex items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-zinc-900">{item.name}</p>
                    <p className="mt-0.5 text-xs text-zinc-500">
                      {item.issuing_organization ?? "—"}
                      {item.issue_date ? ` · ${item.issue_date}` : ""}
                      {item.credential_id ? ` · ${item.credential_id}` : ""}
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