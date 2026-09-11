"use client";

import { SkillsEditor } from "@/components/skills-editor";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/ui";

export default function SkillsPage() {
  return (
    <AppShell>
      <PageHeader
        title="Skills"
        description="Technical skills and domain expertise shown on your profile."
      />
      <SkillsEditor />
    </AppShell>
  );
}