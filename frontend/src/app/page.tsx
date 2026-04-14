// Home page — server component that fetches the curated repo list and renders
// the repo picker. Runs on the server so the initial HTML already contains the
// cards; no loading spinner needed on first paint.
import RepoCards from "./repo-cards";

interface Repo {
  id: string;
  name: string;
  description: string;
  language: string;
  path: string;
}

export default async function Home() {
  let repos: Repo[] = [];
  let backendError = false;

  try {
    const res = await fetch("http://localhost:8000/api/repos", {
      cache: "no-store",
    });
    if (res.ok) {
      repos = await res.json();
    } else {
      backendError = true;
    }
  } catch {
    backendError = true;
  }

  return (
    <div className="min-h-screen bg-zinc-50 font-sans dark:bg-black">
      <main className="mx-auto max-w-4xl px-6 py-16">
        <h1 className="mb-2 text-3xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100">
          VIGIL
        </h1>
        <p className="mb-8 text-zinc-600 dark:text-zinc-400">
          Select a repository to scan for security vulnerabilities.
        </p>
        {backendError ? (
          <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-6 text-center">
            <p className="text-sm text-red-400">
              Could not reach the backend at localhost:8000.
            </p>
            <p className="mt-1 text-xs text-zinc-500">
              Make sure the FastAPI server is running.
            </p>
          </div>
        ) : (
          <RepoCards repos={repos} />
        )}
      </main>
    </div>
  );
}
