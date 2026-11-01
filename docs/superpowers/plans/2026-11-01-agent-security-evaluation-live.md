# Project 25 Live-Ready Implementation and Study Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for the preserved Native execution method. Steps use checkbox (`- [ ]`) syntax for tracking. One fresh whole-branch review follows implementation.

**Goal:** Add one bounded real-model path and accurate live/human reporting, then prepare a concrete paid-run packet for separate owner approval.

**Architecture:** Keep the existing three-tool policy and local API. A lazy Anthropic adapter handles the wire protocol; a small separate SQLite allowance ledger guards every paid dispatch. The explicit live CLI freezes source/configuration and executes the unchanged twelve cases once; ordinary API/CLI commands remain offline. Existing review packets and reports gain truthful live provenance and actual usage handling.

**Tech Stack:** Existing Python 3.12/FastAPI/SQLite/pytest stack; official `anthropic==2.3.0`, API version 2026-10-21, supported HTTPX2 backend and explicit native truststore context. See the recorded backend ruling in the execution ledger and live-readiness runbook.

**Spec:** [Approved Project 25 design](../specs/2026-11-01-agent-security-evaluation-design.md), [completed offline plan](2026-11-01-agent-security-evaluation-offline.md), and [dated provider facts](../../research/2026-11-01-live-provider-facts.md).

**Status:** Native implementation approved by Dmitry on 1 November 2026. Tasks 1-4 complete; Task 5 acceptance passes and final verification/review is underway. Paid execution remains separately unapproved. The proposal language below records the planning basis; the backend adjustment is documented in the execution ledger and live-readiness runbook.

## Global Constraints

- This is a bounded personal portfolio demonstration, not a production service.
- Start from local main `3546648`; preserve its 69-test baseline and the original/corrected fake captures. Use a new `codex/` branch/worktree at execution; leave the policy-retained retired checkout untouched.
- Personal commits: `Dmitry Lyubaev <Dmitry.Lyubaev@gmail.com>`.
- Exactly the existing three model-selected tools and `open -> follow_up_requested` transition. No new model tools, cloud, judge, UI, hosted evaluation platform or other-project changes.
- Preserve `cases/`, `prompts/assistant.txt` and `rubric.json` bytes; freeze their hashes before live measurement. No tuning/replacement after observing results.
- Proposed provider/model: Anthropic direct API, `claude-haiku-5-5`; no automatic fallback to another model/provider.
- Proposed profile: `thinking={"type":"disabled"}`, medium effort, tool choice auto, standard-only service, nonstreaming text/client-tool responses, `max_tokens=1024`. Omit temperature/top-p/top-k, caching, server tools and fast/priority features.
- Twelve cases once, ordered B01-B04 then A01-A08. At most six generation requests and twelve tool dispatches/case, 72 generation requests/study, one case at a time, 30 seconds/request and 180 active seconds/case. No automatic SDK/application retries.
- Free token-count requests have a separate ceiling of 72, one per attempted generation request, and count toward the same active-time deadline. Reject an input estimate over 8,192 before generation. Counting does not authorize a paid call.
- After grant validation, permit one free model-metadata GET to confirm account access/capabilities before any generation. It cannot change the approved profile; a mismatch stops with all later slots unrun. No inference warm-up.
- Proposed allowance: USD2 gross API token usage before tax/FX/credits; local warning at USD1. A provider budget notification must be configured/confirmed before anything can bill, per RULES.md.
- No credentials in arguments, manifests, logs, packets or source. Read the real `ANTHROPIC_API_KEY` only after the paid entrypoint validates its grant; variable presence is not proof of personal ownership.
- Paid execution requires a later explicit approval of the final source/configuration digest, personal account/workspace and USD2 allowance. Plan approval permits implementation and offline checks, not inference.
- Keep the original threat model and reporting distinctions: attempts, denials, executed effects, disclosure, task quality and human judgments are separate evidence. Poor outcomes are valid; human labels cannot be supplied by an assistant.

## Proposed Approach

Use Haiku 5.5 for one narrow real-tool study: it supports a simple thinking-disabled
profile and keeps the budget small. Sonnet 5.5 is an alternative if the owner specifically
wants it, but adds thinking-block continuity work and higher rates. Do not implement
both. Haiku is a recommendation pending this plan's approval, not an agreed prior choice.

Reuse the shared runner and tools rather than writing a second agent. A separate allowance
file avoids schema changes to archived evidence databases. Add only the live protocol,
dispatch guard and reporting that the approved design needs. Continue Native execution;
the paid run remains a final separately approved operation after software verification.

## Review Focus

1. A real response can contain text plus tool blocks; preserve valid replay without calling it a final answer or discarding tool IDs. Task 1.
2. An interrupted request, second process or new output folder must not release uncertain money, reset the allowance or issue a second attempt. Task 2.
3. A live run passed to ordinary `resume` must not silently use the fake provider; wrong source/model/grant must refuse before key access/network. Task 3.
4. Every live proposal pause must resolve under the declared fixture policy within the original counters; repeated proposals cannot obtain extra approvals. Task 3.
5. Live/test/fake evidence, missing receipts and partial human labels must not become a completed or zero-cost study through hardcoded report fields. Task 4.

## File Structure

Paths are relative to `E:\Projects\agent-security-evaluation`.

| File | Responsibility |
|---|---|
| `src/agent_security_evaluation/anthropic_provider.py` | Fixed official SDK client, pure wire translation, typed response/usage parsing, TLS readiness |
| `src/agent_security_evaluation/allowance.py` | Project-owned proposal/grant, cumulative counters, atomic reservation/settlement and durable alert |
| `src/agent_security_evaluation/live.py` | Live manifest preparation, readiness/authorization boundary and one-pass study coordinator |
| `provider.py`, `runner.py`, `study.py` | Backward-compatible response metadata, frozen expected provider and shared loop/approval helper |
| `cli.py` | Live prepare/readiness commands and explicitly granted study entrypoint; existing ordinary paths stay offline |
| `review.py`, `report.py` | Source-bound packets, honest live/human status, usage and uncertainty reporting |
| `pyproject.toml`, `uv.lock` | One pinned official provider SDK and supported HTTP backend |
| `tests/test_anthropic_provider.py` | SDK-backed mocked HTTP/protocol/TLS checks without inference |
| `tests/test_allowance.py` | Real SQLite grant, money, race/crash and counter checks |
| `tests/test_live.py` | Manifest/key-access gates, twelve-case coordinator and live-resume isolation |
| `tests/test_live_report.py` | Receipt accounting, provenance, partial data and real-human-label reporting logic |
| `tests/test_live_acceptance.py` | Full mocked-provider CLI path, restart/uncertain charge and original evidence readback |
| `docs/live-readiness.md`, `docs/live-results.md` | Exact approval packet/runbook; later dated observed results |

Use fresh ignored `private/p25-live/` for run state/traces and
`private/p25-live/allowance.sqlite3` for cumulative authority. The final grant binds the
absolute ledger/run-store locations; selecting another folder never grants more money.
No migrations or writes to archived databases. Keep existing Store tables; new per-run/
study metadata fits their JSON documents, with legacy defaults only for legacy fake data.

## Task 1: Add the official adapter and demonstrate valid TLS separately

**Files:** Create `anthropic_provider.py`, `tests/test_anthropic_provider.py`; modify `provider.py`, `pyproject.toml`, `uv.lock`.

**Interfaces:**

- `LiveProfile` fixes model/API/SDK identity, normalized `provider_identity="anthropic:claude-haiku-5-5"`, output cap 1024, input-estimate cap 8192, medium effort/thinking disabled, standard-only service and fixed host `https://api.anthropic.com`.
- `encode_request(request: ModelRequest, profile: LiveProfile) -> dict` and `decode_response(payload: dict, profile: LiveProfile) -> ModelReply` are pure functions.
- Extend `ModelReply` with optional `provider_message`, `stop_reason` and `request_id`, retaining defaults for existing fake tests. Preserve provider text/tool blocks for replay; do not add required fields to old stored snapshots.
- Extend `ModelRequest` with optional `run_id`, `case_id` and `request_ordinal`, populated from trusted run state. Existing three-positional-argument construction stays valid for fake tests. The ordinal is the persisted next request number, never a value taken from model content.
- `make_client(api_key: str, profile: LiveProfile)` returns the pinned official `AsyncAnthropic` with supported HTTPX2 client with explicit native truststore context, validated TLS, retries zero and timeout 30. No configurable alternate host, proxy, telemetry exporter or implicit environment endpoint.
- `AnthropicProvider(client, profile, allowance)` implements `Provider.complete`; Task 2 supplies the allowance. Client creation and adapters are lazy so ordinary fake API/CLI paths never read a key or construct TLS clients.
- `tls_preflight(output_path: Path) -> dict` runs in a bounded subprocess without a real key/inference. It may make at most one certificate/hostname-validated unauthenticated GET to the official host; 401 proves TLS, not account/model access.

- [x] **Step 1: Write failing protocol tests.** Names/assertions: `test_real_sdk_encodes_three_client_tools` checks `input_schema` and all three unchanged function contracts; `test_text_plus_tools_is_not_final` preserves full assistant blocks/call IDs; `test_matching_tool_results_and_operator_decision` groups results under a valid user message, maps trusted approval context without treating retrieved text as authority, and never resends a fictional operator role to the API. `test_truncation_is_incomplete` preserves partial data but never fabricates a completed answer. `test_no_automatic_retry` proves one failed HTTP attempt; `test_wrong_model_or_unknown_content_refused` keeps the receipt and stops before dispatch. Mock at the official SDK HTTP boundary, not by replacing the adapter with a fake.
- [x] **Step 2: Run RED.** `uv run pytest tests/test_anthropic_provider.py -q` must show missing adapter behavior. Install/lock the proposed SDK only during this approved task; do not make paid probes.
- [x] **Step 3: Implement translation and the strict client.** Lift only trusted system instructions into `system`; preserve ordinary user, assistant and tool-result order. A tool-use stop produces calls plus replay metadata, with no final answer even if text blocks are present. Only a valid terminal text response becomes final. Preserve stop/refusal metadata and request ID. Reject unknown modes/blocks, service classes or model identity. Thinking is disabled, so do not request reasoning or expose any unexpected reasoning content to a packet.

At this task's boundary the pure codec/client are testable; paid `complete` remains
closed until Task 2's real allowance interface is wired. Its SDK-level tests use fake
credentials and mocked transport, never the configured personal key.
- [x] **Step 4: Verify GREEN and TLS readiness.** Run adapter tests and the existing suite. Run the separate no-inference TLS preflight and retain its outcome, including any native crash. The earlier `httpx.Client` OpenSSL crash is evidence, not proof that aiohttp fixes TLS. If the supported native path fails, complete independent offline tasks and leave paid readiness blocked; do not disable verification, change global DLL/PATH/security settings or silently add a cloud/container fallback.
- [x] **Step 5: Commit.** `feat: add pinned Anthropic adapter and TLS readiness`. Record exact resolved SDK/backend versions and no-inference preflight result.

## Task 2: Guard every generation with cumulative money and attempt reservations

**Files:** Create `allowance.py`, `tests/test_allowance.py`; integrate the guard in `anthropic_provider.py`.

**Interfaces:**

- `AllowanceLedger(path: Path)` owns a fresh SQLite file and never touches another project's ledger.
- `prepare_allowance(manifest_sha256: str, cap_micro_usd: int = 2_000_000) -> dict` creates a disabled proposal; `authorize(approval: dict) -> str` records a trusted operator grant only after actual owner approval. It binds manifest/source/model/prices/account/workspace, ledger/store paths and a 24-hour expiry.
- `begin_study(manifest_sha256: str) -> None` atomically claims the grant once; a second executor or restart cannot start another paid pass. `permit_count(case_id: str, request_ordinal: int) -> None` enforces the free count-request ceiling.
- `reserve(case_id: str, request_ordinal: int, *, run_id: str, request_sha256: str) -> Reservation`; `settle(reservation_id: str, receipt: dict) -> int`; `mark_uncertain(reservation_id: str, reason: str) -> None`; `summary() -> dict` exposes settled, unspent reserved, uncertain reserved and remaining amounts separately. Bind each case to one run and each ordinal to one request digest. Amounts are integer micro-USD, rounded up from exact decimal rates.
- `parse_usage(payload: dict, profile: LiveProfile) -> dict` preserves exclusive input/cache categories and inclusive output. Thinking breakdown is included in output, never billed twice.
- Frozen conservative context bound: 1,048,576 tokens, subject to preflight capability confirmation. Highest listed input-category rate USD1/million plus output USD2.50/million at 1024 tokens gives a per-call reservation of **1,051,136 micro-USD**. Never substitute a token-count estimate for this money reservation.

- [x] **Step 1: Write failing real-SQLite tests.** `test_disabled_or_expired_grant_refuses_before_dispatch`, `test_full_context_reservation`, `test_two_processes_cannot_double_reserve`, `test_actual_receipt_releases_only_unused_reservation`, `test_timeout_keeps_reservation_and_stops`, `test_new_output_directory_does_not_reset_cap`, `test_same_case_ordinal_cannot_resend`, `test_count_and_generation_caps_persist`, `test_alert_is_durable_before_next_dispatch`, `test_unsupported_usage_or_price_change_halts`.

```python
assert reservation.micro_usd == 1_051_136
assert ledger.summary()["cap_micro_usd"] == 2_000_000
# A normal small receipt settles a small actual amount; the unused reserve is released.
assert settled_micro_usd < reservation.micro_usd
# Unknown network acceptance retains the full amount and stops all later generation.
assert ledger.summary()["uncertain_micro_usd"] == 1_051_136
assert next_dispatch_refused
```

- [x] **Step 2: Run RED.** `uv run pytest tests/test_allowance.py -q` must reproduce missing money/counter protection.
- [x] **Step 3: Implement the small ledger and receipt settlement.** Use `BEGIN IMMEDIATE`; persist reservation before generation HTTP. Validate the grant and remaining full-context allowance before permitting the preceding free count. Require `settled + uncertain + outstanding + next_reservation <= cap`. Unknown acceptance/usage stops the entire paid study without releasing money. No automatic retries, resets or new grants to retry a measured case. Recognized input/cache tokens use the frozen tier-specific rates; inclusive output includes thinking detail. Choose price tier from total input, not uncached input alone. No caching/server tools are requested; unexpected known charge categories are accounted then halt, unknown ones keep the reservation. Validate standard service/speed, token bounds and model identity before release. Emit one durable local alert at settled/uncertain USD1; display ordinary reservations separately from actual charges.
- [x] **Step 4: Run GREEN.** Run allowance/adapter tests with fake keys and network tripwires. A subprocess interrupted after reservation must leave a reserved/uncertain row and refuse a resend after reopen. This is tested dispatch accounting, not a claim of invoice reconciliation or unrelated-account cost control.
- [x] **Step 5: Commit.** `feat: enforce Project 25 live allowance and uncertain-charge stop`.

## Task 3: Freeze and orchestrate the single real-model study through one entrypoint

**Files:** Create `live.py`, `tests/test_live.py`; modify `runner.py`, `study.py`, `cli.py` with shared helpers.

**Interfaces:**

- `prepare_live(profile: LiveProfile, output_path: Path) -> dict` writes a disabled proposal with exact source/lock/SDK/API, original case/prompt/rubric hashes, provider-translated tool schemas, ordered IDs, caps, prices, ledger/store paths and expiry policy. It reads no key and makes no request.
- `validate_live_authority(manifest_path: Path, grant_path: Path, ledger_path: Path) -> dict` verifies all identities before opening credentials or transport.
- `run_live_study(store: Store, manifest_path: Path, grant_path: Path, ledger_path: Path, evidence_dir: Path) -> StudySummary` is async and executes only the frozen order once.
- Extend `start_run` with keyword-only `expected_provider="offline_fake"` and `provenance="offline_fake"`. The runner verifies the frozen expected identity instead of accepting any provider. `decode_response` checks the raw model ID and emits Task 1's normalized provider identity. Old fake captures remain readable without mutation. Allow `StudySummary.run_ids` to contain `None` for planned/unrun slots without changing existing completed fake summaries.
- Extract `resolve_fixture_approval(store: Store, case: CaseSpec, proposal_id: str, *, prior_grants: int) -> str` from the existing coordinator. Only B01 can obtain one exact proposal-bound fixture grant; all other proposals are withheld. Model-generated approval is never authority.
- CLI additions: `live-prepare --output PATH`, `live-readiness --manifest PATH`, and granted `study-live --manifest PATH --grant PATH --ledger PATH`. No live HTTP route. Existing `run`, `serve`, `study-offline` stay fake; ordinary `resume` rejects live runs before creating a fake provider.

- [x] **Step 1: Write failing integration tests.** `test_wrong_source_profile_or_grant_refuses_before_key_access`; `test_ordinary_resume_never_switches_live_to_fake`; `test_model_selects_all_tools_from_real_shaped_replies`; `test_each_live_proposal_pause_resolves_with_original_counters`; `test_b01_only_one_exact_grant`; `test_repeat_case_or_changed_manifest_refused`; `test_interrupted_call_retains_error_and_unrun_slots`; `test_estimated_input_over_cap_never_generates`. Test doubles are explicitly marked fixture evidence, not measured model results.
- [x] **Step 2: Run RED.** `uv run pytest tests/test_live.py -q` must fail on missing live orchestration/gates.
- [x] **Step 3: Implement the frozen coordinator.** Record all twelve planned slots before dispatch. After authority validation, the one metadata GET checks access, thinking/tool support and the conservative context bound; no match means no generation. Loop through proposal pauses until the case is terminal or its original bounds stop it; never reset counters or leave an uncounted second pause. The first paid message belongs to B01, not an unreported warm-up. The model chooses tools naturally, without scripted reads or forced tool calls. On uncertain charge stop the study, preserve the error and mark later cases unrun. Invalid/truncated final output remains incomplete, not a favorable retry. Persist real provider identity, request IDs, exact stop reasons, traces, usage receipts and grant/manifest identities. Enforce the same deadlines over count+generation; only granted live execution reads the real key.
- [x] **Step 4: Run GREEN.** Run Task 1-3 tests and original runner/API checks. An ungranted `study-live` still exits 2 with no key/transport/storage side effect. A full official-SDK mocked study stays labeled `test_fixture`; no test creates a canonical live claim. The existing real loopback API test remains fake and passes.
- [x] **Step 5: Commit.** `feat: add explicitly granted single-pass live study coordinator`.

## Task 4: Report live behavior, actual usage and genuine human scores accurately

**Files:** Modify `review.py`, `report.py`; create `tests/test_live_report.py`.

**Interfaces:**

- Consume frozen provenance (`offline_fake`, `test_fixture`, `live_model`), actual provider receipts and Task 2 allowance summary. Keep existing export/import/report function signatures unless an optional read-only ledger argument is required.
- `model_evaluation.status`: `not_run`, `partial`, `completed`, or `attempted_no_completed_output`, derived from actual provenance/outcomes. Completed text is not automatically a correct task.
- Live usage reports expose supported token categories, receipt-calculated gross USD, uncertain reserved USD, missing receipts and unreconciled invoice status. Fake reports retain their existing unknown/not-applicable fields.
- Human review completes only for nonempty eligible live output with actual owner-supplied human labels for every completed case. Fixture labels and human-origin labels on fake data cannot complete the live milestone. Preserve original labels/corrections and exact unsafe categories/diversion comparisons.

- [x] **Step 1: Write failing report regressions.** `test_live_packet_is_not_hardcoded_fake`; `test_partial_model_study_is_not_complete`; `test_missing_usage_is_not_zero_cost`; `test_output_thinking_detail_not_double_billed`; `test_cache_tier_uses_total_input`; `test_test_fixture_labels_never_complete_live_review`; `test_all_actual_human_labels_complete_single_reviewer_status`; `test_partial_labels_and_disagreements_remain_visible`; `test_legacy_archives_read_without_schema_or_byte_changes`. The label fixture simulates import logic and is never published as actual human work.
- [x] **Step 2: Run RED.** `uv run pytest tests/test_live_report.py -q` must expose the current hardcoded fake/pending/cost behavior.
- [x] **Step 3: Implement provenance-aware reports and packets.** Keep the trusted instructions/disclosure policy and verdict-free packet from the offline correction. Do not export credential/header/reasoning content. Score or compare human labels only after explicit import; do not prefill scores or treat machine expectations as human references. Include all denominators and unavailable outputs. If every provider request errors, there is no completed model/human evidence; record that limit instead of claiming a finished validation. A poor quality/security result with reviewable outputs is valid evidence.
- [x] **Step 4: Run GREEN.** Run live-report and original review/report tests. Read archived original/corrected fake databases using safe copied/read-only fixtures and confirm their input-file hashes remain unchanged. Inspect generated sample live-fixture and fake reports for clearly different status/usage wording.
- [x] **Step 5: Commit.** `feat: separate live evidence and actual human review in reports`.

## Task 5: Verify readiness and hand over the concrete paid packet

**Files:** Create `tests/test_live_acceptance.py`, `docs/live-readiness.md`; update README and the tracker/handover. Do not create measured results before a real run.

**Interfaces:** Consumes Tasks 1-4. No new subsystem or hosting.

- [ ] **Step 1: Write subprocess acceptance tests.** Run the official-SDK mocked twelve-case path through prepare/grant-fixture/study/export/test-label/report. Reopen the ledger after an interrupted request and prove no paid resend, cap reset or fake/live switch. Check ordinary API/CLI cannot reach credentials or live transport. Verify a changed source/configuration and expired grant fail before network. If existing tests already cover a scenario, record that coverage without adding an unnecessary implementation change.
- [ ] **Step 2: Run and inspect acceptance.** `uv run pytest tests/test_live_acceptance.py -q` passes with no external generation. The no-inference TLS result is a separate readiness receipt, not a model observation.
- [ ] **Step 3: Run required checks.** `uv sync --frozen`, Ruff check/format, full `uv run pytest -q`, whitespace and source-identity checks. Preserve the 69 existing tests plus new meaningful checks. Run one fresh whole-branch review and one bounded correction pass if needed; do not repeat reviews or canonical fake studies merely to improve appearances.
- [ ] **Step 4: Prepare the final disabled paid packet from clean reviewed source.** Include exact source/config/price hashes, personal account/workspace identity to be confirmed, expected capabilities from the dated official model page, actual no-inference TLS receipt, twelve IDs/order, token/attempt/time caps, USD2 proposal, USD1 local alert, provider notification receipt, fresh ledger/store paths and the human review procedure. Prices/access/configuration changes invalidate the packet. No API key or secret value is included. Owner confirmation of personal ownership/Haiku access and budget notification, plus the 24-hour approval window, precede grant activation; the one granted metadata GET verifies capabilities again before generation.
- [ ] **Step 5: Commit and hand off.** `docs: record live readiness and disabled paid-run proposal`. Update tracker/handover with actual implementation/check status. Ask for paid execution only now, using the exact packet digest and USD2 allowance. Implementation approval alone never enables it. Keep source publication/CI and provider account/admin changes separately authorized.

## Later Operator Runbook: Not Authorized by This Plan's Preparation

After explicit approval of the final packet, confirm the personal account/key/workspace
and provider email notification through the owner's Console. Notifications are a
prerequisite, not a promise of instant cutoff; the local ledger controls project dispatch.
Do not buy credits, enable auto-reload, raise account limits or modify shared workspaces
without separate authorization. No allowance from Project 13/15 carries over.

Enable the exact grant, run the twelve cases once, and preserve all calls, receipts,
denials, effects, partial/error/unrun cases and the allowance. No paid smoke test before
B01, favorable retry, model switch or case/prompt retuning follows automatically.

Export the live packet without verdicts. Dmitry must personally score every completed
output on the agreed three axes with rationale for adverse/unclear cases. An assistant
may explain the rubric and import supplied labels, never invent or submit human scores.
Missing participation remains pending. Report one reviewer and no inter-rater agreement.

Write a dated report with actual model/version, samples, task completion/quality,
adversarial attempts/denials/effects/disclosures, human assessments/disagreements,
usage-based cost/latency and limits. Recheck all private evidence hashes and archive
source/configuration. Stop owned services and keep original failed outcomes. A bad
result is valid; no production or general prompt-injection-immunity claim follows.
Public source/evidence and hosted CI remain optional separately approved actions.

## Self-Review and Execution Handoff

Coverage: Task 1 handles official protocol/TLS, Task 2 protects money/attempts, Task 3
freezes and executes one bounded study, Task 4 separates real/fake/human evidence,
Task 5 validates the software and produces the concrete approval packet. Each Review
Focus input has a named owning test. Interface metadata extends existing JSON rather
than migrating archived databases; fake defaults remain fake and never upgrade evidence.

Preserve Native execution for these five tightly coupled tasks and one fresh final
review. Owner review of this plan is the next step. The model/profile, budget proposal
and execution method can be approved together; an actual paid run needs its later
source-bound approval after the implementation and readiness packet exist.
