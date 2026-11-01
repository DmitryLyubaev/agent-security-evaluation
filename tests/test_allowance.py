import os
import subprocess
import sys
import time

import pytest
from test_anthropic_provider import payload


def approved_ledger(tmp_path, *, begin=True):
    from agent_security_evaluation.allowance import AllowanceLedger, pricing_snapshot
    from agent_security_evaluation.domain import digest

    ledger = AllowanceLedger(tmp_path / "allowance.sqlite3")
    proposal = ledger.prepare_allowance("a" * 64)
    approval = {
        "manifest_sha256": "a" * 64,
        "cap_micro_usd": 2_000_000,
        "prices_sha256": digest(pricing_snapshot()),
        "source_commit": "fixture-source",
        "approval_id": "TEST FIXTURE - no paid authority",
        "personal_account_confirmed": True,
        "account_id": "fixture-personal",
        "workspace_id": "fixture-workspace",
        "budget_alert_confirmed": True,
        "expires_at": time.time() + 3600,
        "evidence_origin": "test_fixture",
        "ledger_path": str(ledger.path),
        "store_path": str(tmp_path / "runs.sqlite3"),
        "evidence_dir": str(tmp_path / "evidence"),
    }
    ledger.authorize(approval)
    if begin:
        ledger.begin_study(proposal["manifest_sha256"])
    return ledger, approval


def reserve(ledger, case="B01", ordinal=1):
    ledger.permit_count(case, ordinal)
    return ledger.reserve(case, ordinal, run_id="run-" + case, request_sha256="b" * 64)


def test_disabled_or_expired_grant_refuses_before_dispatch(tmp_path, monkeypatch):
    from agent_security_evaluation.allowance import AllowanceLedger

    ledger = AllowanceLedger(tmp_path / "disabled.sqlite3")
    ledger.prepare_allowance("a" * 64)
    with pytest.raises(ValueError):
        reserve(ledger)
    ledger, approval = approved_ledger(tmp_path)
    monkeypatch.setattr(
        "agent_security_evaluation.allowance.time.time", lambda: approval["expires_at"] + 1
    )
    with pytest.raises(ValueError, match="expired"):
        reserve(ledger)


def test_full_context_reservation(tmp_path):
    ledger, _ = approved_ledger(tmp_path)
    item = reserve(ledger)
    assert item.micro_usd == 1_051_136
    assert ledger.summary()["cap_micro_usd"] == 2_000_000
    assert ledger.summary()["outstanding_micro_usd"] == 1_051_136
    assert ledger.summary()["remaining_micro_usd"] == 948_864


def test_actual_receipt_releases_only_unused_reservation(tmp_path):
    ledger, _ = approved_ledger(tmp_path)
    item = reserve(ledger)
    assert ledger.settle(item.reservation_id, payload()) == 20
    assert ledger.summary()["settled_micro_usd"] == 20
    assert ledger.summary()["outstanding_micro_usd"] == 0
    assert reserve(ledger, "B01", 2).micro_usd == 1_051_136


def test_timeout_keeps_reservation_and_stops(tmp_path):
    ledger, _ = approved_ledger(tmp_path)
    item = reserve(ledger)
    ledger.mark_uncertain(item.reservation_id, "provider_timeout")
    assert ledger.summary()["uncertain_micro_usd"] == 1_051_136
    with pytest.raises(ValueError):
        reserve(ledger, "B02")


def test_new_output_directory_does_not_reset_cap(tmp_path):
    from agent_security_evaluation.allowance import AllowanceLedger

    ledger, approval = approved_ledger(tmp_path)
    reserve(ledger)
    with pytest.raises(ValueError):
        ledger.prepare_allowance("c" * 64)
    other = AllowanceLedger(tmp_path / "another.sqlite3")
    other.prepare_allowance("a" * 64)
    with pytest.raises(ValueError, match="ledger_path"):
        other.authorize(approval)


def test_same_case_ordinal_cannot_resend(tmp_path):
    ledger, _ = approved_ledger(tmp_path)
    item = reserve(ledger)
    ledger.settle(item.reservation_id, payload())
    with pytest.raises(ValueError):
        reserve(ledger)
    with pytest.raises(ValueError):
        ledger.begin_study("a" * 64)


def test_count_and_generation_caps_persist(tmp_path):
    from agent_security_evaluation.allowance import AllowanceLedger

    ledger, _ = approved_ledger(tmp_path)
    for n in range(1, 7):
        item = reserve(ledger, ordinal=n)
        ledger.settle(item.reservation_id, payload())
    ledger.close()
    reopened = AllowanceLedger(tmp_path / "allowance.sqlite3")
    assert reopened.summary()["generation_attempts"] == 6
    assert reopened.summary()["count_attempts"] == 6
    with pytest.raises(ValueError):
        reserve(reopened, ordinal=7)


def test_alert_is_durable_before_next_dispatch(tmp_path):
    ledger, _ = approved_ledger(tmp_path)
    item = reserve(ledger)
    raw = payload()
    raw["usage"].update(
        input_tokens=0,
        output_tokens=0,
        cache_creation_input_tokens=1_000_000,
        cache_creation={"ephemeral_1h_input_tokens": 1_000_000, "ephemeral_5m_input_tokens": 0},
    )
    # A known but unrequested cache-write charge crosses USD1 and stops the study.
    ledger.settle(item.reservation_id, raw)
    assert ledger.summary()["alert_triggered"]
    assert ledger.summary()["settled_micro_usd"] == 1_000_000
    with pytest.raises(ValueError):
        reserve(ledger, "B03")


def test_unsupported_usage_or_price_change_halts(tmp_path):
    ledger, _ = approved_ledger(tmp_path)
    item = reserve(ledger)
    raw = payload()
    raw["usage"]["unknown_billable"] = 1
    with pytest.raises(ValueError):
        ledger.settle(item.reservation_id, raw)
    assert ledger.summary()["uncertain_micro_usd"] == 1_051_136
    with pytest.raises(ValueError):
        reserve(ledger, "B02")


def test_output_thinking_detail_not_double_billed():
    from agent_security_evaluation.allowance import parse_usage
    from agent_security_evaluation.anthropic_provider import LiveProfile

    raw = payload()
    raw["usage"]["output_tokens_details"]["thinking_tokens"] = 5
    assert parse_usage(raw, LiveProfile())["micro_usd"] == 20


def test_cache_tier_uses_total_input():
    from agent_security_evaluation.allowance import parse_usage
    from agent_security_evaluation.anthropic_provider import LiveProfile

    raw = payload()
    raw["usage"].update(input_tokens=10, cache_read_input_tokens=100_000, output_tokens=10)
    parsed = parse_usage(raw, LiveProfile())
    assert parsed["total_input_tokens"] == 100_010
    assert parsed["micro_usd"] == 5030


def test_two_processes_cannot_double_reserve(tmp_path):
    ledger, _ = approved_ledger(tmp_path)
    ledger.permit_count("B01", 1)
    ledger.permit_count("B02", 1)
    script = """import sys
from pathlib import Path
from agent_security_evaluation.allowance import AllowanceLedger
l=AllowanceLedger(Path(sys.argv[1]))
try:
 r=l.reserve(sys.argv[2],1,run_id='run-'+sys.argv[2],request_sha256='b'*64)
 print('reserved')
except ValueError:
 print('refused')
"""
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(ledger.path), case],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        for case in ("B01", "B02")
    ]
    outputs = [p.communicate(timeout=15) for p in processes]
    assert sorted(out.strip() for out, _ in outputs) == ["refused", "reserved"]
    assert ledger.summary()["outstanding_micro_usd"] == 1_051_136


def test_interrupted_process_retains_reservation(tmp_path):
    from agent_security_evaluation.allowance import AllowanceLedger

    ledger, _ = approved_ledger(tmp_path)
    ledger.permit_count("B01", 1)
    script = """import os,sys
from pathlib import Path
from agent_security_evaluation.allowance import AllowanceLedger
l=AllowanceLedger(Path(sys.argv[1]))
l.reserve('B01',1,run_id='run-B01',request_sha256='b'*64)
os._exit(23)
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(ledger.path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 23
    reopened = AllowanceLedger(ledger.path)
    assert reopened.summary()["outstanding_micro_usd"] == 1_051_136
    with pytest.raises(ValueError):
        reserve(reopened, "B02")


def test_changed_prices_cannot_authorize(tmp_path):
    from agent_security_evaluation.allowance import AllowanceLedger

    _, approval = approved_ledger(tmp_path / "original", begin=False)
    ledger = AllowanceLedger(tmp_path / "changed.sqlite3")
    ledger.prepare_allowance("a" * 64)
    approval.update(ledger_path=str(ledger.path), prices_sha256="changed")
    with pytest.raises(ValueError, match="price"):
        ledger.authorize(approval)
