"use client";

import { PreferencesForm } from "@/components/preferences-form";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/ui";

export default function PreferencesPage() {
  return (
    <AppShell>
      <PageHeader
        title="Preferences"
        description="Career preferences and compensation targets used later during matching."
      />
      <PreferencesForm />
    </AppShell>
  );
}