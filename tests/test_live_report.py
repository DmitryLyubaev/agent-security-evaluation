"""Synthetic reporting inputs only. No generated files are measured live/human evidence."""

import asyncio
import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from live_helpers import live_fixture, sdk_fixture_for
from test_anthropic_provider import payload
from test_review_report import packet_and_labels
from test_study import freeze


@pytest.fixture(scope="module")
def report_template(tmp_path_factory):
    from agent_security_evaluation.live import run_live_study
    from agent_security_evaluation.store import Store

    prepared = live_fixture(tmp_path_factory.mktemp("live-report-template"))
    _, mp, gp, manifest = prepared
    paths = manifest["content"]["paths"]
    store = Store(Path(paths["store"]))
    server = sdk_fixture_for(manifest)
    summary = asyncio.run(
        run_live_study(
            store,
            mp,
            gp,
            Path(paths["ledger"]),
            Path(paths["evidence"]),
            client_factory=server.factory,
        )
    )
    store.close()
    return Path(paths["store"]), summary.study_id


@pytest.fixture
def simulated_live(tmp_path, report_template):
    from agent_security_evaluation.store import Store
    from agent_security_evaluation.study import get_study, save_study

    original, study_id = report_template
    shutil.copy(original, tmp_path / "simulated.sqlite3")
    store = Store(tmp_path / "simulated.sqlite3")
    study = get_study(store, study_id)
    # Exercise the live reporting branch using a private copied test input only.
    study["provenance"] = "live_model"
    for run_id in study["runs"].values():
        data = store.run_data(run_id)
        data["provenance"] = "live_model"
        store.save_run_data(data)
    save_study(store, study)
    yield store, study_id, tmp_path
    store.close()


def report(prepared):
    from agent_security_evaluation.report import build_report

    store, study_id, root = prepared
    return build_report(store, study_id, root / "report.json")


def change(prepared, update):
    from agent_security_evaluation.study import get_study, save_study

    store, study_id, _ = prepared
    study = get_study(store, study_id)
    update(study)
    save_study(store, study)


def test_live_packet_is_not_hardcoded_fake(simulated_live):
    packet, _, _ = packet_and_labels(simulated_live)
    assert json.loads(packet.read_text())["content"]["provenance"] == "live_model"
    result = report(simulated_live)
    assert result["provenance"] == "live_model"
    assert result["model_evaluation"]["status"] == "completed"
    assert result["usage"]["receipt_count"] == 38
    assert result["usage"]["cost"] == 0.00076


def test_partial_model_study_is_not_complete(simulated_live):
    change(simulated_live, lambda study: study["runs"].update(A08=None))
    result = report(simulated_live)
    assert result["model_evaluation"]["status"] == "partial"
    assert result["counts"]["unrun"] == 1


def test_missing_usage_is_not_zero_cost(simulated_live):
    change(simulated_live, lambda study: study.update(allowance_receipts=[]))
    usage = stored_usage(simulated_live)
    assert usage["cost"] is None
    assert usage["missing_receipts"] == 38
    assert usage["invoice_reconciliation"] == "not_reconciled"


def single_receipt(study, raw):
    study["allowance_receipts"] = [
        {"state": "settled", "amount": 999999, "receipt": json.dumps({"raw": raw})}
    ]
    study["allowance"]["generation_attempts"] = 1


def stored_usage(prepared):
    from agent_security_evaluation.report import usage_report
    from agent_security_evaluation.study import get_study

    return usage_report(get_study(prepared[0], prepared[1]))


def test_output_thinking_detail_not_double_billed(simulated_live):
    raw = payload()
    raw["usage"]["output_tokens_details"]["thinking_tokens"] = 10
    change(simulated_live, lambda study: single_receipt(study, raw))
    usage = stored_usage(simulated_live)
    assert usage["cost"] == 0.00002
    assert usage["output_tokens"] == 20 and usage["thinking_tokens"] == 10


def test_cache_tier_uses_total_input(simulated_live):
    raw = payload()
    raw["usage"]["input_tokens"] = 10
    raw["usage"]["cache_read_input_tokens"] = 100001
    change(simulated_live, lambda study: single_receipt(study, raw))
    usage = stored_usage(simulated_live)
    assert usage["cost"] == 0.005056
    assert usage["input_tokens"] == 100011


def test_test_fixture_labels_never_complete_live_review(simulated_live):
    from agent_security_evaluation.review import import_labels

    packet, labels, _ = packet_and_labels(simulated_live)
    import_labels(simulated_live[0], packet, labels, provenance="test_fixture")
    result = report(simulated_live)
    assert result["human_review"]["status"] == "pending"
    assert result["human_review"]["missing"] == 12


def test_all_actual_human_labels_complete_single_reviewer_status(simulated_live):
    from agent_security_evaluation.review import import_labels

    packet, labels, _ = packet_and_labels(simulated_live)
    import_labels(simulated_live[0], packet, labels, provenance="human")
    result = report(simulated_live)
    assert result["human_review"]["status"] == "completed"
    assert result["human_review"]["missing"] == 0
    assert result["human_review"]["reviewer_count"] == 1
    assert result["human_review"]["inter_rater_agreement"] is None


def test_partial_labels_and_disagreements_remain_visible(simulated_live):
    from agent_security_evaluation.review import import_labels

    packet, labels, body = packet_and_labels(simulated_live, count=1)
    body["labels"][0].update(unsafe_behavior="executed", rationale="Synthetic disagreement")
    labels.write_text(json.dumps(body))
    import_labels(simulated_live[0], packet, labels, provenance="human")
    review = report(simulated_live)["human_review"]
    assert review["status"] == "pending" and review["missing"] == 11
    assert review["comparisons"][0]["safety_disagreement"] is True


def test_fixture_study_never_claims_model_evaluation(simulated_live):
    change(simulated_live, lambda study: study.update(provenance="test_fixture"))
    result = report(simulated_live)
    assert result["provenance"] == "test_fixture"
    assert result["model_evaluation"]["status"] == "not_run"
    assert "fixture" in (simulated_live[2] / "report.md").read_text().lower()


def test_no_completed_output_cannot_complete_human_review(simulated_live):
    store, _, _ = simulated_live

    def empty(study):
        for rid in study["runs"].values():
            data = store.run_data(rid)
            data.update(status="error", final_text=None)
            store.save_run_data(data)

    change(simulated_live, empty)
    result = report(simulated_live)
    assert result["model_evaluation"]["status"] == "attempted_no_completed_output"
    assert result["human_review"]["status"] == "pending"


def test_empty_answers_never_become_reviewable_outputs(simulated_live):
    from agent_security_evaluation.review import export_review

    store, study_id, root = simulated_live

    def empty(study):
        for rid in study["runs"].values():
            data = store.run_data(rid)
            data["final_text"] = " \n\t"
            store.save_run_data(data)

    change(simulated_live, empty)
    export_review(store, study_id, root / "empty-packet")
    packet = json.loads((root / "empty-packet/packet.json").read_text())
    assert packet["content"]["runs"] == []
    result = report(simulated_live)
    assert result["human_review"]["eligible_completed"] == 0
    assert result["human_review"]["status"] == "pending"
    assert result["model_evaluation"]["status"] == "attempted_no_completed_output"


def test_legacy_offline_archive_reads_without_schema_or_byte_changes(tmp_path):
    from agent_security_evaluation.evidence import file_sha256
    from agent_security_evaluation.report import build_report
    from agent_security_evaluation.store import Store
    from agent_security_evaluation.study import get_study, run_offline_study, save_study

    # Build synthetic legacy input in isolation. Private measured archives are not
    # portable test dependencies and must never be required by a fresh checkout.
    _, _, manifest, _ = freeze(tmp_path)
    original = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(original) as connection:
        schema_path = Path(__file__).parent / "fixtures/offline-v1-schema.sql"
        connection.executescript(schema_path.read_text())
        schema = connection.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()
    store = Store(original)
    summary = asyncio.run(run_offline_study(store, manifest, tmp_path / "evidence"))
    study = get_study(store, summary.study_id)
    study.pop("provenance", None)  # Original offline studies had no top-level provenance.
    save_study(store, study)
    for run_id in study["runs"].values():
        data = store.run_data(run_id)
        for field in ("expected_provider", "pending_proposal_ids"):
            data.pop(field, None)
        store.save_run_data(data)
    store.close()
    sha = file_sha256(original)
    copied = tmp_path / "archive-copy.sqlite3"
    shutil.copy(original, copied)
    store = Store(copied)
    try:
        result = build_report(store, summary.study_id, tmp_path / "legacy.json")
        assert result["provenance"] == "offline_fake"
        assert result["counts"]["completed"] == 12
        assert result["usage"]["cost"] is None
        assert schema == [
            tuple(row) for row in store.conn.execute("SELECT sql FROM sqlite_master ORDER BY name")
        ]
    finally:
        store.close()
    assert file_sha256(original) == sha
    assert file_sha256(copied) == sha
