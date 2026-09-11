"use client";

import { ConnectionsPanel } from "@/components/connections-panel";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/ui";

export default function ConnectionsPage() {
  return (
    <AppShell>
      <PageHeader
        title="Connections"
        description="Manage career-site providers, track sign-in state, challenges, and authentication secrets."
      />
      <ConnectionsPanel />
    </AppShell>
  );
}