import asyncio
import json

import httpx2
import pytest
from live_helpers import live_fixture
from test_allowance import approved_ledger
from test_anthropic_provider import payload

from agent_security_evaluation.anthropic_provider import AnthropicProvider, LiveProfile, make_client
from agent_security_evaluation.domain import Limits
from agent_security_evaluation.provider import ModelRequest


def test_haiku_wire_contract_rejects_speed_even_when_standard(tmp_path):
    """Replay the captured 400 contract, rather than a transport that accepts any field."""
    ledger, _ = approved_ledger(tmp_path)
    bodies = []

    async def handler(req):
        body = json.loads(req.content)
        bodies.append(body)
        headers = {
            "request-id": "req-haiku-contract",
            "anthropic-workspace-id": "fixture-workspace",
        }
        if req.url.path.endswith("count_tokens"):
            return httpx2.Response(200, json={"input_tokens": 100}, headers=headers)
        if "speed" in body:
            return httpx2.Response(
                400,
                json={
                    "type": "error",
                    "error": {
                        "type": "invalid_request_error",
                        "message": "'claude-haiku-5-5' does not support the `speed` parameter. This feature is only available on supported models.",
                    },
                },
                headers=headers,
            )
        return httpx2.Response(200, json=payload(), headers=headers)

    async def run():
        client = make_client(
            "fixture-key",
            LiveProfile(),
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
        )
        try:
            reply = await AnthropicProvider(client, LiveProfile(), ledger).complete(
                ModelRequest(
                    [{"role": "user", "content": "fixture"}], [], Limits(), "run-B01", "B01", 1
                )
            )
            assert reply.final_text
        finally:
            await client.close()

    asyncio.run(run())
    assert len(bodies) == 2 and all("speed" not in body for body in bodies)
    assert bodies[-1]["service_tier"] == "standard_only"
    assert ledger.summary()["settled_micro_usd"] == 20
    ledger.close()


def test_reduced_allowance_refuses_dispatch_that_only_fits_default_cap(tmp_path):
    ledger, _ = approved_ledger(tmp_path, cap_micro_usd=1_800_000)
    assert ledger.summary()["cap_micro_usd"] == 1_800_000
    assert ledger.summary()["remaining_micro_usd"] == 1_800_000
    # Synthetic prior settled spend isolates allowance accounting from model pricing.
    ledger.conn.execute(
        "INSERT INTO calls VALUES(?,?,?,?,?,'settled',?,?)",
        ("past", "B01", 1, "past-run", "b" * 64, 800_000, "{}"),
    )
    with pytest.raises(ValueError, match="insufficient_allowance"):
        ledger.permit_count("B02", 1)
    assert ledger.summary()["count_attempts"] == 0
    ledger.close()


def test_reduced_manifest_and_grant_bind_the_same_lower_cap(tmp_path):
    from pathlib import Path

    from agent_security_evaluation.allowance import AllowanceLedger
    from agent_security_evaluation.live import validate_live_authority

    _, mp, gp, manifest = live_fixture(tmp_path, cap_micro_usd=1_800_000)
    paths = manifest["content"]["paths"]
    validate_live_authority(mp, gp, Path(paths["ledger"]))
    ledger = AllowanceLedger(Path(paths["ledger"]), read_only=True)
    assert (
        ledger.authorization["cap_micro_usd"] == manifest["content"]["cap_micro_usd"] == 1_800_000
    )
    assert ledger.summary()["cap_micro_usd"] == 1_800_000
    ledger.close()


@pytest.mark.parametrize("cap", [True, 0, 1_000_000, 2_000_001, 1_800_000.0])
def test_allowance_ceiling_cannot_be_increased_or_underfunded(tmp_path, cap):
    from agent_security_evaluation.allowance import AllowanceLedger

    ledger = AllowanceLedger(tmp_path / "cap.sqlite3")
    with pytest.raises(ValueError, match="unsupported_allowance"):
        ledger.prepare_allowance("a" * 64, cap_micro_usd=cap)
    ledger.close()


@pytest.mark.parametrize("speed", [None, "absent"])
def test_haiku_nullable_optional_usage_has_no_fast_or_cache_surcharge(speed):
    from agent_security_evaluation.allowance import parse_usage

    raw = payload()
    if speed == "absent":
        raw["usage"].pop("speed")
    else:
        raw["usage"]["speed"] = None
    raw["usage"]["cache_creation_input_tokens"] = None
    raw["usage"]["cache_read_input_tokens"] = None
    parsed = parse_usage(raw, LiveProfile())
    assert parsed["micro_usd"] == 20
    assert parsed["total_input_tokens"] == 100 and not parsed["profile_deviation"]


def test_haiku_fast_receipt_or_boolean_counter_is_still_refused():
    from agent_security_evaluation.allowance import parse_usage

    raw = payload()
    raw["usage"]["speed"] = "fast"
    with pytest.raises(ValueError, match="unsupported_service_class"):
        parse_usage(raw, LiveProfile())
    raw["usage"]["speed"] = None
    raw["usage"]["cache_read_input_tokens"] = False
    with pytest.raises(ValueError, match="invalid_usage_integer"):
        parse_usage(raw, LiveProfile())
