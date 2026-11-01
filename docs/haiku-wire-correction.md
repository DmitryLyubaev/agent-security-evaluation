# Haiku request correction - 1 November 2026

The approved diagnostic follow-up captured HTTP400 `invalid_request_error` from the
Messages endpoint: Haiku 5.5 does not support the `speed` parameter. This applies even
when its value is `standard`. Generation request ID:
`req_011CgbfqPjTo6M6HnTvRRCnz`. The adapter included that unsupported field, while its
mocked transport accepted it. This was an adapter/test-contract defect.

The token-count request and Models access check succeeded, so those checks did not
prove the generation request's model-specific options were valid. Each of the two
live passes planned twelve cases, attempted B01 once, completed zero answers and
left eleven cases unrun. The first detailed error was not retained; the second
definitively establishes this wire rejection. Neither pass is a successful evaluation.

## Correction and regression checks

Generation and token-count bodies omit `speed`; Haiku uses its ordinary model behavior.
`service_tier=standard_only`, global inference, disabled thinking, medium effort and
all token/time/tool limits remain fixed. No fast/priority feature or sampling override
is introduced. The SDK version, case/prompt/rubric/lock bytes and tool contracts are
unchanged. The service-specific constraint is now enforced by the SDK HTTP fixture,
which returns the captured400 error when a generation includes `speed`.

The pinned SDK's Usage schema declares speed and cache counters nullable. For this
fixed Haiku profile, absent/null speed has no fast-mode surcharge; explicit `fast` is
still refused. Null optional cache counters use the same zero interpretation as already
absent counters. Boolean counts remain invalid, required token counts remain strict,
and positive cache categories still cause a profile-deviation stop after accounting.
Service tier and inference geography must still match the approved standard/global
profile. This does not change the rates or release an uncertain old charge.

## Lower frozen allowance

A proposal may freeze a smaller integer cap between the full per-call reserve
(1,051,136 micro-USD) and the existing maximum (2,000,000 micro-USD). It cannot raise
the maximum. Manifest, grant, ledger summary, remaining balance and dispatch checks
all bind the selected cap. A cap change requires a new exact owner-approved proposal;
no running allowance can be edited or reset.

This permits a proposed USD1.80 follow-up to fit within the already approved combined
USD4 envelope while both previous USD1.051136 reserves remain held:

`1.051136 + 1.051136 + 1.80 = 3.902272 USD`, below USD4 before tax/FX/credits.

Reallocation of unreserved balances and a third source-bound pass are **not approved**
merely by correcting code. Both previous grants remain stopped, every failed observation
stays visible, and provider invoice reconciliation remains outstanding.

## Preserved diagnostic attempt

Executed source: `f830a01b97fd9d9dc0c17b8cf5dd67b3d558fb54`.
Study: `48ea90fe47357325064df5b05656a42fd6298512754a063225594987fed1aae4`.
Grant: `codex-p25-diagnostic-9658d613-2026-11-01`.
Recorded active case time: about 1.344 seconds. One model GET, one free token count,
one generation attempt, zero tools and no completed answer or human label.

Its stopped ledger retains USD1.051136, with no supported usage receipt. The 400 is a
known request rejection, but this software does not infer an invoice settlement or
silently release the reserve. Actual charge remains unreconciled. Together with the
first attempt, retained uncertain exposure is USD2.102272, not a measured bill.

The diagnostic report, trace, grant and owner approval remain under the untouched
`.worktrees/provider-fix/private/` tree. Its closed archive contains 15 verified files
and a source bundle at `private/archive/diagnostic-2026-11-01-48ea90fe/`.
Archive receipt SHA-256:
`11d3dd046a513d591b323ca30259f8139880a7a6c103f6c7adb906813f6e4482`.
The first attempt's 16-file archive remains independently preserved.

Verification: 154 tests passed in 129.68 seconds, with Ruff check/format and whitespace
clean. One fresh focused review found no Critical, Important or Minor issues. The
review did not claim external success or authorize balance reallocation; both remain
subject to the concrete next packet and owner approval. No second review was run.

Public API reference: [speed is a model-dependent option](https://platform.claude.com/docs/en/api/messages/create).
The SDK accepting a typed argument is not proof that the selected model supports it.
