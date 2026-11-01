# Live provider facts checked 1 November 2026

These are planning inputs, not proof of personal account access or paid-run approval.
No provider API request, SDK installation or model evaluation was made for this research.

| Topic | Verified fact | Official source |
|---|---|---|
| Proposed model | `claude-haiku-5-5`, text/tool-capable, advertised 1M context | [Haiku 5.5](https://platform.claude.com/docs/en/models/haiku-5-5/overview) and [model comparison](https://platform.claude.com/docs/en/models/overview) |
| Pinning | Current dateless model IDs identify fixed snapshots; serving infrastructure can still change | [Model versioning](https://platform.claude.com/docs/en/about-claude/models/model-ids-and-versions) |
| Standard prices, USD per million | Up to 100,000 input tokens: input 0.10, output 0.50, 5m cache write 0.125, 1h write 0.20, cache read 0.01. Above that threshold: 0.50, 2.50, 0.625, 1.00, 0.05 respectively | [Haiku pricing](https://platform.claude.com/docs/en/models/haiku-5-5/overview) |
| Thinking | Haiku 5.5 accepts `thinking={"type":"disabled"}` at medium effort; omit sampling controls | [Thinking](https://platform.claude.com/docs/en/build-with-claude/thinking) and [model guidance](https://platform.claude.com/docs/en/models/haiku-5-5/overview) |
| SDK | Official Python SDK 2.3.0 is listed; SDK major 2 uses API version 2026-10-21. Async client supports the official aiohttp backend | [SDK versions](https://platform.claude.com/docs/en/cli-sdks-libraries/overview) and [Python SDK](https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python) |
| Retries/timeouts | SDK retries twice by default; explicitly set retries to zero and timeout to 30 seconds | [SDK controls](https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python) |
| Tool loop | Send client schemas, preserve assistant tool blocks, then matching tool-result blocks; the application executes tools | [Handle tool calls](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls) |
| Output bound | `max_tokens` limits generated output; standard-only capacity is selectable | [Messages reference](https://platform.claude.com/docs/en/api/messages/create) |
| Count endpoint | Token counting is free, rate-limited and an estimate, not a final bill | [Token counting](https://platform.claude.com/docs/en/build-with-claude/token-counting) |
| Billing alert | Console workspace settings offer spend limits and email notifications. Default-workspace spend-limit restrictions apply | [Workspace controls](https://support.claude.com/en/articles/9796807-create-and-manage-workspaces-in-the-claude-console) and [rate/spend limits](https://platform.claude.com/docs/en/api/rate-limits) |

## Recommended profile and estimate

The recommendation is one Haiku 5.5 study, not a model comparison. Sonnet 5.5 is a
credible alternative, but its minimum thinking configuration requires additional block
continuity handling for this application; see [Sonnet guidance](https://platform.claude.com/docs/en/models/sonnet-5-5/overview).
Haiku keeps the existing simple text/client-tool boundary and a small spending envelope.
It is not assumed to pass the cases or outperform any other model.

Proposed limits: twelve cases once each, six generation requests/case, input estimate
at most 8,192 tokens/request, `max_tokens=1024`, one concurrent case, no automatic retry.
At the small-prompt standard prices, 72 requests at both token bounds project
USD0.0958464 before tax/FX. This is arithmetic at nominal bounds, not a measured bill
or a guarantee that all cases will finish. Proposed cumulative project allowance: USD2.

For stronger dispatch protection than an estimated input count alone, reserve an entire
conservative context allowance per request: 1,048,576 input tokens at the maximum listed
input category rate of USD1/million, plus 1,024 output tokens at USD2.50/million. That is
USD1.051136. Settle from supported actual receipts and release only the unused portion.
Unknown charges retain the reservation and stop further generation. A local USD1 alert
uses settled/uncertain spend; ordinary unspent reservations are shown separately.

These chosen bounds rely on standard-tier pricing and the provider's documented context/
output contract. Verify model capabilities and dated prices before enabling the paid
grant; refuse any larger context, unrecognized charge class, fast/priority service or
price change. The USD2 allowance covers this application's gross token usage, excluding
tax, currency conversion and unrelated account activity. It is not invoice reconciliation.

The configured environment contains an Anthropic credential variable; only its presence
was checked. Ownership, selected workspace, model access and billing alert are unverified.
No credential value was inspected or placed in a document. Those checks belong to the
final paid-readiness handoff, after the implementation is reviewable.
