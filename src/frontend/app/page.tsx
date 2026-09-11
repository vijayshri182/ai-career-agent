import Link from "next/link";

export default function Home() {
  return (
    <div className="flex flex-1 flex-col">
      <header className="border-b border-zinc-200">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4">
          <span className="text-sm font-semibold tracking-tight text-zinc-900">
            AI Career Agent
          </span>
          <nav className="flex items-center gap-3">
            <Link
              href="/login"
              className="rounded-md px-3 py-1.5 text-sm font-medium text-zinc-600 transition-colors hover:bg-zinc-50 hover:text-zinc-900"
            >
              Sign in
            </Link>
            <Link
              href="/register"
              className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-zinc-700"
            >
              Create account
            </Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col items-center justify-center px-4 py-20 text-center">
        <p className="mb-4 text-sm font-medium uppercase tracking-widest text-zinc-400">
          Phase 1 · Profile &amp; resume workspace
        </p>
        <h1 className="max-w-2xl text-4xl font-bold tracking-tight text-zinc-900 sm:text-5xl">
          Your applications, organized. Your credentials, ready.
        </h1>
        <p className="mt-5 max-w-xl text-lg text-zinc-500">
          Capture your profile, skills, experience, and resumes once — then let the agent keep
          everything consistent as you apply to more roles.
        </p>
        <div className="mt-8 flex flex-col gap-3 sm:flex-row">
          <Link
            href="/register"
            className="inline-flex h-11 items-center justify-center rounded-md bg-zinc-900 px-6 text-sm font-medium text-white transition-colors hover:bg-zinc-700"
          >
            Get started
          </Link>
          <Link
            href="/login"
            className="inline-flex h-11 items-center justify-center rounded-md border border-zinc-300 bg-white px-6 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50"
          >
            Sign in
          </Link>
        </div>

        <div className="mt-16 grid w-full grid-cols-1 gap-4 text-left sm:grid-cols-3">
          {[
            {
              title: "Structured profile",
              body: "Skills, experience, education, certifications, and career preferences in one place.",
            },
            {
              title: "Resume management",
              body: "Upload, parse, and apply resume data to your profile with a single click.",
            },
            {
              title: "Connection readiness",
              body: "Track sign-in providers, challenges, and sessions so nothing stalls the pipeline.",
            },
          ].map((feature) => (
            <div key={feature.title} className="rounded-xl border border-zinc-200 bg-white p-5">
              <h2 className="text-sm font-semibold text-zinc-900">{feature.title}</h2>
              <p className="mt-1.5 text-sm leading-6 text-zinc-500">{feature.body}</p>
            </div>
          ))}
        </div>
      </main>

      <footer className="border-t border-zinc-200 py-6">
        <p className="text-center text-xs text-zinc-400">
          AI Career Agent — Phase 1 frontend.
        </p>
      </footer>
    </div>
  );
}