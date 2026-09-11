"use client";

import { EducationEditor } from "@/components/education-editor";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/ui";

export default function EducationPage() {
  return (
    <AppShell>
      <PageHeader
        title="Education"
        description="Academic qualifications and institutions."
      />
      <EducationEditor />
    </AppShell>
  );
}