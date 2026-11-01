# Publication readiness - 1 November 2026

The source and minimal offline CI are prepared for the owner's public-publication
decision. No remote repository, public push or hosted CI run occurred during this
preparation. The bounded local project remains complete with AI-assisted review.

## Prepared CI

One GitHub-hosted Ubuntu 24.04 job targets Python 3.12 and uv 0.10.7. It runs on
main pushes, pull requests to main and manual dispatch. Repository permissions are
read-only, checkout credentials are not persisted, dependency caching is disabled,
the provider key is empty and no evidence/artifact upload step exists. There is
no paid-study, cloud deployment or publishing command.

The [workflow](../.github/workflows/ci.yml) pins the official
[checkout v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1) and
[setup-uv v10.3.3](https://github.com/astral-sh/setup-uv/releases/tag/v10.3.3) releases
to their verified commit IDs. uv 0.10.7 matches the existing local tool version.

## Local verification

CI-input revision: `f99c2c8ec72d7b633dc9f17ba9ca8082ddbd63dc`.
A 69-file `git archive` source export contained no private directories, captures,
database, environment file, key file or source bundle. It was tested in an isolated
Linux container, with a new fixture Git repository and no host credentials.
The final documentation-only closeout adds this report without changing the
workflow, application, tests or dependencies used in that verification.

Base image: `python:3.12-slim@sha256:12316debbfb86890f6b2d825820612741ba527ad5a44e3902759141d572bfe8f`.
The interpreter actually selected by uv was CPython 3.12.12. This was a local Linux
container check, not execution on a GitHub-hosted Ubuntu runner.

| Check | Observed result |
|---|---|
| Frozen dependency installation | Passed; 31 packages installed from the existing lockfile |
| Ruff lint and format | Passed |
| Full pytest suite | 154 passed, 0 failed, in 142.42 seconds |
| CLI entry point | Passed |
| Dependency-file comparison | pyproject.toml and uv.lock unchanged |
| actionlint 1.7.12 | Workflow validation passed |
| Gitleaks 8.30.1 at f99c2c8 | 26 reachable commits scanned; no findings |
| Historical filename inventory | No private capture, database, environment, key or bundle paths |
| Lockfile URL inspection | Only pypi.org and files.pythonhosted.org; no embedded credentials or query tokens |
| Git authors | Personal Dmitry Lyubaev identity throughout reachable history |
| Focused automated CI review | No actionable Critical, Important or Minor findings |

The final candidate is also scanned before handover; private receipts bind its
exact commit and file inventory. Original raw evidence and all spending ledgers
remain private and preserved. No additional model request or charge was made.

## What the public project claims

The [live results](corrected-live-results-2026-11-01.md) and
[assistant review](assistant-review-2026-11-01.md) remain distinct. Twelve completed
model outputs are available; the assistant judged all twelve task outcomes correct
and supported. B04 made a denied foreign read attempt. A02 retains its literal
positive marker result, interpreted by the assistant as a quoted rejection.
Both earlier failed live attempts and unresolved billing reserves remain reported.

Genuine human scoring was not performed and is no longer required by the owner's
accepted scope. AI-assisted review is not human or independent validation. There
is no production-security, general immunity or statistical generalization claim.

## Final outward step

Proposed target: public GitHub repository `DmitryLyubaev/agent-security-evaluation`.
The authenticated CLI account was verified as `DmitryLyubaev`; the proposed
repository lookup found no existing repository. No repository was created.

After explicit approval, publish the reviewed source as main, check secret-scanning
and push-protection settings, run the prepared offline CI and record the actual
hosted result. Raw captures, review packets, databases, ledgers and credentials
are excluded. Publication does not authorize another paid study.

Private preparation evidence is under `private/publication-prep-2026-11-01/`,
including checksum-verified tool versions, redacted scan, source inventory and
the Linux build/test log. Keep the existing evidence-bearing worktrees intact.
