import json

import pytest


def kit(tmp_path):
    from agent_security_evaluation.domain import (
        Evidence,
        ExceptionRecord,
        ToolCall,
        TrustedApprover,
        TrustedContext,
    )
    from agent_security_evaluation.store import Store
    from agent_security_evaluation.tools import dispatch_tool, record_approval

    store = Store(tmp_path / "tools.sqlite3")
    ctx = TrustedContext("r1", "operator-a", "A")
    records = [
        ExceptionRecord("A-100", "A", "open", 1, (Evidence("E-A1", "document", "Delayed"),)),
        ExceptionRecord("B-200", "B", "open", 1, (Evidence("E-B1", "document", "FOREIGN"),)),
    ]
    store.seed_records("r1", records)
    store.seed_records("r2", records)

    def call(name, **args):
        return dispatch_tool(store, ctx, ToolCall("c1", name, args))

    def propose():
        return call(
            "propose_status_change",
            exception_id="A-100",
            expected_version=1,
            reason="Request carrier follow-up.",
            evidence_ids=["E-A1"],
        ).data["proposal_id"]

    return store, ctx, call, propose, record_approval, TrustedApprover, ToolCall, dispatch_tool


def test_read_own_account(tmp_path):
    store, ctx, call, *_ = kit(tmp_path)
    assert call("get_exception", exception_id="A-100").data["exception_id"] == "A-100"
    assert store.events(ctx.run_id)[-1]["result"]["ok"]


def test_foreign_read_returns_no_content(tmp_path):
    store, ctx, call, *_ = kit(tmp_path)
    foreign = call("get_exception", exception_id="B-200")
    missing = call("get_exception", exception_id="missing")
    assert foreign.code == missing.code == "access_denied"
    assert foreign.data == missing.data == {}
    assert "FOREIGN" not in json.dumps(foreign.data)
    assert len(store.events(ctx.run_id)) == 2


@pytest.mark.parametrize("extra", [{"actor_id": "other"}, {"approved": True}])
def test_strict_arguments_reject_extra_actor_and_approved_flag(tmp_path, extra):
    _, _, call, *_ = kit(tmp_path)
    assert call("get_exception", exception_id="A-100", **extra).code == "invalid_arguments"


def test_citations_belong_to_target(tmp_path):
    _, _, call, *_ = kit(tmp_path)
    result = call(
        "propose_status_change",
        exception_id="A-100",
        expected_version=1,
        reason="Follow up",
        evidence_ids=["E-B1"],
    )
    assert result.code == "invalid_evidence"


def test_forged_or_missing_grant_denies(tmp_path):
    store, _, call, propose, *_ = kit(tmp_path)
    proposal = propose()
    assert call("apply_proposal", proposal_id=proposal, approved=True).code == "invalid_arguments"
    assert call("apply_proposal", proposal_id=proposal).code == "approval_required"
    assert store.get_record("r1", "A-100").status == "open"


def test_wrong_approver_account_denies(tmp_path):
    store, _, _, propose, approve, approver, *_ = kit(tmp_path)
    with pytest.raises(ValueError, match="access_denied"):
        approve(store, propose(), approver("reviewer-b", "B"), approve=True)


@pytest.mark.parametrize("change", ["reason", "version"])
def test_altered_or_stale_proposal_denies(tmp_path, change):
    store, _, call, propose, approve, approver, *_ = kit(tmp_path)
    proposal = propose()
    approve(store, proposal, approver("reviewer-a", "A"), approve=True)
    if change == "reason":
        body = store.get_proposal(proposal)
        body["reason"] = "Altered"
        store.conn.execute("UPDATE proposals SET data=? WHERE id=?", (json.dumps(body), proposal))
        expected = "proposal_altered"
    else:
        record = store.get_record("r1", "A-100")
        store.conn.execute("UPDATE records SET version=2 WHERE run_id='r1' AND id='A-100'")
        assert record.version == 1
        expected = "stale_proposal"
    assert call("apply_proposal", proposal_id=proposal).code == expected


def test_foreign_run_proposal_denies(tmp_path):
    store, _, _, propose, approve, approver, tool, dispatch = kit(tmp_path)
    from agent_security_evaluation.domain import TrustedContext

    proposal = propose()
    approve(store, proposal, approver("reviewer-a", "A"), approve=True)
    result = dispatch(
        store,
        TrustedContext("r2", "operator-a", "A"),
        tool("c2", "apply_proposal", {"proposal_id": proposal}),
    )
    assert result.code == "access_denied"
    assert store.get_record("r2", "A-100").status == "open"


def test_grant_is_single_use(tmp_path):
    store, _, call, propose, approve, approver, *_ = kit(tmp_path)
    proposal = propose()
    approve(store, proposal, approver("reviewer-a", "A"), approve=True)
    assert call("apply_proposal", proposal_id=proposal).ok
    assert store.get_record("r1", "A-100").status == "follow_up_requested"
    assert call("apply_proposal", proposal_id=proposal).code == "approval_consumed"


def test_apply_audit_failure_rolls_back(tmp_path):
    store, _, call, propose, approve, approver, *_ = kit(tmp_path)
    proposal = propose()
    approve(store, proposal, approver("reviewer-a", "A"), approve=True)
    store.conn.execute(
        "CREATE TRIGGER reject_apply BEFORE INSERT ON events "
        "WHEN NEW.name='apply_proposal' BEGIN SELECT RAISE(ABORT,'audit down'); END"
    )
    with pytest.raises(Exception, match="audit down"):
        call("apply_proposal", proposal_id=proposal)
    assert store.get_record("r1", "A-100").status == "open"
    assert store.conn.execute("SELECT consumed FROM decisions").fetchone()[0] == 0


def test_unknown_tool(tmp_path):
    _, _, call, *_ = kit(tmp_path)
    assert call("export_secret", url="fixture://sink").code == "unknown_tool"
