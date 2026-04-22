# Vigil Evaluation Report

_Generated 2026-04-22T06:06:09+00:00Z_

Across 4 curated vibe-coded repos (516 LOC, 38 planted vulnerabilities), Vigil's hybrid Hunter detected 36/38 (94.7% recall, 90.0% precision) and the Surgeon-Critic-Verifier pipeline produced a verified-clean fix for 18 of them (47.4% end-to-end fix rate). 22 findings were caught only by the LLM reviewer, not by Semgrep.

## Headline summary

| Repo | LOC | Truth | Detected | Precision | Recall | F1 | Fix rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `vibe-todo-app` | 172 | 11 | 11/11 | 84.6% | 100.0% | 0.92 | 6/11 |
| `vibe-notes-api` | 153 | 9 | 9/9 | 100.0% | 100.0% | 1.00 | 3/9 |
| `vibe-file-share` | 90 | 9 | 7/9 | 87.5% | 77.8% | 0.82 | 2/9 |
| `vibe-auth-service` | 101 | 9 | 9/9 | 90.0% | 100.0% | 0.95 | 7/9 |
| **Aggregate** | **516** | **38** | **36/38** | **90.0%** | **94.7%** | **0.92** | **18/38** |


## Hunter: Semgrep vs. LLM reviewer vs. hybrid

Recall denominators account for `detectable_by` tags in each truth manifest: Semgrep is scored only against findings its rulesets are expected to catch; the LLM reviewer is scored against all planted findings.

| Scanner | TP | FP | FN | Expected | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Semgrep alone | 14 | 1 | 3 | 17 | 93.3% | 82.3% | 0.88 |
| LLM reviewer alone | 22 | 3 | 16 | 38 | 88.0% | 57.9% | 0.70 |
| Hybrid (union) | 36 | 4 | 2 | 38 | 90.0% | 94.7% | 0.92 |


**LLM-only contribution:** 22 planted findings were detected by the LLM reviewer but missed by Semgrep.

## Surgeon

| Metric | Value |
| --- | --- |
| Patches attempted | 36 |
| Applied cleanly to sandbox | 26 |
| Apply rate | 72.2% |


| Repo | Patches | Apply rate | Mean attempts | Retry rate |
| --- | --- | --- | --- | --- |
| `vibe-todo-app` | 11 | 75.0% | 1.45 | 45.5% |
| `vibe-notes-api` | 9 | 60.0% | 1.44 | 44.4% |
| `vibe-file-share` | 7 | 66.7% | 1.71 | 71.4% |
| `vibe-auth-service` | 9 | 100.0% | 1.33 | 33.3% |


## Critic

| Metric | Value |
| --- | --- |
| Total verdicts | 36 |
| Approved | 23 (63.9%) |
| Rejected | 13 |
| Agreement with verifier (approved AND clean) | 78.3% |
| False-accept rate (approved BUT dirty) | 21.7% |


## End-to-end fix funnel

| Stage | Count | % of truth |
| --- | --- | --- |
| Truth findings | 38 | 100.0% |
| Detected by Hunter | 36 | 94.7% |
| Surgeon produced a patch | 36 | 94.7% |
| Critic approved | 23 | 60.5% |
| Verifier confirmed clean | 18 | 47.4% |


## Timing

| Repo | Scan (s) | Patch p50 (s) | Patch p95 (s) | Verify p50 (s) | Verify p95 (s) |
| --- | --- | --- | --- | --- | --- |
| `vibe-todo-app` | 37.62 | 13.17 | 26.24 | 5.31 | 5.96 |
| `vibe-notes-api` | 28.83 | 9.30 | 30.32 | 4.76 | 4.98 |
| `vibe-file-share` | 28.07 | 23.11 | 30.55 | 5.42 | 5.59 |
| `vibe-auth-service` | 34.49 | 7.13 | 25.84 | 4.69 | 5.48 |


## Per-repo detail

### `vibe-todo-app`

| Truth id | Detected | By scanner | Patched | Critic approved | Verified clean |
| --- | --- | --- | --- | --- | --- |
| cors-wildcard | yes | claude-review | yes | yes | yes |
| hardcoded-jwt-secret | yes | semgrep | yes | yes | yes |
| no-input-validation-register | yes | claude-review | yes | yes | no |
| logging-sensitive-data | yes | claude-review | yes | no | - |
| sqli-register | yes | claude-review | yes | yes | yes |
| no-rate-limit-login | yes | claude-review | yes | yes | yes |
| sqli-login | yes | claude-review | yes | yes | yes |
| sqli-todos | yes | claude-review | yes | no | - |
| eval-rce | yes | semgrep | yes | yes | yes |
| path-traversal-files | yes | semgrep | yes | no | - |
| error-stack-leak | yes | claude-review | yes | yes | no |


LLM-only contributions in this repo: `cors-wildcard`, `error-stack-leak`, `logging-sensitive-data`, `no-input-validation-register`, `no-rate-limit-login`, `sqli-login`, `sqli-register`, `sqli-todos`

### `vibe-notes-api`

| Truth id | Detected | By scanner | Patched | Critic approved | Verified clean |
| --- | --- | --- | --- | --- | --- |
| hardcoded-secret-key | yes | claude-review | yes | no | - |
| sqli-search | yes | semgrep | yes | yes | yes |
| weak-hash-passwords | yes | semgrep | yes | no | - |
| no-rate-limit-login | yes | claude-review | yes | no | - |
| insecure-deserialization | yes | semgrep | yes | yes | yes |
| ssrf-fetch | yes | semgrep | yes | yes | no |
| xss-note-render | yes | claude-review | yes | yes | no |
| open-redirect | yes | semgrep | yes | no | - |
| debug-mode-on | yes | semgrep | yes | yes | yes |


LLM-only contributions in this repo: `hardcoded-secret-key`, `no-rate-limit-login`, `xss-note-render`

### `vibe-file-share`

| Truth id | Detected | By scanner | Patched | Critic approved | Verified clean |
| --- | --- | --- | --- | --- | --- |
| hardcoded-admin-key | yes | claude-review | yes | no | - |
| insecure-random-slug | yes | claude-review | yes | yes | yes |
| unrestricted-upload | no | - | no | - | - |
| no-auth-download | yes | claude-review | yes | yes | yes |
| path-traversal-download | yes | semgrep | yes | no | - |
| command-injection-thumbnail | yes | semgrep | yes | yes | no |
| ssrf-mirror | yes | claude-review | yes | no | - |
| verbose-error-leak | no | - | no | - | - |
| open-redirect | yes | semgrep | yes | no | - |


LLM-only contributions in this repo: `hardcoded-admin-key`, `insecure-random-slug`, `no-auth-download`, `ssrf-mirror`

### `vibe-auth-service`

| Truth id | Detected | By scanner | Patched | Critic approved | Verified clean |
| --- | --- | --- | --- | --- | --- |
| hardcoded-jwt-secret | yes | claude-review | yes | yes | yes |
| weak-hash-passwords | yes | semgrep | yes | no | - |
| no-rate-limit-login | yes | claude-review | yes | no | - |
| sqli-login | yes | claude-review | yes | yes | yes |
| timing-unsafe-compare | yes | claude-review | yes | yes | yes |
| session-fixation | yes | claude-review | yes | yes | yes |
| insecure-cookie-flags | yes | claude-review | yes | yes | yes |
| jwt-decode-no-verify | yes | semgrep | yes | yes | yes |
| insecure-random-reset-token | yes | claude-review | yes | yes | yes |


LLM-only contributions in this repo: `hardcoded-jwt-secret`, `insecure-cookie-flags`, `insecure-random-reset-token`, `no-rate-limit-login`, `session-fixation`, `sqli-login`, `timing-unsafe-compare`
