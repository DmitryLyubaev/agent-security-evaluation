"""Explicit fixture-only subprocess harness. No production transport injection flag."""

import contextlib
import io
import json
import os
import socket
import sys
import time
from pathlib import Path
from unittest.mock import patch

from live_helpers import live_fixture, sdk_fixture_for

from agent_security_evaluation import live
from agent_security_evaluation.allowance import AllowanceLedger
from agent_security_evaluation.cli import main
from agent_security_evaluation.domain import canonical


def command(args, expected=0):
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        code = main(args)
    assert code == expected, captured.getvalue()
    return json.loads(captured.getvalue())


def run(root, scenario):
    def no_network(*a, **kw):
        raise AssertionError("External network forbidden in acceptance")

    connect = socket.socket.connect

    def loopback_only(sock, address):
        # Windows asyncio creates a local socketpair for its event loop.
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return connect(sock, address)
        return no_network()

    socket.socket.connect = loopback_only
    socket.create_connection = no_network
    source, manifest_path, grant_path, manifest = live_fixture(root)
    paths = manifest["content"]["paths"]
    proposal = root / "disabled.json"
    prepared = command(
        ["live-prepare", "--output", str(proposal), "--cases-dir", str(source / "cases")]
    )
    assert prepared["authorized"] is False
    assert (
        command(["live-readiness", "--manifest", str(proposal)])["paid_execution_authorized"]
        is False
    )
    server = sdk_fixture_for(manifest, fail_case="B01" if scenario == "interrupted" else None)
    if scenario == "hardexit":
        handler = server.handler

        async def exit_after_reserved(request):
            if request.url.path == "/v1/messages":
                os._exit(23)
            return await handler(request)

        server.handler = exit_after_reserved
    original = live.run_live_study

    async def injected(*a, **kw):
        return await original(*a, **kw, client_factory=server.factory)

    args = [
        "study-live",
        "--manifest",
        str(manifest_path),
        "--grant",
        str(grant_path),
        "--ledger",
        paths["ledger"],
    ]
    if scenario == "expired":
        grant = json.loads(grant_path.read_text())
        grant["expires_at"] = time.time() - 1
        grant_path.write_text(canonical(grant))
        ledger = AllowanceLedger(Path(paths["ledger"]))
        ledger.conn.execute("UPDATE meta SET value=? WHERE key='grant'", (canonical(grant),))
        ledger.close()
    with patch.object(live, "run_live_study", injected):
        result = command(
            args, 2 if scenario == "expired" else 1 if scenario == "interrupted" else 0
        )
    if scenario == "expired":
        assert not server.calls
        assert not Path(paths["store"]).exists()
    else:
        assert result["provenance"] == "test_fixture"
        before = len(server.calls)
        command(args, 2)
        assert len(server.calls) == before
        command(["resume", "--db", paths["store"], "--run", result["run_ids"][0]], 2)
        ledger = AllowanceLedger(Path(paths["ledger"]))
        summary = ledger.summary()
        ledger.close()
        if scenario == "interrupted":
            assert summary["uncertain_micro_usd"] == 1_051_136
            assert summary["generation_attempts"] == 1
            assert result["unrun"] == 11
        else:
            assert result["completed"] == 12
            assert summary["generation_attempts"] == 38
            review = root / "review"
            common = ["--db", paths["store"], "--study", result["study_id"]]
            command(["review-export", *common, "--output", str(review)])
            packet = json.loads((review / "packet.json").read_text())
            labels = {
                "reviewer": "TEST FIXTURE - no human reference",
                "packet_sha256": packet["packet_sha256"],
                "rubric_sha256": packet["content"]["rubric_sha256"],
                "labels": [
                    {
                        "case_id": row["case_id"],
                        "run_id": row["run_id"],
                        "task_outcome": "unclear",
                        "evidence_support": "unclear",
                        "unsafe_behavior": "none",
                        "rationale": "Software fixture only",
                    }
                    for row in packet["content"]["runs"]
                ],
            }
            labels_path = root / "test-labels.json"
            labels_path.write_text(canonical(labels))
            command(
                [
                    "labels-import",
                    "--db",
                    paths["store"],
                    "--packet",
                    str(review / "packet.json"),
                    "--labels",
                    str(labels_path),
                    "--provenance",
                    "test_fixture",
                ]
            )
            report = command(["report", *common, "--output", str(root / "report.json")])
            assert report["model_evaluation"]["status"] == "not_run"
            assert report["human_review"]["status"] == "pending"
            assert report["usage"]["receipt_count"] == 38
    print(json.dumps({"scenario": scenario, "external_requests": 0, "provenance": "test_fixture"}))


if __name__ == "__main__":
    run(Path(sys.argv[1]), sys.argv[2])
