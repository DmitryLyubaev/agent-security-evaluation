import asyncio
import copy
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from live_helpers import live_fixture, sdk_fixture_for


def test_losing_claim_never_halts_or_overwrites_the_winner(tmp_path, monkeypatch):
    from agent_security_evaluation.allowance import AllowanceLedger
    from agent_security_evaluation.live import run_live_study
    from agent_security_evaluation.store import Store
    from agent_security_evaluation.study import get_study, save_study

    _, mp, gp, manifest = live_fixture(tmp_path)
    paths = manifest["content"]["paths"]
    store = Store(Path(paths["store"]))
    begin = AllowanceLedger.begin_study
    winner = {
        "study_id": manifest["manifest_sha256"],
        "runs": {"B01": "winner-run"},
        "marker": "winner evidence",
    }

    def lose(self, study_id):
        # Force the real two-claim interleaving immediately after the preflight checks.
        begin(self, study_id)
        save_study(store, winner)
        raise ValueError("grant_cannot_start_or_expired")

    monkeypatch.setattr(AllowanceLedger, "begin_study", lose)
    server = sdk_fixture_for(manifest)
    with pytest.raises(ValueError, match="grant_cannot_start"):
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
    assert get_study(store, manifest["manifest_sha256"]) == winner
    ledger = AllowanceLedger(Path(paths["ledger"]))
    assert ledger.summary()["state"] == "running"
    ledger.close()
    assert not server.calls
    store.close()


@pytest.mark.parametrize("ledger_state", ["available", "missing", "mismatched"])
def test_hard_exit_report_reads_bound_ledger_without_mutation(tmp_path, ledger_state):
    from agent_security_evaluation.evidence import file_sha256
    from agent_security_evaluation.report import build_report
    from agent_security_evaluation.store import Store
    from agent_security_evaluation.study import get_study, save_study

    child = Path(__file__).with_name("live_acceptance_child.py")
    result = subprocess.run(
        [sys.executable, str(child), str(tmp_path), "hardexit"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 23, result.stdout + result.stderr
    manifest = json.loads((tmp_path / "source/private/proposal.json").read_text())
    paths = manifest["content"]["paths"]
    store = Store(Path(paths["store"]))
    study_id = manifest["manifest_sha256"]
    study = get_study(store, study_id)
    assert "allowance" not in study
    # Synthetic copied test input to exercise live status; never a real model claim.
    study["provenance"] = "live_model"
    save_study(store, study)
    ledger = Path(paths["ledger"])
    if ledger_state == "missing":
        ledger.rename(ledger.with_suffix(".retained"))
    elif ledger_state == "mismatched":
        with sqlite3.connect(ledger) as connection:
            row = connection.execute("SELECT value FROM meta WHERE key='grant'").fetchone()
            grant = json.loads(row[0])
            grant["manifest_sha256"] = "0" * 64
            connection.execute("UPDATE meta SET value=? WHERE key='grant'", (json.dumps(grant),))
    if ledger_state != "available":
        report = build_report(store, study_id, tmp_path / "unavailable-ledger.json")
        assert report["usage"]["generation_attempts"] is None
        assert report["usage"]["outstanding_reserved_micro_usd"] is None
        assert report["usage"]["missing_receipts"] is None
        assert report["usage"]["cost"] is None
        assert report["usage"]["ledger_evidence"] == "unavailable"
        assert report["model_evaluation"]["status"] == "attempted_no_completed_output"
        assert ledger.exists() == (ledger_state == "mismatched")
        store.close()
        return
    before = file_sha256(ledger)
    report = build_report(store, study_id, tmp_path / "crash-report.json")
    assert report["usage"]["generation_attempts"] == 1
    assert report["usage"]["outstanding_reserved_micro_usd"] == 1_051_136
    assert report["usage"]["missing_receipts"] == 1
    assert report["usage"]["cost"] is None
    assert report["model_evaluation"]["status"] == "attempted_no_completed_output"
    assert file_sha256(ledger) == before
    store.close()


def test_all_proposals_in_one_reply_resolve_in_order_with_only_one_grant(tmp_path):
    import httpx2

    from agent_security_evaluation.live import run_live_study
    from agent_security_evaluation.store import Store

    _, mp, gp, manifest = live_fixture(tmp_path)
    paths = manifest["content"]["paths"]
    server = sdk_fixture_for(manifest)
    handler = server.handler
    generation_bodies = []

    async def several(request):
        response = await handler(request)
        if request.url.path == "/v1/messages":
            body = json.loads(request.content)
            generation_bodies.append(body)
            turns = sum(m["role"] == "assistant" for m in body["messages"])
            if server.case_index == 0 and turns == 1:
                raw = json.loads(response.content)
                duplicate = copy.deepcopy(raw["content"][0])
                duplicate["id"] = "propose-second-exact"
                other = copy.deepcopy(duplicate)
                other["id"] = "propose-third-other"
                other["input"]["reason"] = "Different request"
                raw["content"].extend([duplicate, other])
                return httpx2.Response(200, json=raw, headers=response.headers)
        return response

    server.handler = several
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
    b01 = result.run_ids[0]
    proposals = [
        store.get_proposal(e["result"]["data"]["proposal_id"])
        for e in store.events(b01)
        if e["call"]["name"] == "propose_status_change"
    ]
    assert len(proposals) == 3
    decisions = [
        store.conn.execute(
            "SELECT approved FROM decisions WHERE proposal_id=?", (proposal["proposal_id"],)
        ).fetchone()
        for proposal in proposals
    ]
    assert [None if row is None else bool(row[0]) for row in decisions] == [True, False, False]
    run = store.run_data(b01)
    assert run["model_requests"] == 4 and run["tool_dispatches"] == 5
    replay = generation_bodies[2]["messages"]
    results = [
        block
        for message in replay
        for block in message["content"]
        if block["type"] == "tool_result"
        and "proposal_id" in json.loads(block["content"]).get("data", {})
    ]
    assert len(results) == 3
    store.close()
