# Project 25 live readiness - 1 November 2026

Implementation approval permits local coding and offline checks. It does not grant
paid execution. No measured model result or actual human label exists yet.

The final private proposal is `private/live-ready/proposal.json`. Its content hash
freezes source commit, source/lock/case/prompt/rubric bytes, runtime versions, translated
tools, prices, fixed profile, case order, limits and absolute evidence locations.
`private/live-ready/paid-packet.json` binds that proposal to the no-inference TLS
receipt and outstanding owner confirmations. Neither file is an active grant.
Any source/configuration/price/account/workspace change requires a new reviewable
proposal and explicit approval. Never reset an attempted allowance to obtain a retry.

## Fixed study and money boundary

- Direct Anthropic `claude-haiku-5-5`, SDK 2.3.0, API 2026-10-21.
- Thinking disabled, medium effort, automatic client-tool selection, nonstreaming,
  standard-only service, standard speed and global inference geography. No caching,
  server tools, sampling overrides, SDK/application retries or model fallback.
- B01-B04, then A01-A08, once each. Three existing tools and one existing transition.
  Only B01 may receive one exact predeclared fixture approval. This is deterministic
  application fixture authority, not human scoring.
- Six generation turns and twelve dispatched tools per case; 72 generation requests
  and 72 separate free token counts total. Each estimate must be at most 8,192 input
  tokens. Output cap 1,024. Count plus generation share the 30-second turn deadline;
  each case has 180 cumulative active seconds, excluding approval waiting.
- One granted free Models GET precedes generation. It checks model lifecycle/access,
  workspace, context/output limits and disabled-thinking/medium-effort support.
  The Models schema has no client-tool support flag; support is documented for the
  pinned model. Actual model tool choices remain unobserved until the study.
- USD2 gross token allowance before tax, FX and credits. Local durable warning at USD1.
  A provider budget email notification must also be confirmed before execution.
  Neither notification nor this ledger controls unrelated account usage or invoices.
- Every generation first reserves 1,051,136 micro-USD: 1,048,576 context tokens at
  the highest input-category rate plus 1,024 output tokens at the highest output rate.
  Supported receipts settle exact decimal rates, rounding each call upward to micro-USD.
  Only the unused reserve is released. Unknown acceptance/usage retains the full reserve
  and stops further generation. A process crash leaves a durable outstanding reservation.
- Prices are frozen in the manifest and [dated provider facts](research/2026-11-01-live-provider-facts.md).
  The nominal 72-turn small-prompt projection is USD0.0958464, not a measured bill.

## Native TLS result

The unauthenticated official-host Models GET returned HTTP 401 with certificate and
hostname verification enabled, and zero generation requests. This proves TLS only;
personal ownership, workspace/model access and billing notification are unconfirmed.

The proposed aiohttp extra fatally constructs an OpenSSL context during import on this
Windows host. The supported SDK default backend works with an explicit native
truststore context: anthropic 2.3.0, httpx2 2.16.0, truststore 0.10.5. No global TLS,
DLL, PATH or security setting was changed. Verification is never disabled.
The private receipt is `private/live-ready/tls-preflight.json`.

## Before asking for paid approval

Confirm that `ANTHROPIC_API_KEY` belongs to Dmitry's personal Console account, identify
the account and exact workspace, confirm Haiku access and the workspace's budget email
notification. Supply account/workspace identifiers and a nonsecret notification receipt,
never the key. Current proposal placeholders remain disabled until those facts exist.
Do not buy credits, enable auto-reload, raise limits or change a shared account.

From a clean reviewed checkout, prepare the proposal locally:

```powershell
uv run agent-security live-prepare --output private/live-ready/proposal.json
uv run agent-security live-readiness --manifest private/live-ready/proposal.json
```

`prepare_live(..., account=confirmed_facts)` accepts those explicit nonsecret account
facts when preparing the final proposal. The expected keys are `account_id`,
`workspace_id`, `personal_account_confirmed` and `budget_alert_confirmed`. Do not edit
an existing proposal in place. Re-freeze and obtain approval of its new digest.
The final paid request must state its exact packet/manifest digest, reviewed source,
personal account/workspace, USD2 allowance and 24-hour execution window.

After actual owner approval, a local operator prepares the separate allowance using
`AllowanceLedger.prepare_allowance(manifest_sha256)` and records the exact approval
with `authorize(approval)`. The grant must bind `manifest_sha256`, `source_commit`,
`prices_sha256`, `cap_micro_usd=2000000`, `approval_id`, both confirmed booleans,
`account_id`, `workspace_id`, `ledger_path`, `store_path`, `evidence_dir`,
`evidence_origin="live_model"` and an `expires_at` within 24 hours. Save the same grant
JSON at `private/live-ready/grant.json`. These local assertions rely on the trusted
operator; this portfolio demo does not authenticate the machine's owner.

Only then may the approved command read the key and construct transport:

```powershell
uv run agent-security study-live --manifest private/live-ready/proposal.json --grant private/live-ready/grant.json --ledger private/p25-live/allowance.sqlite3
```

Source, runtime, grant, paths, account, workspace, prices and expiry must match before
credential access. Another process cannot claim the grant, and a restart/new output
directory cannot resume or reset it. Preserve errors, missing receipts and later unrun
slots. Do not run an inference warm-up, paid retry, new grant or tuned case set.

## Human review and results

Export every completed output through `review-export`. The packet contains the trusted
task/policy, allowed evidence, actual tool events, committed state and final answer,
without expected outcomes or generated scores. It excludes raw provider headers and
reasoning. Dmitry personally supplies the three rubric axes with rationale for adverse
or unclear labels. `labels-import --provenance human` records those supplied labels;
an assistant must never invent human scores. Test labels use `test_fixture`.

Reports keep planned/attempted/completed/error/incomplete/unrun denominators, benign
and adversarial groups, attempts/denials/effects/disclosures, exact safety comparisons,
actual supported token categories, unknown charges and active latency separate.
Human review completes only with nonempty completed live output and human labels for
every eligible case. A single reviewer supplies no inter-rater agreement. Partial or
poor model outcomes are valid evidence; twelve synthetic cases imply no general
security guarantee. Record actual results later in a dated results document.

Original/corrected fake archives and the policy-retained offline worktree stay intact.
No archived Store schema migration is needed. The allowance uses a separate database.
Public source/evidence, hosted CI and provider account changes remain separately scoped.
