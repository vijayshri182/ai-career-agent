"use client";

import { CertificationsEditor } from "@/components/certifications-editor";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/ui";

export default function CertificationsPage() {
  return (
    <AppShell>
      <PageHeader
        title="Certifications"
        description="Professional certifications and credentials."
      />
      <CertificationsEditor />
    </AppShell>
  );
}