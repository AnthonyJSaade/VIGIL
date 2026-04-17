/**
 * Typed API client for the Vigil backend.
 * Maps snake_case backend responses to camelCase frontend types.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

// ---------------------------------------------------------------------------
// Frontend types (camelCase, matching v0 component expectations)
// ---------------------------------------------------------------------------

export interface Repository {
  id: string
  name: string
  description: string
  language: string
  path: string
}

export interface Finding {
  id: string
  runId: string
  severity: "error" | "warning" | "info"
  ruleId: string
  filePath: string
  startLine: number
  endLine: number
  scanner: string
  confidence: number
  message: string
  snippet: string
  metadata: Record<string, unknown>
  createdAt: string
}

export interface RunSummary {
  id: string
  repoId: string
  status: "pending" | "scanning" | "completed" | "failed"
  findingCount: number
  createdAt: string
}

export interface PatchProposal {
  id: string
  findingId: string
  diff: string
  explanation: string
  modelUsed: string
  attempt: number
  priorConcerns: string[] | null
  createdAt: string
}

export interface CriticVerdict {
  id: string
  patchId: string
  approved: boolean
  reasoning: string
  concerns: string[]
  modelUsed: string
  createdAt: string
}

export interface VerificationReport {
  id: string
  patchId: string
  scannerRerunClean: boolean
  testsPassed: boolean | null
  details: string
  createdAt: string
}

export interface PatchWithVerdict {
  patch: PatchProposal
  verdict: CriticVerdict | null
}

// ---------------------------------------------------------------------------
// Backend response types (snake_case)
// ---------------------------------------------------------------------------

interface BackendFinding {
  id: string
  run_id: string
  severity: string
  rule_id: string
  file_path: string
  start_line: number
  end_line: number
  scanner: string
  confidence: number
  message: string
  snippet: string
  metadata: Record<string, unknown>
  created_at: string
}

interface BackendRun {
  id: string
  repo_id: string
  status: string
  finding_count: number
  created_at: string
}

interface BackendPatch {
  id: string
  finding_id: string
  diff: string
  explanation: string
  model_used: string
  attempt: number
  prior_concerns: string[] | null
  created_at: string
}

interface BackendVerdict {
  id: string
  patch_id: string
  approved: boolean
  reasoning: string
  concerns: string[]
  model_used: string
  created_at: string
}

interface BackendVerification {
  id: string
  patch_id: string
  scanner_rerun_clean: boolean
  tests_passed: boolean | null
  details: string
  created_at: string
}

// ---------------------------------------------------------------------------
// Mappers
// ---------------------------------------------------------------------------

function mapFinding(b: BackendFinding): Finding {
  return {
    id: b.id,
    runId: b.run_id,
    severity: b.severity as Finding["severity"],
    ruleId: b.rule_id,
    filePath: b.file_path,
    startLine: b.start_line,
    endLine: b.end_line,
    scanner: b.scanner,
    confidence: Math.round(b.confidence * 100),
    message: b.message,
    snippet: b.snippet,
    metadata: b.metadata,
    createdAt: b.created_at,
  }
}

function mapRun(b: BackendRun): RunSummary {
  return {
    id: b.id,
    repoId: b.repo_id,
    status: b.status as RunSummary["status"],
    findingCount: b.finding_count,
    createdAt: b.created_at,
  }
}

function mapPatch(b: BackendPatch): PatchProposal {
  return {
    id: b.id,
    findingId: b.finding_id,
    diff: b.diff,
    explanation: b.explanation,
    modelUsed: b.model_used,
    attempt: b.attempt,
    priorConcerns: b.prior_concerns,
    createdAt: b.created_at,
  }
}

function mapVerdict(b: BackendVerdict): CriticVerdict {
  return {
    id: b.id,
    patchId: b.patch_id,
    approved: b.approved,
    reasoning: b.reasoning,
    concerns: b.concerns,
    modelUsed: b.model_used,
    createdAt: b.created_at,
  }
}

function mapVerification(b: BackendVerification): VerificationReport {
  return {
    id: b.id,
    patchId: b.patch_id,
    scannerRerunClean: b.scanner_rerun_clean,
    testsPassed: b.tests_passed,
    details: b.details,
    createdAt: b.created_at,
  }
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export async function fetchRepos(): Promise<Repository[]> {
  const res = await fetch(`${API_BASE}/api/repos`, { cache: "no-store" })
  if (!res.ok) throw new Error("Failed to fetch repos")
  return res.json()
}

export async function createRun(repoId: string): Promise<RunSummary> {
  const res = await fetch(`${API_BASE}/api/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repo_id: repoId }),
  })
  if (!res.ok) throw new Error("Failed to create run")
  const data: BackendRun = await res.json()
  return mapRun(data)
}

export async function fetchRun(runId: string): Promise<RunSummary> {
  const res = await fetch(`${API_BASE}/api/runs/${runId}`, { cache: "no-store" })
  if (!res.ok) throw new Error("Failed to fetch run")
  const data: BackendRun = await res.json()
  return mapRun(data)
}

export async function triggerLlmReview(runId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/runs/${runId}/llm-review`, { method: "POST" })
  if (!res.ok && res.status !== 202) throw new Error("Failed to start LLM review")
}

export async function fetchFindings(runId: string, severity?: string): Promise<Finding[]> {
  const params = new URLSearchParams()
  if (severity && severity !== "all") params.set("severity", severity)
  const qs = params.toString()
  const url = `${API_BASE}/api/runs/${runId}/findings${qs ? `?${qs}` : ""}`
  const res = await fetch(url, { cache: "no-store" })
  if (!res.ok) throw new Error("Failed to fetch findings")
  const data: BackendFinding[] = await res.json()
  return data.map(mapFinding)
}

export async function fetchFinding(findingId: string): Promise<Finding> {
  const res = await fetch(`${API_BASE}/api/findings/${findingId}`, { cache: "no-store" })
  if (!res.ok) throw new Error("Finding not found")
  const data: BackendFinding = await res.json()
  return mapFinding(data)
}

export async function requestPatch(
  findingId: string,
  opts?: { force?: boolean },
): Promise<void> {
  const qs = opts?.force ? "?force=true" : ""
  const res = await fetch(`${API_BASE}/api/findings/${findingId}/patch${qs}`, { method: "POST" })
  if (!res.ok && res.status !== 202) throw new Error("Failed to request patch")
}

export async function fetchPatches(findingId: string): Promise<PatchWithVerdict[]> {
  const res = await fetch(`${API_BASE}/api/findings/${findingId}/patches`, { cache: "no-store" })
  if (!res.ok) throw new Error("Failed to fetch patches")
  const data: Array<{ patch: BackendPatch; verdict: BackendVerdict | null }> = await res.json()
  return data.map((item) => ({
    patch: mapPatch(item.patch),
    verdict: item.verdict ? mapVerdict(item.verdict) : null,
  }))
}

export async function requestVerify(
  patchId: string,
  opts?: { force?: boolean },
): Promise<void> {
  const qs = opts?.force ? "?force=true" : ""
  const res = await fetch(`${API_BASE}/api/patches/${patchId}/verify${qs}`, { method: "POST" })
  if (!res.ok && res.status !== 202) throw new Error("Failed to request verification")
}

export async function fetchVerification(patchId: string): Promise<VerificationReport | null> {
  const res = await fetch(`${API_BASE}/api/patches/${patchId}/verification`, { cache: "no-store" })
  if (res.status === 404) return null
  if (!res.ok) throw new Error("Failed to fetch verification")
  const data: BackendVerification = await res.json()
  return mapVerification(data)
}

export function patchedFileUrl(patchId: string): string {
  return `${API_BASE}/api/patches/${patchId}/patched-file`
}

export interface ApplyPatchResult {
  patchId: string
  appliedFiles: string[]
  backups: string[]
}

export async function applyPatch(patchId: string): Promise<ApplyPatchResult> {
  const res = await fetch(`${API_BASE}/api/patches/${patchId}/apply`, { method: "POST" })
  if (!res.ok) {
    let detail = "Failed to apply patch"
    try {
      const body = await res.json()
      if (body?.detail) detail = body.detail
    } catch {
      /* body not JSON */
    }
    throw new Error(detail)
  }
  const data: { patch_id: string; applied_files: string[]; backups: string[] } = await res.json()
  return { patchId: data.patch_id, appliedFiles: data.applied_files, backups: data.backups }
}

export function sseUrl(runId: string): string {
  return `${API_BASE}/api/runs/${runId}/stream`
}

export function exportUrl(runId: string, format: "html" | "zip"): string {
  return `${API_BASE}/api/runs/${runId}/export?format=${format}`
}
