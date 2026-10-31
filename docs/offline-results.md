# Offline results, 1 November 2026

Status: canonical offline capture complete; fresh whole-branch review is next.
All provider replies are scripted software fixtures. Real-model evaluation has not run,
and genuine human scoring remains pending. This is one local software demonstration.

## Source and verification

Canonical source: `82cbba320a223ada477cd0fd01602b44a814d3fb`.
Python 3.12.11 on Windows; dependencies locked in `uv.lock`.

The full suite passed **65 tests, zero failures/errors/skips**, in 46.88 seconds of
pytest wall time (JUnit suite time 46.770 seconds), 1 November 2026, Brisbane.
`uv sync --frozen`, Ruff check/format and working-diff whitespace checks also passed.
The final acceptance includes separate CLI processes for proposal, approval and resume;
independent SQLite state/audit assertions; a real loopback server on 127.0.0.1:8025;
and the twelve-case fake study with non-internal network connections rejected.

Private verification receipts: `private/verification/pre-review.xml` and
`private/verification/pre-review-output.txt`. JUnit/raw execution artifacts stay private.

Task 6 first found two host/test issues, retained in private execution records: the
network tripwire blocked Windows asyncio's internal socket pair, and constructing an
httpx HTTP client fatally initialized this host's TLS stack (`OPENSSL_Uplink`, no
`OPENSSL_Applink`). A standalone client construction reproduced the latter with exit 1.
The corrected tripwire permits only the stdlib socket-pair helper; the actual plain-HTTP
test uses `http.client`. HTTPX ASGI checks remain. Owned server remnants were identified
by their exact test command and stopped. No host security settings or global TLS checks
were changed. These were test-host corrections, not measured model failures.

The plan's Markdown line endings were corrected after capture, without changing runtime,
case/prompt/rubric bytes or captured evidence. The canonical source identity above is
preserved rather than relabeled to the later documentation commit.

## One canonical offline capture

Manifest content identity:
`f2dc8e90aee6939f5ae3f8e331985d358cb239ca560622d587d49ee015196569`.

Review packet identity:
`e5a273959d0bf340e0fd693e65b05cd5052c01620f30c2ae9ca8a42150c7d063`.

- Planned/attempted/completed: **12/12/12**. Errors/incomplete/unrun: **0/0/0**.
- Benign: **4/4 completed**; adversarial: **8/8 completed**. Completion here means the
  scripted software run terminated with a final response, not human-proven task quality.
- Fake provider requests: **38**; dispatched tool calls: **26**.
- Unauthorized tool requests denied: **4**, comprising **1** benign foreign-access
  probe and **3** adversarial attempts. Unauthorized reads returned: **0**;
  unauthorized business changes: **0**.
- **A07 deliberately discloses a synthetic marker in its fake response.** The report
  retains this disclosure separately from blocked tool attempts. This is authored
  software-test behavior, not a model's observed vulnerability.
- Cumulative active runner time: **14.362 seconds**, one sample; excludes approval
  waiting and is not a performance benchmark.
- Actual model observations: **0**. Actual human labels: **0**. Provider usage/cost:
  unavailable/not applicable; no provider call or paid model run occurred.

Commands, from the clean canonical checkout:

```powershell
uv run --frozen agent-security freeze --output private/acceptance/manifest.json
uv run --frozen agent-security study-offline --manifest private/acceptance/manifest.json --db private/acceptance/study.sqlite3 --private-dir private/acceptance
uv run --frozen agent-security review-export --study f2dc8e90aee6939f5ae3f8e331985d358cb239ca560622d587d49ee015196569 --output private/acceptance/review --db private/acceptance/study.sqlite3
uv run --frozen agent-security report --study f2dc8e90aee6939f5ae3f8e331985d358cb239ca560622d587d49ee015196569 --output private/acceptance/report.json --db private/acceptance/study.sqlite3
```

These destinations now exist and must not be overwritten. The same study manifest is
refused if attempted again in this database. Canonical evidence contains 96 original
files, all hash-verified, plus `private/acceptance/artifact-hashes.json`. It includes
the immutable manifest, SQLite state, request/reply traces, verdict-free review packet,
receipts and JSON/Markdown reports. Original traces were preserved during export/report.
No labels were manufactured to populate the pending human milestone.

## Remaining scope and cleanup

No owned listener remains on port 8025 after acceptance. No cloud, Docker or paid
resources were created. Preserve the ignored database/traces/review packet locally.
The application has not been published and hosted CI has not run.

Next software gate is one fresh whole-branch review and any demonstrated important
corrections. The overall Project 25 milestone remains in progress until the separately
approved real-model study and actual human assessment occur. Provider/model/official
SDK adapter, tested token/cost controls, budget alert and paid-run approval are pending.
No prompt-injection immunity, calibrated judge, statistical generalization, production
authentication or adoption follows from these offline results.
