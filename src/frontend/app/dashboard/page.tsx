"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { apiGet } from "@/lib/api";
import { useCandidate } from "@/lib/hooks";
import type { ProfileRead } from "@/lib/types";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  PageHeader,
  Spinner,
} from "@/components/ui";
import { AppShell } from "@/components/app-shell";

const SECTION_LINKS = [
  { href: "/profile", label: "Profile details", body: "Name, headline, summary, compensation." },
  { href: "/profile/skills", label: "Skills", body: "Your technical stack with proficiency." },
  { href: "/profile/experience", label: "Experience", body: "Roles, responsibilities, achievements." },
  { href: "/profile/education", label: "Education", body: "Degrees and institutions." },
  { href: "/profile/certifications", label: "Certifications", body: "Certifications and credentials." },
  { href: "/profile/preferences", label: "Preferences", body: "Target roles, industries, locations." },
  { href: "/resumes", label: "Resumes", body: "Upload, parse, and apply to your profile." },
  { href: "/connections", label: "Connections", body: "Providers, challenges, sessions, secrets." },
];

export default function DashboardPage() {
  const { candidate, loading, error, refresh } = useCandidate();
  const [profile, setProfile] = useState<ProfileRead | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);

  useEffect(() => {
    if (candidate?.id) {
      let stale = false;
      apiGet<ProfileRead>(`/api/v1/candidates/${candidate.id}/profile`)
        .then((data) => {
          if (!stale) setProfile(data);
        })
        .catch(() => {})
        .finally(() => {
          if (!stale) setProfileLoading(false);
        });
      return () => {
        stale = true;
      };
    }
  }, [candidate?.id]);

  if (loading) {
    return (
      <AppShell>
        <div className="flex justify-center py-24">
          <Spinner />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageHeader
        title={`Welcome${candidate?.full_name ? `, ${candidate.full_name.split(" ")[0]}` : ""}`}
        description={
          candidate?.headline ??
          "Your career workspace — keep your profile and materials ready for applications."
        }
      />

      {error ? (
        <Alert tone="error" title="Could not load your profile">
          {error}
        </Alert>
      ) : null}

      {!candidate ? (
        <Card className="mb-8">
          <CardBody>
            <h2 className="text-base font-semibold text-zinc-900">Create your candidate profile</h2>
            <p className="mt-1 text-sm text-zinc-500">
              Your profile holds the core details shared across resumes and future application the
              agent builds for you. Get started with a few essential fields.
            </p>
            <div className="mt-4">
              <Link href="/profile">
                <Button>Create profile</Button>
              </Link>
            </div>
          </CardBody>
        </Card>
      ) : (
        <Card className="mb-8">
          <CardHeader
            title={
              <span className="flex flex-wrap items-center gap-2">
                Profile
                <Badge value={candidate.status} />
              </span>
            }
            description="Completeness is estimated from the fields you have filled in."
            action={
              <Link href="/profile">
                <Button variant="secondary">Edit profile</Button>
              </Link>
            }
          />
          <CardBody>
            {profileLoading ? (
              <div className="flex justify-center py-6">
                <Spinner />
              </div>
            ) : profile ? (
              <div className="space-y-4">
                <div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium text-zinc-700">Profile completeness</span>
                    <span className="text-zinc-500">{profile.completeness.percentage}%</span>
                  </div>
                  <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-zinc-200">
                    <div
                      className="h-full rounded-full bg-zinc-900 transition-all"
                      style={{ width: `${Math.min(100, profile.completeness.percentage)}%` }}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
                  {profile.completeness.items.map((item) => (
                    <div key={item.name} className="flex items-center gap-2 text-sm">
                      <span
                        className={`inline-block h-2 w-2 shrink-0 rounded-full ${
                          item.present ? "bg-green-500" : "bg-zinc-300"
                        }`}
                      />
                      <span className={item.present ? "text-zinc-700" : "text-zinc-400"}>
                        {item.name.replaceAll("_", " ")}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <EmptyState>No aggregation available.</EmptyState>
            )}
          </CardBody>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {SECTION_LINKS.map((section) => (
          <Link key={section.href} href={section.href} className="group">
            <Card className="h-full transition-colors group-hover:border-zinc-300">
              <CardBody>
                <h2 className="text-sm font-semibold text-zinc-900">{section.label}</h2>
                <p className="mt-1 text-sm leading-5 text-zinc-500">{section.body}</p>
              </CardBody>
            </Card>
          </Link>
        ))}
      </div>

      {candidate ? (
        <div className="mt-8 flex justify-end">
          <Button variant="ghost" onClick={() => void refresh()}>
            Refresh
          </Button>
        </div>
      ) : null}
    </AppShell>
  );
}