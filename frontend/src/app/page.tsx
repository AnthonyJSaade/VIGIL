import RepoCards from "./repo-cards";

interface Repo {
  id: string;
  name: string;
  description: string;
  language: string;
  path: string;
}

export default async function Home() {
  const res = await fetch("http://localhost:8000/api/repos", {
    cache: "no-store",
  });
  const repos: Repo[] = await res.json();

  return (
    <div className="min-h-screen bg-zinc-50 font-sans dark:bg-black">
      <main className="mx-auto max-w-4xl px-6 py-16">
        <h1 className="mb-2 text-3xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100">
          VIGIL
        </h1>
        <p className="mb-8 text-zinc-600 dark:text-zinc-400">
          Select a repository to scan for security vulnerabilities.
        </p>
        <RepoCards repos={repos} />
      </main>
    </div>
  );
}
