"use client";

import { useCallback, useEffect, useState } from "react";

import { apiGet } from "@/lib/api";
import type { CandidateRead } from "@/lib/types";

interface CandidateState {
  candidate: CandidateRead | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

/** Loads the current user's candidate profile (null when none exists yet). */
export function useCandidate(): CandidateState {
  const [candidate, setCandidate] = useState<CandidateRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const me = await apiGet<CandidateRead>("/api/v1/candidates/me");
      setCandidate(me);
    } catch (err) {
      if (err instanceof Error && err.message.includes("404")) {
        setCandidate(null);
      } else {
        setError(err instanceof Error ? err.message : "Failed to load profile");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => void refresh(), 0);
    return () => clearTimeout(timer);
  }, [refresh]);

  return { candidate, loading, error, refresh };
}

/** Loads data for a candidate sub-resource and refreshes after mutations. */
export function useList<T>(path: string | null): {
  items: T[];
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
} {
  const [items, setItems] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!path) return;
    try {
      const data = await apiGet<T[]>(path);
      setItems(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    const timer = setTimeout(() => void reload(), 0);
    return () => clearTimeout(timer);
  }, [reload]);

  return { items, loading, error, reload };
}