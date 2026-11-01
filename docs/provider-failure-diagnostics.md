# Provider failure diagnostics repair - 1 November 2026

The first live attempt retained only `provider_request_uncertain`. The provider
boundary caught the exception, saved a generic ledger code and re-raised it; the
runner then normalized the exception without preserving its class or HTTP evidence.
That application defect is reproduced and repaired on `codex/p25-provider-fix`.
The frozen failed study remains on its original worktree and allowance.

The repair records the failing stage (`token_count`, `generation` or `receipt`),
exception class, HTTP status and request ID when available, provider error type,
bounded redacted error text and a short exception-cause chain. It excludes raw SDK
request objects, response headers and unstructured HTTP error bodies. The current
client credential and bearer/API-key patterns are redacted before persistence.
The same safe diagnostic reaches the uncertain ledger row, hashed trace, saved run
and report. A response-parsing failure retains HTTP status/request ID separately
from the generation call, so it can be distinguished from an API rejection.

The financial behavior is unchanged: unknown acceptance retains the full reservation,
halts dispatch and never retries. Cancellation also preserves diagnostics and money,
including cooperative cancellation of the runner before it re-raises cancellation.
Malformed error fields use a safe fallback. Diagnostic formatting cannot bypass the
financial stop or replace the original provider exception.
No automatic zero-cost settlement is inferred from an HTTP error. Model/profile,
pricing, tools, case/prompt/rubric bytes, token/time bounds and SDK retries are unchanged.
No API key or external generation is used in the repair tests.

Tests reproduce HTTP 400/402/429/500 failures, malformed successful HTTP responses,
generation cancellation and report propagation. A real loopback HTTP server, through
the official SDK and HTTP transport, also completes and settles a valid response.
That checks an actual HTTP connection in addition to the existing mocked transport.
It does not prove the external provider will accept the next request.

The owner reported API credit available and no reached spend limit. No connected
Console browser was available for inspecting the original provider-side request.
The original detailed error cannot be reconstructed from the saved record, and the
successful local HTTP test does not establish the original upstream cause. Do not
claim that missing original information has been recovered or a paid rerun passed.

The original USD1.051136 uncertain reserve remains intact, with zero completed
outputs. No new charged request, grant reset or alteration of that study is part of
this repair. Any later diagnostic/live attempt needs its own concrete approval and
must retain the original failed observation and reserved exposure.

Verification: 143 tests passed in 130.16 seconds, including sixteen new failure/
transport regressions. One fresh focused review found two Important gaps (malformed
error types and runner cancellation); both were reproduced RED and fixed. No Critical
or Minor findings remain, and no second review was dispatched. Ruff/format and
whitespace checks pass. Only documentation/lint-comment changes followed the suite.
