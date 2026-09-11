"use client";

import { ExperienceEditor } from "@/components/experience-editor";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/ui";

export default function ExperiencePage() {
  return (
    <AppShell>
      <PageHeader
        title="Experience"
        description="Work history including roles, responsibilities, and achievements."
      />
      <ExperienceEditor />
    </AppShell>
  );
}