"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { login, register } from "@/lib/api";
import { Alert, Button, Card, CardBody, Field, Input } from "@/components/ui";

type Mode = "login" | "register";

export function AuthForm({ mode }: { mode: Mode }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password);
      }
      router.push("/dashboard");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setLoading(false);
    }
  }

  return (
    <Card className="w-full max-w-sm">
      <CardBody>
        <h1 className="mb-1 text-center text-xl font-semibold text-zinc-900">
          {mode === "login" ? "Sign in" : "Create account"}
        </h1>
        <p className="mb-6 text-center text-sm text-zinc-500">
          {mode === "login" ? "Access your career dashboard." : "Start tracking your job search."}
        </p>
        {error ? (
          <Alert tone="error" title="Unable to continue" className="mb-4">
            {error}
          </Alert>
        ) : null}
        <form onSubmit={handleSubmit} className="space-y-4">
          <Field label="Email">
            <Input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
            />
          </Field>
          <Field label="Password">
            <Input
              type="password"
              required
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </Field>
          <Button type="submit" loading={loading} className="w-full">
            {mode === "login" ? "Sign in" : "Create account"}
          </Button>
        </form>
        <p className="mt-5 text-center text-sm text-zinc-500">
          {mode === "login" ? (
            <>
              New here?{" "}
              <Link href="/register" className="font-medium text-zinc-900 hover:underline">
                Create an account
              </Link>
            </>
          ) : (
            <>
              Already registered?{" "}
              <Link href="/login" className="font-medium text-zinc-900 hover:underline">
                Sign in
              </Link>
            </>
          )}
        </p>
      </CardBody>
    </Card>
  );
}