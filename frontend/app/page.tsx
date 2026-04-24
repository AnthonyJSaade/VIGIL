// Landing page: pick a curated demo repo (or point at a local path) and kick off a run.
"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { Shield, ArrowRight, Crosshair, Scissors, Eye, Github, Loader2, Lock, Scan, Zap, Upload, FileArchive } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { RepoCard } from "@/components/vigil/repo-card"
import { fetchRepos, createRun, type Repository } from "@/lib/api"

export default function HomePage() {
  const router = useRouter()
  const [repos, setRepos] = useState<Repository[]>([])
  const [selectedRepo, setSelectedRepo] = useState<Repository | null>(null)
  const [starting, setStarting] = useState(false)
  const [backendError, setBackendError] = useState(false)
  const [githubUrl, setGithubUrl] = useState("")
  const [activeTab, setActiveTab] = useState<"select" | "clone">("select")
  const [uploadedFile, setUploadedFile] = useState<File | null>(null)

  useEffect(() => {
    fetchRepos()
      .then(setRepos)
      .catch(() => setBackendError(true))
  }, [])

  const handleStartAudit = async () => {
    if (!selectedRepo || starting) return
    setStarting(true)
    try {
      const run = await createRun(selectedRepo.id)
      router.push(`/audit/${run.id}`)
    } catch {
      alert("Failed to start audit. Is the backend running?")
      setStarting(false)
    }
  }

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadedFile(file)
    setSelectedRepo(null)
  }

  const isValidGithubUrl = (url: string) => {
    return url.match(/^https?:\/\/(www\.)?github\.com\/[\w-]+\/[\w.-]+\/?$/)
  }

  return (
    <main className="min-h-screen flex flex-col">
      {/* Hero Header with Grid Background */}
      <div className="relative overflow-hidden">
        <div className="absolute inset-0 bg-[linear-gradient(rgba(6,182,212,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(6,182,212,0.03)_1px,transparent_1px)] bg-[size:60px_60px]" />
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-cyan-500/10 rounded-full blur-[120px] -translate-y-1/2" />
        <div className="absolute top-0 right-1/4 w-80 h-80 bg-violet-500/8 rounded-full blur-[100px] -translate-y-1/3" />
        <div className="absolute top-20 left-1/2 w-64 h-64 bg-amber-500/5 rounded-full blur-[80px] -translate-x-1/2" />

        <header className="relative z-10 px-6 py-4">
          <div className="max-w-6xl mx-auto flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="relative">
                <Shield className="h-6 w-6 text-primary" />
                <div className="absolute inset-0 bg-primary/20 blur-md" />
              </div>
              <span className="font-semibold text-foreground tracking-tight">VIGIL</span>
            </div>
            <div className="flex items-center gap-6 text-sm text-muted-foreground">
              <span className="flex items-center gap-1.5"><Lock className="h-3.5 w-3.5" />Secure</span>
              <span className="flex items-center gap-1.5"><Scan className="h-3.5 w-3.5" />AI-Powered</span>
              <span className="flex items-center gap-1.5"><Zap className="h-3.5 w-3.5" />Real-time</span>
            </div>
          </div>
        </header>

        <section className="relative z-10 flex flex-col items-center justify-center px-6 pt-16 pb-24">
          <div className="text-center max-w-2xl mx-auto mb-12">
            <div className="relative inline-block mb-6">
              <h1 className="text-6xl font-bold tracking-tighter text-transparent bg-clip-text bg-gradient-to-b from-cyan-300 via-cyan-400 to-cyan-600">
                VIGIL
              </h1>
              <div className="absolute inset-0 text-6xl font-bold tracking-tighter text-primary blur-2xl opacity-50">
                VIGIL
              </div>
            </div>
            <p className="text-lg text-muted-foreground mb-2">Multi-Agent DevSecOps Gatekeeper</p>
            <p className="text-sm text-muted-foreground/70 max-w-md mx-auto">
              Automated security auditing powered by specialized AI agents that hunt vulnerabilities, craft patches, and verify fixes.
            </p>
            <div className="flex items-center justify-center gap-3 mt-8">
              <div className="flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-4 py-2">
                <Crosshair className="h-4 w-4 text-cyan-400" />
                <span className="text-sm font-medium text-cyan-400">Hunter</span>
              </div>
              <div className="flex items-center gap-2 rounded-full border border-amber-500/30 bg-amber-500/10 px-4 py-2">
                <Scissors className="h-4 w-4 text-amber-400" />
                <span className="text-sm font-medium text-amber-400">Surgeon</span>
              </div>
              <div className="flex items-center gap-2 rounded-full border border-violet-400/30 bg-violet-400/10 px-4 py-2">
                <Eye className="h-4 w-4 text-violet-400" />
                <span className="text-sm font-medium text-violet-400">Critic</span>
              </div>
            </div>
          </div>
        </section>

        <div className="absolute bottom-0 left-0 right-0 h-24 bg-gradient-to-t from-background to-transparent" />
      </div>

      {/* Repo Selection Section */}
      <section className="relative z-20 flex-1 px-6 pb-16 -mt-12">
        <div className="w-full max-w-4xl mx-auto">
          {/* Tabs */}
          <div className="flex items-center gap-1 mb-8 bg-card/80 backdrop-blur-sm border border-border/50 rounded-lg p-1.5 w-fit mx-auto shadow-lg">
            <button
              onClick={() => setActiveTab("select")}
              className={`px-5 py-2.5 rounded-md text-sm font-medium transition-all ${
                activeTab === "select"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
              }`}
            >
              Select Repository
            </button>
            <button
              onClick={() => setActiveTab("clone")}
              className={`px-5 py-2.5 rounded-md text-sm font-medium transition-all flex items-center gap-2 ${
                activeTab === "clone"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
              }`}
            >
              <Github className="h-4 w-4" />
              Clone from GitHub
            </button>
          </div>

          {activeTab === "select" ? (
            <>
              {backendError ? (
                <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6 text-center">
                  <p className="text-sm font-medium text-destructive">Backend Unavailable</p>
                  <p className="text-xs text-muted-foreground mt-1">Make sure the backend is running on localhost:8000</p>
                </div>
              ) : (
                <>
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="text-sm font-medium text-foreground">Select a repository to audit</h2>
                    {(selectedRepo || uploadedFile) && (
                      <span className="text-xs text-muted-foreground">
                        Selected: <span className="text-primary">{uploadedFile ? uploadedFile.name : selectedRepo?.name}</span>
                      </span>
                    )}
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Upload ZIP card (non-functional) */}
                    <label
                      className={`group relative flex flex-col rounded-lg border-2 border-dashed p-5 cursor-pointer transition-all ${
                        uploadedFile
                          ? "border-primary bg-primary/5"
                          : "border-border hover:border-primary/50 hover:bg-card/50"
                      }`}
                    >
                      <input type="file" accept=".zip" onChange={handleFileUpload} className="sr-only" />
                      <div className="flex items-start gap-4">
                        <div className={`h-10 w-10 rounded-lg flex items-center justify-center shrink-0 transition-colors ${
                          uploadedFile ? "bg-primary/20" : "bg-muted/50 group-hover:bg-primary/10"
                        }`}>
                          {uploadedFile ? (
                            <FileArchive className="h-5 w-5 text-primary" />
                          ) : (
                            <Upload className="h-5 w-5 text-muted-foreground group-hover:text-primary" />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          {uploadedFile ? (
                            <>
                              <h3 className="text-sm font-medium text-foreground truncate">{uploadedFile.name}</h3>
                              <p className="text-xs text-muted-foreground mt-0.5">{(uploadedFile.size / 1024 / 1024).toFixed(2)} MB</p>
                            </>
                          ) : (
                            <>
                              <h3 className="text-sm font-medium text-foreground">Upload Repository</h3>
                              <p className="text-xs text-muted-foreground mt-0.5">Drop a .zip file or click to browse</p>
                            </>
                          )}
                        </div>
                      </div>
                    </label>

                    {repos.map((repo) => (
                      <RepoCard
                        key={repo.id}
                        repo={repo}
                        selected={selectedRepo?.id === repo.id}
                        onSelect={(r) => {
                          setSelectedRepo(r)
                          setUploadedFile(null)
                        }}
                      />
                    ))}
                  </div>

                  <div className="mt-8 flex justify-center">
                    <Button
                      size="lg"
                      onClick={handleStartAudit}
                      disabled={!selectedRepo || starting}
                      className="bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 gap-2 px-8"
                    >
                      {starting ? (
                        <><Loader2 className="h-4 w-4 animate-spin" />Starting audit...</>
                      ) : (
                        <>Start Audit<ArrowRight className="h-4 w-4" /></>
                      )}
                    </Button>
                  </div>
                </>
              )}
            </>
          ) : (
            /* Clone from GitHub tab (non-functional UI) */
            <div className="max-w-xl mx-auto">
              <div className="rounded-lg border border-border bg-card p-6">
                <div className="flex items-center gap-3 mb-4">
                  <div className="h-10 w-10 rounded-full bg-muted/50 flex items-center justify-center">
                    <Github className="h-5 w-5 text-foreground" />
                  </div>
                  <div>
                    <h3 className="text-sm font-medium text-foreground">Clone Repository</h3>
                    <p className="text-xs text-muted-foreground">Enter a GitHub repository URL to audit</p>
                  </div>
                </div>
                <div className="flex gap-3">
                  <Input
                    placeholder="https://github.com/owner/repository"
                    value={githubUrl}
                    onChange={(e) => setGithubUrl(e.target.value)}
                    className="flex-1 bg-background border-border"
                  />
                  <Button disabled={!isValidGithubUrl(githubUrl)} className="bg-primary text-primary-foreground hover:bg-primary/90 gap-2">
                    Clone & Audit <ArrowRight className="h-4 w-4" />
                  </Button>
                </div>
                {githubUrl && !isValidGithubUrl(githubUrl) && (
                  <p className="text-xs text-destructive mt-2">Please enter a valid GitHub repository URL</p>
                )}
                <div className="mt-4 pt-4 border-t border-border">
                  <p className="text-xs text-muted-foreground">Coming soon — currently only curated demo repos are supported.</p>
                </div>
              </div>
            </div>
          )}
        </div>
      </section>

      <footer className="border-t border-border/50 px-6 py-4">
        <p className="text-center text-xs text-muted-foreground">
          Powered by AI agents. Securing your code, one commit at a time.
        </p>
      </footer>
    </main>
  )
}
