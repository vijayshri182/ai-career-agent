"use client";

import { useState } from "react";

import { apiDelete, apiGet, apiPost } from "@/lib/api";
import { useCandidate, useList } from "@/lib/hooks";
import {
  AUTH_METHODS,
  AUTH_PROVIDER_TYPES,
  AUTH_STATES,
  CHALLENGE_TYPES,
  SECRET_TYPES,
} from "@/lib/constants";
import type {
  AuthOverview,
  AuthState,
  AuthStateReport,
  BrowserSessionCreate,
  BrowserSessionRead,
  ChallengeCancelInput,
  ChallengeCompleteInput,
  ChallengeRead,
  ProviderCreate,
  ProviderRead,
  ProviderStateRead,
  SecretReferenceRead,
  SecretReferenceRegister,
  UUID,
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
  Textarea,
} from "@/components/ui";

interface ProviderForm {
  name: string;
  provider_type: string;
  base_url: string;
  authentication_method: string;
  is_enabled: boolean;
  notes: string;
}

const BLANK_PROVIDER: ProviderForm = {
  name: "",
  provider_type: "career_site",
  base_url: "",
  authentication_method: "session",
  is_enabled: true,
  notes: "",
};

function titleCase(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

interface SessionForm {
  provider_id: string;
  storage_reference: string;
  external_session_id: string;
}

const BLANK_SESSION: SessionForm = {
  provider_id: "",
  storage_reference: "",
  external_session_id: "",
};

interface SecretForm {
  provider_id: string;
  secret_type: string;
  external_reference: string;
  notes: string;
}

const BLANK_SECRET: SecretForm = {
  provider_id: "",
  secret_type: "password",
  external_reference: "",
  notes: "",
};

export function ConnectionsPanel() {
  const { candidate, loading: candidateLoading } = useCandidate();
  const candidateId = candidate?.id ?? null;
  const base = candidateId ? `/api/v1/candidates/${candidateId}/auth` : null;

  const providers = useList<ProviderRead>(base ? `${base}/providers` : null);
  const challenges = useList<ChallengeRead>(base ? `${base}/challenges` : null);
  const sessions = useList<BrowserSessionRead>(base ? `${base}/browser-sessions` : null);
  const secrets = useList<SecretReferenceRead>(base ? `${base}/secrets` : null);

  const [overview, setOverview] = useState<AuthOverview | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [overviewError, setOverviewError] = useState<string | null>(null);

  const [providerForm, setProviderForm] = useState<ProviderForm>(BLANK_PROVIDER);
  const [sessionForm, setSessionForm] = useState<SessionForm>(BLANK_SESSION);
  const [secretForm, setSecretForm] = useState<SecretForm>(BLANK_SECRET);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [states, setStates] = useState<Record<string, ProviderStateRead>>({});

  function errorOf(err: unknown): string {
    return err instanceof Error ? err.message : "Action failed.";
  }

  async function loadOverview() {
    if (!base) return;
    setOverviewLoading(true);
    setOverviewError(null);
    try {
      setOverview(await apiGet<AuthOverview>(`${base}/overview`));
    } catch (err) {
      setOverviewError(errorOf(err));
    } finally {
      setOverviewLoading(false);
    }
  }

  async function createProvider(e: React.FormEvent) {
    e.preventDefault();
    if (!base) return;
    setBusy(true);
    setActionError(null);
    try {
      const payload: ProviderCreate = {
        name: providerForm.name.trim(),
        provider_type: providerForm.provider_type as ProviderCreate["provider_type"],
        base_url: providerForm.base_url || null,
        authentication_method:
          providerForm.authentication_method as ProviderCreate["authentication_method"],
        is_enabled: providerForm.is_enabled,
        notes: providerForm.notes || null,
      };
      await apiPost<ProviderRead>(`${base}/providers`, payload);
      setProviderForm(BLANK_PROVIDER);
      await providers.reload();
      await loadOverview();
    } catch (err) {
      setActionError(errorOf(err));
    } finally {
      setBusy(false);
    }
  }

  async function observeProvider(providerId: UUID, status: AuthState) {
    if (!base) return;
    setBusy(true);
    setActionError(null);
    try {
      const report: AuthStateReport = { status };
      const state = await apiPost<ProviderStateRead>(
        `${base}/providers/${providerId}/state`,
        report,
      );
      setStates((prev) => ({ ...prev, [providerId]: state }));
    } catch (err) {
      setActionError(errorOf(err));
    } finally {
      setBusy(false);
    }
  }

  async function reportProviderState(providerId: UUID) {
    if (!base) return;
    setBusy(true);
    setActionError(null);
    try {
      const state = await apiGet<ProviderStateRead>(`${base}/providers/${providerId}/state`);
      setStates((prev) => ({ ...prev, [providerId]: state }));
    } catch (err) {
      setActionError(errorOf(err));
    } finally {
      setBusy(false);
    }
  }

  async function deleteProvider(provider: ProviderRead) {
    if (!base) return;
    if (!window.confirm(`Delete provider "${provider.name}"? Associated states remain available.`)) return;
    setActionError(null);
    try {
      await apiDelete(`${base}/providers/${provider.id}`);
      await providers.reload();
      await loadOverview();
    } catch (err) {
      setActionError(errorOf(err));
    }
  }

  async function acknowledge(challenge: ChallengeRead) {
    if (!base) return;
    setActionError(null);
    try {
      await apiPost<ChallengeRead>(`${base}/challenges/${challenge.id}/acknowledge`);
      await challenges.reload();
      await loadOverview();
    } catch (err) {
      setActionError(errorOf(err));
    }
  }

  async function complete(challenge: ChallengeRead) {
    if (!base) return;
    const input: ChallengeCompleteInput = { resolution_method: "human" };
    setActionError(null);
    try {
      await apiPost<ChallengeRead>(`${base}/challenges/${challenge.id}/complete`, input);
      await challenges.reload();
      await loadOverview();
    } catch (err) {
      setActionError(errorOf(err));
    }
  }

  async function cancel(challenge: ChallengeRead) {
    if (!base) return;
    const reason = window.prompt("Reason for cancelling this challenge?", "Resolved by user");
    const input: ChallengeCancelInput = { reason: reason?.trim() || null };
    setActionError(null);
    try {
      await apiPost<ChallengeRead>(`${base}/challenges/${challenge.id}/cancel`, input);
      await challenges.reload();
      await loadOverview();
    } catch (err) {
      setActionError(errorOf(err));
    }
  }

  async function createSession(e: React.FormEvent) {
    e.preventDefault();
    if (!base) return;
    setBusy(true);
    setActionError(null);
    try {
      const payload: BrowserSessionCreate = {
        provider_id: sessionForm.provider_id,
        storage_reference: sessionForm.storage_reference || null,
        external_session_id: sessionForm.external_session_id || null,
      };
      await apiPost<BrowserSessionRead>(`${base}/browser-sessions`, payload);
      setSessionForm(BLANK_SESSION);
      await sessions.reload();
    } catch (err) {
      setActionError(errorOf(err));
    } finally {
      setBusy(false);
    }
  }

  async function closeSession(session: BrowserSessionRead) {
    if (!base) return;
    setActionError(null);
    try {
      await apiPost<BrowserSessionRead>(`${base}/browser-sessions/${session.id}/close`);
      await sessions.reload();
    } catch (err) {
      setActionError(errorOf(err));
    }
  }

  async function registerSecret(e: React.FormEvent) {
    e.preventDefault();
    if (!base) return;
    setBusy(true);
    setActionError(null);
    try {
      const payload: SecretReferenceRegister = {
        provider_id: secretForm.provider_id,
        secret_type: secretForm.secret_type as SecretReferenceRegister["secret_type"],
        external_reference: secretForm.external_reference.trim(),
        notes: secretForm.notes || null,
      };
      await apiPost<SecretReferenceRead>(`${base}/secrets`, payload);
      setSecretForm(BLANK_SECRET);
      await secrets.reload();
    } catch (err) {
      setActionError(errorOf(err));
    } finally {
      setBusy(false);
    }
  }

  async function rotateSecret(ref: SecretReferenceRead) {
    if (!base) return;
    setActionError(null);
    try {
      await apiPost<SecretReferenceRead>(`${base}/secrets/${ref.id}/rotate`);
      await secrets.reload();
    } catch (err) {
      setActionError(errorOf(err));
    }
  }

  async function revokeSecret(ref: SecretReferenceRead) {
    if (!base) return;
    if (!window.confirm("Revoke this secret reference?")) return;
    setActionError(null);
    try {
      await apiPost<SecretReferenceRead>(`${base}/secrets/${ref.id}/revoke`);
      await secrets.reload();
    } catch (err) {
      setActionError(errorOf(err));
    }
  }

  const providerSelect = (value: string, onChange: (v: string) => void) => (
    <Select value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">Select provider…</option>
      {providers.items.map((p) => (
        <option key={p.id} value={p.id}>
          {p.name}
        </option>
      ))}
    </Select>
  );

  if (candidateLoading) return <Spinner />;
  if (!candidate) {
    return <EmptyState>Create your candidate profile before configuring auth providers.</EmptyState>;
  }

  return (
    <div className="space-y-6">
      {/* Summary */}
      <Card>
        <CardHeader
          title="Connected services"
          description="Configuration and state for the career sites your agent can sign in to."
          action={
            <Button type="button" variant="secondary" loading={overviewLoading} onClick={() => void loadOverview()}>
              Refresh
            </Button>
          }
        />
        <CardBody>
          {overviewError ? <Alert tone="error">{overviewError}</Alert> : null}
          {overview ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="rounded-lg bg-zinc-50 px-4 py-3">
                <p className="text-2xl font-bold text-zinc-900">{overview.provider_count}</p>
                <p className="text-sm text-zinc-500">Providers</p>
              </div>
              <div className="rounded-lg bg-zinc-50 px-4 py-3">
                <p className="text-2xl font-bold text-zinc-900">{overview.open_challenge_count}</p>
                <p className="text-sm text-zinc-500">Open challenges</p>
              </div>
              <div className="rounded-lg bg-zinc-50 px-4 py-3">
                <p className="text-2xl font-bold text-zinc-900">
                  {overview.providers.filter((p) => p.auth_status === "authenticated").length}
                </p>
                <p className="text-sm text-zinc-500">Authenticated</p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-zinc-500">Press Refresh to load the summary.</p>
          )}
        </CardBody>
      </Card>

      {/* Providers */}
      <Card>
        <CardHeader title="Providers" description="Career sites and their sign-in methods." />
        <CardBody>
          <form onSubmit={createProvider} className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Name">
              <Input required value={providerForm.name} onChange={(e) => setProviderForm({ ...providerForm, name: e.target.value })} placeholder="Workday at Acme" />
            </Field>
            <Field label="Provider type">
              <Select value={providerForm.provider_type} onChange={(e) => setProviderForm({ ...providerForm, provider_type: e.target.value })}>
                {AUTH_PROVIDER_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Base URL">
              <Input value={providerForm.base_url} onChange={(e) => setProviderForm({ ...providerForm, base_url: e.target.value })} placeholder="https://…" />
            </Field>
            <Field label="Authentication method">
              <Select value={providerForm.authentication_method} onChange={(e) => setProviderForm({ ...providerForm, authentication_method: e.target.value })}>
                {AUTH_METHODS.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="flex items-center gap-2 pt-6 text-sm font-medium text-zinc-700">
              <input
                type="checkbox"
                checked={providerForm.is_enabled}
                onChange={(e) => setProviderForm({ ...providerForm, is_enabled: e.target.checked })}
              />
              Enabled
            </div>
            <div className="flex items-end">
              <Button type="submit" loading={busy}>
                Add provider
              </Button>
            </div>
            <div className="sm:col-span-2 lg:col-span-3">
              <Field label="Notes">
                <Textarea rows={2} value={providerForm.notes} onChange={(e) => setProviderForm({ ...providerForm, notes: e.target.value })} />
              </Field>
            </div>
          </form>

          {providers.loading ? (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
          ) : providers.error ? (
            <Alert tone="error" className="mt-4">{providers.error}</Alert>
          ) : providers.items.length === 0 ? (
            <div className="mt-4">
              <EmptyState>No providers configured yet.</EmptyState>
            </div>
          ) : (
            <ul className="mt-4 divide-y divide-zinc-100">
              {providers.items.map((provider) => {
                const state = states[provider.id];
                return (
                  <li key={provider.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                    <div className="min-w-0">
                      <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-zinc-900">
                        {provider.name}
                        <Badge value={provider.provider_type} />
                        <Badge value={provider.authentication_method} />
                        {provider.is_enabled ? null : (
                          <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-amber-800">
                            Disabled
                          </span>
                        )}
                      </p>
                      <p className="mt-0.5 text-xs text-zinc-500">
                        {provider.base_url ?? "No URL"}
                        {state ? ` · ${titleCase(state.status)}` : ""}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Select
                        className="h-9 w-44"
                        aria-label={`Observe state for ${provider.name}`}
                        value=""
                        onChange={(e) => {
                          const status = e.target.value as AuthState;
                          if (status) void observeProvider(provider.id, status);
                        }}
                      >
                        <option value="">Report state…</option>
                        {AUTH_STATES.map((s) => (
                          <option key={s.value} value={s.value}>
                            {s.label}
                          </option>
                        ))}
                      </Select>
                      <Button type="button" variant="secondary" onClick={() => void reportProviderState(provider.id)}>
                        Last state
                      </Button>
                      <Button type="button" variant="danger" onClick={() => void deleteProvider(provider)}>
                        Delete
                      </Button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </CardBody>
      </Card>

      {/* Challenges */}
      <Card>
        <CardHeader title="Challenges" description="Human-verification and auth challenges detected for this account." />
        <CardBody>
          {challenges.loading ? (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
          ) : challenges.error ? (
            <Alert tone="error">{challenges.error}</Alert>
          ) : challenges.items.length === 0 ? (
            <EmptyState>No challenges recorded yet.</EmptyState>
          ) : (
            <ul className="divide-y divide-zinc-100">
              {challenges.items.map((challenge) => (
                <li key={challenge.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-zinc-900">
                      <Badge value={challenge.challenge_type} />
                      <Badge value={challenge.status} />
                      <Badge value={challenge.severity} />
                      {challenge.human_required ? (
                        <span className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-red-800">
                          Human required
                        </span>
                      ) : null}
                    </p>
                    <p className="mt-1 text-xs text-zinc-500">
                      {challenge.description ?? CHALLENGE_TYPES.find((t) => t.value === challenge.challenge_type)?.label ?? challenge.challenge_type}
                      {" · "}
                      detected {new Date(challenge.detected_at).toLocaleString()}
                      {challenge.expires_at ? ` · expires ${new Date(challenge.expires_at).toLocaleString()}` : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {challenge.status === "open" || challenge.status === "acknowledged" ? (
                      <>
                        <Button type="button" variant="secondary" onClick={() => void acknowledge(challenge)}>
                          Acknowledge
                        </Button>
                        <Button type="button" onClick={() => void complete(challenge)}>
                          Mark resolved
                        </Button>
                        <Button type="button" variant="danger" onClick={() => void cancel(challenge)}>
                          Cancel
                        </Button>
                      </>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      {/* Browser sessions */}
      <Card>
        <CardHeader title="Browser sessions" description="Agent-managed sign-in sessions." />
        <CardBody>
          <form onSubmit={createSession} className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Provider">{providerSelect(sessionForm.provider_id, (v) => setSessionForm({ ...sessionForm, provider_id: v }))}</Field>
            <Field label="Storage reference">
              <Input value={sessionForm.storage_reference} onChange={(e) => setSessionForm({ ...sessionForm, storage_reference: e.target.value })} />
            </Field>
            <Field label="External session ID">
              <Input value={sessionForm.external_session_id} onChange={(e) => setSessionForm({ ...sessionForm, external_session_id: e.target.value })} />
            </Field>
            <div className="flex items-end">
              <Button type="submit" loading={busy} disabled={!sessionForm.provider_id}>
                Create session
              </Button>
            </div>
          </form>

          {sessions.loading ? (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
          ) : sessions.error ? (
            <Alert tone="error" className="mt-4">{sessions.error}</Alert>
          ) : sessions.items.length === 0 ? (
            <div className="mt-4">
              <EmptyState>No browser sessions yet.</EmptyState>
            </div>
          ) : (
            <ul className="mt-4 divide-y divide-zinc-100">
              {sessions.items.map((session) => (
                <li key={session.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-zinc-900">
                      <Badge value={session.status} />
                      <span>{providers.items.find((p) => p.id === session.provider_id)?.name ?? session.provider_id}</span>
                    </p>
                    <p className="mt-0.5 text-xs text-zinc-500">
                      created {new Date(session.created_at).toLocaleString()}
                      {session.last_seen_at ? ` · last seen ${new Date(session.last_seen_at).toLocaleString()}` : ""}
                      {session.storage_reference ? ` · ${session.storage_reference}` : ""}
                    </p>
                  </div>
                  {session.status === "active" ? (
                    <Button type="button" variant="danger" onClick={() => void closeSession(session)}>
                      Close
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      {/* Secrets */}
      <Card>
        <CardHeader
          title="Authentication secrets"
          description="External references only — values are never stored or returned to the browser."
        />
        <CardBody>
          <form onSubmit={registerSecret} className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <Field label="Provider">{providerSelect(secretForm.provider_id, (v) => setSecretForm({ ...secretForm, provider_id: v }))}</Field>
            <Field label="Secret type">
              <Select value={secretForm.secret_type} onChange={(e) => setSecretForm({ ...secretForm, secret_type: e.target.value })}>
                {SECRET_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="External reference">
              <Input required value={secretForm.external_reference} onChange={(e) => setSecretForm({ ...secretForm, external_reference: e.target.value })} placeholder="vault://path/key" />
            </Field>
            <Field label="Notes">
              <Input value={secretForm.notes} onChange={(e) => setSecretForm({ ...secretForm, notes: e.target.value })} />
            </Field>
            <div className="flex items-end">
              <Button type="submit" loading={busy} disabled={!secretForm.provider_id}>
                Register
              </Button>
            </div>
          </form>

          {secrets.loading ? (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
          ) : secrets.error ? (
            <Alert tone="error" className="mt-4">{secrets.error}</Alert>
          ) : secrets.items.length === 0 ? (
            <div className="mt-4">
              <EmptyState>No secrets registered.</EmptyState>
            </div>
          ) : (
            <ul className="mt-4 divide-y divide-zinc-100">
              {secrets.items.map((ref) => (
                <li key={ref.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-zinc-900">
                      <Badge value={ref.secret_type} />
                      <Badge value={ref.status} />
                      <span className="font-mono text-xs">{ref.external_reference}</span>
                    </p>
                    <p className="mt-0.5 text-xs text-zinc-500">
                      {providers.items.find((p) => p.id === ref.provider_id)?.name ?? ref.provider_id}
                      {ref.is_local_dev_placeholder ? " · local dev placeholder" : ""}
                      {ref.notes ? ` · ${ref.notes}` : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button type="button" variant="secondary" onClick={() => void rotateSecret(ref)}>
                      Rotate
                    </Button>
                    <Button type="button" variant="danger" onClick={() => void revokeSecret(ref)}>
                      Revoke
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      {actionError ? <Alert tone="error">{actionError}</Alert> : null}
    </div>
  );
}
