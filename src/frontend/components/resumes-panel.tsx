"use client";

import { useState } from "react";

import { apiDelete, apiGet, apiPost, apiUpload } from "@/lib/api";
import { useCandidate, useList } from "@/lib/hooks";
import type {
  ParsedResumeRead,
  ResumeCreate,
  ResumeRead,
  ResumeVersionRead,
} from "@/lib/types";
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

const RESUME_TYPES = [
  { value: "general" as const, label: "General" },
  { value: "targeted" as const, label: "Targeted" },
  { value: "custom" as const, label: "Custom" },
];

interface NewResumeForm {
  name: string;
  resume_type: "general" | "targeted" | "custom";
  target_role: string;
  is_default: boolean;
}

const BLANK: NewResumeForm = {
  name: "",
  resume_type: "general",
  target_role: "",
  is_default: false,
};

export function ResumesPanel() {
  const { candidate, loading: candidateLoading } = useCandidate();
  const candidateId = candidate?.id ?? null;
  const { items, loading, error, reload } = useList<ResumeRead>(
    candidateId ? `/api/v1/candidates/${candidateId}/resumes` : null,
  );

  const [form, setForm] = useState<NewResumeForm>(BLANK);
  const [creating, setCreating] = useState(false);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadTarget, setUploadTarget] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [parsed, setParsed] = useState<Record<string, ParsedResumeRead>>({});
  const [parsingId, setParsingId] = useState<string | null>(null);

  function set<K extends keyof NewResumeForm>(key: K, value: NewResumeForm[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function errorOf(err: unknown): string {
    return err instanceof Error ? err.message : "Action failed";
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!candidateId) return;
    setCreating(true);
    setActionError(null);
    try {
      const payload: ResumeCreate = {
        name: form.name.trim(),
        resume_type: form.resume_type,
        target_role: form.target_role || null,
        is_default: form.is_default,
      };
      await apiPost<ResumeRead>(`/api/v1/candidates/${candidateId}/resumes`, payload);
      setForm(BLANK);
      await reload();
    } catch (err) {
      setActionError(errorOf(err));
    } finally {
      setCreating(false);
    }
  }

  async function handleUpload(resumeId: string | null, file: File) {
    if (!candidateId) return;
    setUploadBusy(true);
    setActionError(null);
    setUploadTarget(resumeId);
    try {
      const body = new FormData();
      body.append("file", file);
      if (resumeId) {
        await apiUpload<ResumeVersionRead>(
          `/api/v1/candidates/${candidateId}/resumes/${resumeId}/upload`,
          body,
        );
      } else {
        await apiUpload<ResumeVersionRead>(
          `/api/v1/candidates/${candidateId}/resumes/upload`,
          body,
        );
      }
      await reload();
    } catch (err) {
      setActionError(errorOf(err));
    } finally {
      setUploadBusy(false);
      setUploadTarget(null);
    }
  }

  async function handleParse(resume: ResumeRead) {
    if (!candidateId) return;
    setParsingId(resume.id);
    setActionError(null);
    try {
      const result = await apiPost<ParsedResumeRead>(
        `/api/v1/candidates/${candidateId}/resumes/${resume.id}/parse`,
      );
      setParsed((prev) => ({ ...prev, [resume.id]: result }));
    } catch (err) {
      setActionError(errorOf(err));
    } finally {
      setParsingId(null);
    }
  }

  async function handleLoadParsed(id: string) {
    if (!candidateId) return;
    try {
      const result = await apiGet<ParsedResumeRead>(
        `/api/v1/candidates/${candidateId}/resumes/${id}/parse`,
      );
      setParsed((prev) => ({ ...prev, [id]: result }));
    } catch (err) {
      setActionError(errorOf(err));
    }
  }

  async function handleApplyParsed(resume: ResumeRead) {
    if (!candidateId) return;
    if (
      !window.confirm(
        "Apply the parsed data to your candidate profile? Only fields that have not been applied before will be written.",
      )
    ) {
      return;
    }
    setActionError(null);
    try {
      const result = await apiPost<ParsedResumeRead>(
        `/api/v1/candidates/${candidateId}/resumes/${resume.id}/apply-parsed?confirm=true`,
      );
      setParsed((prev) => ({ ...prev, [resume.id]: result }));
    } catch (err) {
      setActionError(errorOf(err));
    }
  }

  async function handleDelete(resume: ResumeRead) {
    if (!candidateId) return;
    if (!window.confirm(`Delete resume "${resume.name}" and all its versions?`)) return;
    setActionError(null);
    try {
      await apiDelete(`/api/v1/candidates/${candidateId}/resumes/${resume.id}`);
      await reload();
    } catch (err) {
      setActionError(errorOf(err));
    }
  }

  if (candidateLoading) return <Spinner />;
  if (!candidate) {
    return <EmptyState>Create your candidate profile before uploading resumes.</EmptyState>;
  }

  return (
    <div className="space-y-6">
      {/* Quick upload + create */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Upload a resume" description="Creates a resume record with one uploaded version." />
          <CardBody>
            <label className="flex h-24 cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-zinc-300 text-sm text-zinc-500 transition-colors hover:border-zinc-400 hover:bg-zinc-50">
              {uploadBusy && uploadTarget === null ? (
                <span className="flex items-center gap-2">
                  <Spinner /> Uploading…
                </span>
              ) : (
                <>
                  <span className="font-medium text-zinc-700">Choose a file</span>
                  <span>PDF or DOCX</span>
                </>
              )}
              <input
                type="file"
                accept=".pdf,.docx"
                className="hidden"
                disabled={uploadBusy}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void handleUpload(null, file);
                  e.target.value = "";
                }}
              />
            </label>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Create a resume record" />
          <CardBody>
            <form onSubmit={handleCreate} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Name">
                <Input required value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Main resume" />
              </Field>
              <Field label="Type">
                <Select value={form.resume_type} onChange={(e) => set("resume_type", e.target.value as never)}>
                  {RESUME_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Target role">
                <Input value={form.target_role} onChange={(e) => set("target_role", e.target.value)} />
              </Field>
              <label className="flex items-center gap-2 pt-6 text-sm font-medium text-zinc-700">
                <input type="checkbox" checked={form.is_default} onChange={(e) => set("is_default", e.target.checked)} />
                Default resume
              </label>
              <div className="sm:col-span-2">
                <Button type="submit" loading={creating}>
                  Create resume record
                </Button>
              </div>
            </form>
          </CardBody>
        </Card>
      </div>

      {actionError ? <Alert tone="error">{actionError}</Alert> : null}

      {loading ? (
        <div className="flex justify-center py-10">
          <Spinner />
        </div>
      ) : error ? (
        <Alert tone="error">{error}</Alert>
      ) : items.length === 0 ? (
        <EmptyState>No resumes yet. Upload or create one above.</EmptyState>
      ) : (
        <div className="space-y-4">
          {items.map((resume) => {
            const parsedForThis = parsed[resume.id];
            return (
              <Card key={resume.id}>
                <CardHeader
                  title={
                    <span className="flex flex-wrap items-center gap-2">
                      {resume.name}
                      <Badge value={resume.resume_type} />
                      <Badge value={resume.status} />
                      {resume.is_default ? (
                        <span className="rounded bg-zinc-900 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
                          Default
                        </span>
                      ) : null}
                    </span>
                  }
                  description={
                    resume.target_role ? `Target role: ${resume.target_role}` : undefined
                  }
                  action={
                    <div className="flex items-center gap-2">
                      <Button
                        type="button"
                        variant="danger"
                        onClick={() => void handleDelete(resume)}
                      >
                        Delete
                      </Button>
                    </div>
                  }
                />
                <CardBody>
                  <div className="space-y-4">
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <input
                        type="file"
                        accept=".pdf,.docx"
                        disabled={uploadBusy}
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) void handleUpload(resume.id, file);
                          e.target.value = "";
                        }}
                        className="block w-full max-w-sm text-sm text-zinc-500 file:mr-3 file:rounded-md file:border-0 file:bg-zinc-100 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-zinc-700 hover:file:bg-zinc-200"
                      />
                      <Button
                        type="button"
                        variant="secondary"
                        loading={parsingId === resume.id}
                        onClick={() => void handleParse(resume)}
                      >
                        Parse
                      </Button>
                      <Button type="button" variant="secondary" onClick={() => void handleLoadParsed(resume.id)}>
                        View parsed
                      </Button>
                      {parsedForThis ? (
                        <Button
                          type="button"
                          onClick={() => void handleApplyParsed(resume)}
                        >
                          Apply to profile
                        </Button>
                      ) : null}
                    </div>

                    {resume.active_version ? (
                      <p className="text-xs text-zinc-500">
                        Active version v{resume.active_version.version_number} —{" "}
                        {resume.active_version.original_filename} ({resume.active_version.content_type},{" "}
                        {formatBytes(resume.active_version.size_bytes)}).
                      </p>
                    ) : (
                      <p className="text-xs text-zinc-400">No uploaded version yet.</p>
                    )}

                    {parsedForThis ? (
                      <div>
                        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-400">
                          Parsed status: <span className="capitalize">{parsedForThis.status}</span>
                          {parsedForThis.confidence_score != null
                            ? ` · confidence ${parsedForThis.confidence_score}%`
                            : ""}
                        </p>
                        <pre className="max-h-64 overflow-auto rounded-md bg-zinc-900 p-3 text-xs text-zinc-100">
                          {JSON.stringify(parsedForThis.extracted_data, null, 2)}
                        </pre>
                      </div>
                    ) : null}
                  </div>
                </CardBody>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}