# Publication preparation implementation plan

> **For agentic workers:** Use superpowers:executing-plans for inline execution. Steps use checkbox syntax for tracking.

**Goal:** Prepare source and offline CI for owner review before any public push.

**Architecture:** One GitHub-hosted Ubuntu 24.04 job uses Python 3.12 and uv 0.10.7,
the version already used locally. Install the frozen lockfile, then run Ruff,
pytest and CLI help without provider credentials. Keep private evidence and all
previous measured inputs unchanged.

**Tech stack:** Existing Python/FastAPI/SQLite application, GitHub Actions, uv, Ruff,
pytest, actionlint and a local redacted Gitleaks scan.

**Spec:** The existing project design and the owner's approval in chat to add
offline CI, check publication contents and finalize README/provenance/limitations.

## Constraints and decisions

- No public repository, push, hosted run, paid model call or cloud action in this task.
- AI-assisted review is accepted; do not reopen personal scoring as a requirement.
- One Linux job is sufficient. A platform matrix adds no necessary scope here.
- Pin checkout/setup-uv actions to official verified commit IDs; disable persisted
  checkout credentials and caches; use read-only repository permissions.
- Trigger on main pushes, pull requests to main and manual dispatch. Never use
  pull_request_target or a self-hosted runner; upload no captures/artifacts.
- Test from a source-only copy that contains no private captures or provider key.
- Do not change runtime, case, prompt, rubric, pyproject or lock bytes from 4911804.
- Preserve evidence worktrees, stopped ledgers and the two failed live observations.

## Review focus

Private files in Git history: scan all branches with redacted output and inspect
the final tracked/source-archive inventory. Credentials in dependency URLs: inspect
lockfile hosts and authentication/query components without printing secrets.
Linux portability: run the actual CI commands from a source-only Linux checkout.
Unsafe workflow context: validate with actionlint and review events/permissions.
Claims: identify local results and pending hosted verification separately.

## Task 1: Reviewable publication preparation

**Files:** Create `.github/workflows/ci.yml`; update `README.md`; create a dated
publication-readiness report. Update only Project 25 records in portfolio-plan.
No product interface or runtime behavior changes.

- [x] Add the single-job workflow and validate it with actionlint.
- [x] Scan the tracked tree and full reachable history for accidental credentials
  and private evidence; record only redacted findings and safe aggregates.
- [x] Export only tracked source and run frozen install, Ruff, all tests and CLI
  help on Linux without the original private directories or credentials.
- [x] Finalize the README and dated report with actual results, AI-assisted
  provenance, the literal A02 signal and preserved earlier failures.
- [x] Review the diff, verify unchanged frozen files and archive hashes, commit
  the prepared source, and update tracker/handover with the exact commit.

No tests that merely assert YAML text will be added. actionlint and executing the
real commands provide the meaningful checks for this configuration-only change.
Public creation/push and hosted CI remain the final approval step under RULES.md.
