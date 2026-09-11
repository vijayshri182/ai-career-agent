"use client";

import { ProfileEditor } from "@/components/profile-editor";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/ui";

export default function ProfilePage() {
  return (
    <AppShell>
      <PageHeader
        title="Profile"
        description="Core candidate details used across your profile summary, resumes, and future applications."
      />
      <ProfileEditor />
    </AppShell>
  );
}