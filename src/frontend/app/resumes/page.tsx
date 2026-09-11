"use client";

import { ResumesPanel } from "@/components/resumes-panel";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/ui";

export default function ResumesPage() {
  return (
    <AppShell>
      <PageHeader
        title="Resumes"
        description="Upload, create, and parse resume documents. Keep your latest versions ready for the agent to use."
      />
      <ResumesPanel />
    </AppShell>
  );
}