# Vigil Truth Manifest Schema

Each curated demo repository under `demo-repos/<repo-id>/` ships with a ground-truth manifest at `.vigil/truth.yaml`. The upcoming evaluation harness uses these manifests to score the Hunter, Surgeon, and Critic agents against known-good answers.

The format is intentionally minimal, hand-editable, and does not require any code changes to consume.

## File location

```
demo-repos/<repo-id>/.vigil/truth.yaml
```

One manifest per repo. The manifest is **not** scanned or committed to product runtime logic — it is purely an evaluation artifact.

## Top-level shape

```yaml
repo: <repo-id>                # must match the directory name
description: <short one-liner>
findings:
  - <finding entry>
  - <finding entry>
  ...
```

## Finding entry fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | Stable human-readable slug, unique within the repo (e.g. `sqli-login`, `hardcoded-secret`). Used by the harness to track fixes across attempts. |
| `cwe` | string | yes | CWE identifier, `CWE-<n>` (e.g. `CWE-89`). |
| `kind` | string | yes | Short category label (e.g. `sql-injection`, `hardcoded-secret`, `path-traversal`, `missing-rate-limit`). |
| `file` | string | yes | Path to the vulnerable file, relative to the repo root. |
| `line` | int | one of line/lines | Primary line number of the vulnerability. |
| `lines` | list[int] | one of line/lines | Use when the vulnerability spans multiple distinct lines (e.g. logging sensitive data in two handlers). |
| `severity` | string | yes | One of `critical`, `high`, `medium`, `low`. |
| `detectable_by` | list[string] | yes | Which scanner(s) are *expected* to catch the finding. Allowed values: `semgrep`, `llm`. A finding with `[semgrep, llm]` is detectable by either; `[llm]` means it is LLM-only ground truth (Semgrep will not be penalised for missing it). |
| `notes` | string | no | Free-form explanation of what the bug is and where to look. |

## Example

```yaml
repo: vibe-notes-api
description: Flask notes service with common AI-generated security antipatterns
findings:
  - id: sqli-search
    cwe: CWE-89
    kind: sql-injection
    file: app.py
    line: 57
    severity: high
    detectable_by: [semgrep, llm]
    notes: f-string query in /search endpoint

  - id: no-rate-limit-login
    cwe: CWE-307
    kind: missing-rate-limit
    file: app.py
    line: 82
    severity: medium
    detectable_by: [llm]
    notes: /login has no throttling; LLM-only check
```

## How the eval harness will use it

- **Hunter metrics**: for each run, match reported findings to truth entries by `(file, line)` proximity and `kind`/`cwe`. Compute per-scanner precision/recall using `detectable_by` to split credit (Semgrep is graded against `semgrep`-tagged entries only).
- **Surgeon metrics**: on patch proposal, track which truth entry the patch targets and whether verification came back clean.
- **Critic metrics**: record approve/reject decisions and cross-check against whether the patch ultimately verifies clean.

## Rules when editing

- Keep `id` stable once published — the harness uses it as the primary key when aggregating across runs.
- When you add a new planted bug to a demo repo, add its truth entry in the same commit.
- When you intentionally leave a bug undetectable by Semgrep (e.g. missing rate limit), make sure `detectable_by` is `[llm]` only. Do not claim Semgrep coverage that does not exist.
