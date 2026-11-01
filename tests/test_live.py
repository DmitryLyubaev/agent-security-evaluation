import asyncio
import json
from pathlib import Path

import pytest
from live_helpers import live_fixture, sdk_fixture_for


def execute(prepared, **kwargs):
    from agent_security_evaluation.live import run_live_study
    from agent_security_evaluation.store import Store

    _, mp, gp, manifest = prepared
    paths = manifest["content"]["paths"]
    server = sdk_fixture_for(manifest, **kwargs)
    store = Store(Path(paths["store"]))
    result = asyncio.run(
        run_live_study(
            store,
            mp,
            gp,
            Path(paths["ledger"]),
            Path(paths["evidence"]),
            client_factory=server.factory,
        )
    )
    return store, result, server


@pytest.mark.parametrize("changed", ["source", "profile", "grant"])
def test_wrong_source_profile_or_grant_refuses_before_key_access(tmp_path, monkeypatch, changed):
    from agent_security_evaluation.live import validate_live_authority

    root, mp, gp, manifest = live_fixture(tmp_path)

    def tripwire(*args, **kwargs):
        raise AssertionError("key access forbidden")

    monkeypatch.setattr("os.getenv", tripwire)
    if changed == "source":
        (root / "src/agent_security_evaluation/provider.py").write_text("changed")
    elif changed == "profile":
        manifest["content"]["profile"]["output_tokens"] = 999999
        mp.write_text(json.dumps(manifest))
    else:
        body = json.loads(gp.read_text())
        body["workspace_id"] = "foreign"
        gp.write_text(json.dumps(body))
    with pytest.raises(ValueError):
        validate_live_authority(mp, gp, Path(manifest["content"]["paths"]["ledger"]))


def test_model_selects_all_tools_from_real_shaped_replies(tmp_path):
    prepared = live_fixture(tmp_path)
    store, result, server = execute(prepared)
    assert (result.planned, result.completed, result.errored, result.unrun) == (12, 12, 0, 0)
    assert result.provenance == "test_fixture"
    events = [e for rid in result.run_ids for e in store.events(rid)]
    assert {"get_exception", "propose_status_change", "apply_proposal"}.issubset(
        {e["call"]["name"] for e in events}
    )
    assert server.calls[0].startswith("/v1/models/")
    assert sum(p == "/v1/messages" for p in server.calls) == 38
    assert store.get_record(result.run_ids[0], "A-100").status == "follow_up_requested"


def test_each_live_proposal_pause_resolves_with_original_counters(tmp_path):
    store, result, _ = execute(live_fixture(tmp_path), repeat_proposal=True)
    assert result.completed == 12
    b02 = store.get_run(result.run_ids[1])
    assert b02.model_requests == 4
    assert store.get_record(result.run_ids[1], "A-100").status == "open"


def test_b01_only_one_exact_grant(tmp_path):
    from agent_security_evaluation.domain import ToolCall, TrustedContext
    from agent_security_evaluation.store import Store
    from agent_security_evaluation.study import load_cases, resolve_fixture_approval
    from agent_security_evaluation.tools import dispatch_tool

    root, _, _, _manifest = live_fixture(tmp_path)
    case = next(c for c in load_cases(root / "cases") if c.case_id == "B01")
    store = Store(tmp_path / "approval.sqlite3")
    store.seed_records("run1", case.record_objects())
    context = TrustedContext("run1", "operator-a", "A")
    for index in range(2):
        result = dispatch_tool(
            store,
            context,
            ToolCall(
                str(index),
                "propose_status_change",
                {
                    "exception_id": "A-100",
                    "expected_version": 1,
                    "reason": "Request carrier follow-up.",
                    "evidence_ids": ["E-A1"],
                },
            ),
        )
        assert resolve_fixture_approval(
            store, case, result.data["proposal_id"], prior_grants=index
        ) == ("approved" if index == 0 else "withheld")


def test_repeat_case_or_changed_manifest_refused(tmp_path):
    from agent_security_evaluation.live import run_live_study

    prepared = live_fixture(tmp_path)
    store, _result, server = execute(prepared)
    _, mp, gp, manifest = prepared
    paths = manifest["content"]["paths"]
    before = len(server.calls)
    with pytest.raises(ValueError):
        asyncio.run(
            run_live_study(
                store,
                mp,
                gp,
                Path(paths["ledger"]),
                Path(paths["evidence"]),
                client_factory=server.factory,
            )
        )
    assert len(server.calls) == before


def test_interrupted_call_retains_error_and_unrun_slots(tmp_path):
    store, result, _ = execute(live_fixture(tmp_path), fail_case="B01")
    assert (result.attempted, result.completed, result.errored, result.unrun) == (1, 0, 1, 11)
    from agent_security_evaluation.study import get_study

    study = get_study(store, result.study_id)
    assert study["allowance"]["uncertain_micro_usd"] == 1_051_136


def test_estimated_input_over_cap_never_generates(tmp_path):
    _, result, server = execute(live_fixture(tmp_path), oversized=True)
    assert result.completed == 0 and result.unrun == 11
    assert "/v1/messages" not in server.calls


def test_ordinary_resume_never_switches_live_to_fake(tmp_path, monkeypatch, capsys):
    from agent_security_evaluation.cli import main

    prepared = live_fixture(tmp_path)
    store, result, _ = execute(prepared)
    store.close()
    paths = prepared[3]["content"]["paths"]

    def tripwire(*a, **kw):
        raise AssertionError("fake provider must not be selected")

    monkeypatch.setattr("agent_security_evaluation.cli.fake_provider", tripwire)
    assert main(["resume", "--run", result.run_ids[0], "--db", paths["store"]]) == 2
    assert "live_requires" in capsys.readouterr().err
