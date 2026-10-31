import asyncio
import json
from dataclasses import replace

import pytest
from test_tools import kit


def setup_run(tmp_path, *, limits=None):
    from agent_security_evaluation.domain import Limits
    from agent_security_evaluation.provider import ModelReply, ScriptedFakeProvider
    from agent_security_evaluation.runner import advance_run, start_run

    store, ctx, _, _, approve, approver, call, _ = kit(tmp_path)
    run_id = start_run(store, ctx, [{"role": "user", "content": "Follow up"}], limits or Limits())
    replies = [
        ModelReply((call("read", "get_exception", {"exception_id": "A-100"}),)),
        ModelReply(
            (
                call(
                    "propose",
                    "propose_status_change",
                    {
                        "exception_id": "A-100",
                        "expected_version": 1,
                        "reason": "Request carrier follow-up.",
                        "evidence_ids": ["E-A1"],
                    },
                ),
            )
        ),
        ModelReply((call("apply", "apply_proposal", {"proposal_id": "$latest_proposal"}),)),
        ModelReply(final_text="Requested follow-up [E-A1]."),
    ]

    def advance(provider=None):
        return asyncio.run(
            advance_run(
                store, provider or ScriptedFakeProvider(replies), run_id, tmp_path / "traces"
            )
        )

    return store, run_id, advance, replies, approve, approver, ScriptedFakeProvider, ModelReply


def test_resume_preserves_limits_and_consumed_turn(tmp_path):
    store, run_id, advance, replies, approve, approver, provider, _ = setup_run(tmp_path)
    waiting = advance()
    assert waiting.status == "waiting_approval"
    assert waiting.model_requests == 2
    assert advance().model_requests == 2
    approve(store, waiting.pending_proposal_id, approver("reviewer-a", "A"), approve=True)
    from agent_security_evaluation.runner import advance_run
    from agent_security_evaluation.store import Store

    store.close()
    reopened = Store(tmp_path / "tools.sqlite3")
    done = asyncio.run(advance_run(reopened, provider(replies), run_id, tmp_path / "traces"))
    assert done.status == "completed"
    assert done.model_requests == 4
    assert done.tool_dispatches == 3
    assert reopened.get_record(run_id, "A-100").status == "follow_up_requested"
    assert done.provenance == "offline_fake"
    assert done.active_seconds >= waiting.active_seconds


def test_no_grant_resume_keeps_open(tmp_path):
    store, run_id, advance, _, approve, approver, *_ = setup_run(tmp_path)
    waiting = advance()
    approve(store, waiting.pending_proposal_id, approver("reviewer-a", "A"), approve=False)
    assert advance().status == "completed"
    assert store.get_record(run_id, "A-100").status == "open"


def test_batch_cannot_self_approve(tmp_path, monkeypatch):
    store, run_id, advance, replies, _, _, provider, _ = setup_run(tmp_path)
    from agent_security_evaluation.domain import ToolCall

    monkeypatch.setattr("agent_security_evaluation.tools.uuid.uuid4", lambda: "known-proposal")
    replies[1] = replace(
        replies[1],
        tool_calls=replies[1].tool_calls
        + (ToolCall("premature", "apply_proposal", {"proposal_id": "known-proposal"}),),
    )
    waiting = advance(provider(replies))
    assert waiting.status == "waiting_approval"
    assert store.events(run_id)[-1]["result"]["code"] == "approval_required"
    assert store.get_record(run_id, "A-100").status == "open"


@pytest.mark.parametrize(
    "limit,code",
    [
        ({"model_requests": 1}, "model_request_limit"),
        ({"tool_dispatches": 1}, "tool_dispatch_limit"),
    ],
)
def test_limits(tmp_path, limit, code):
    from agent_security_evaluation.domain import Limits

    _, _, advance, *_ = setup_run(tmp_path, limits=Limits(**limit))
    result = advance()
    assert result.status == "incomplete"
    assert result.error_code == code


def test_case_active_time_limit(tmp_path):
    from agent_security_evaluation.domain import Limits

    _, _, advance, _, _, _, _, reply = setup_run(tmp_path, limits=Limits(case_seconds=0.001))

    class Slow:
        async def complete(self, request):
            await asyncio.sleep(0.02)
            return reply(final_text="too late")

    result = advance(Slow())
    assert result.status == "incomplete"
    assert result.error_code == "case_time_limit"


@pytest.mark.parametrize("failure", ["timeout", "exception"])
def test_provider_error_and_timeout(tmp_path, failure):
    from agent_security_evaluation.domain import Limits

    _, _, advance, *_ = setup_run(tmp_path, limits=Limits(request_seconds=0.01))

    class Broken:
        async def complete(self, request):
            if failure == "timeout":
                await asyncio.sleep(1)
            raise RuntimeError("private provider text")

    result = advance(Broken())
    assert result.status == "error"
    assert result.error_code == ("provider_timeout" if failure == "timeout" else "provider_error")
    assert result.final_text is None
    assert result.model_requests == 1


def test_unknown_malformed_and_missing_usage(tmp_path):
    store, run_id, advance, _, _, _, provider, reply = setup_run(tmp_path)
    from agent_security_evaluation.domain import ToolCall

    responses = [
        reply((ToolCall("x", "export", {}), ToolCall("y", "get_exception", {"exception_id": 23}))),
        reply(final_text="No change"),
    ]
    done = advance(provider(responses))
    assert done.status == "completed"
    assert [e["result"]["code"] for e in store.events(run_id)] == [
        "unknown_tool",
        "invalid_arguments",
    ]
    assert store.run_data(run_id)["usage"] == [None, None]


def test_duplicate_call_ids_rejected(tmp_path):
    _, _, advance, replies, _, _, provider, _ = setup_run(tmp_path)
    replies[0] = replace(replies[0], tool_calls=replies[0].tool_calls * 2)
    assert advance(provider(replies)).error_code == "duplicate_call_id"


def test_ambiguous_reply_rejected(tmp_path):
    _, _, advance, replies, _, _, provider, _ = setup_run(tmp_path)
    replies[0] = replace(replies[0], final_text="also final")
    assert advance(provider(replies)).error_code == "invalid_reply"


def test_inflight_interrupt_never_resends(tmp_path):
    store, run_id, advance, *_ = setup_run(tmp_path)
    data = store.run_data(run_id)
    data.update(in_flight=True, model_requests=1)
    store.save_run_data(data)
    result = advance()
    assert result.status == "incomplete"
    assert result.error_code == "interrupted_request"
    assert result.model_requests == 1


def test_trace_write_failure(tmp_path):
    _, _, advance, *_ = setup_run(tmp_path)
    (tmp_path / "traces").write_text("file instead of directory")
    assert advance().error_code == "evidence_error"


def test_raw_trace_hash_and_exclusive_write(tmp_path):
    from agent_security_evaluation.evidence import verify_trace, write_trace

    path = tmp_path / "trace"
    sha = write_trace(path, "run1", 0, {"raw": "PRIVATE-CANARY"})
    raw_file = path / "run1-0000.jsonl"
    assert verify_trace(raw_file, sha)
    assert json.loads(raw_file.read_text())["raw"] == "PRIVATE-CANARY"
    with pytest.raises(FileExistsError):
        write_trace(path, "run1", 0, {"raw": "overwrite"})
    assert verify_trace(raw_file, sha)
