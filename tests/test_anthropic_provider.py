import asyncio
import json

import pytest

from agent_security_evaluation.domain import Limits, ToolCall
from agent_security_evaluation.provider import ModelRequest
from agent_security_evaluation.tools import tool_schemas


def payload(*, content=None, stop_reason="end_turn", model="claude-haiku-5-5"):
    return {
        "id": "msg_fixture",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content or [{"type": "text", "text": "Awaiting approval [E-A1]."}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": 100,
            "output_tokens": 20,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "output_tokens_details": {"thinking_tokens": 0},
            "server_tool_use": {"web_fetch_requests": 0, "web_search_requests": 0},
            "speed": "standard",
            "service_tier": "standard",
            "inference_geo": "global",
        },
    }


def test_real_sdk_encodes_three_client_tools():
    from agent_security_evaluation.anthropic_provider import LiveProfile, encode_request

    request = ModelRequest(
        [{"role": "system", "content": "Trusted"}, {"role": "user", "content": "Read A-100"}],
        tool_schemas(),
        Limits(),
    )
    body = encode_request(request, LiveProfile())
    assert body["system"] == "Trusted"
    assert {tool["name"] for tool in body["tools"]} == {t["name"] for t in tool_schemas()}
    assert all("input_schema" in tool for tool in body["tools"])
    assert body["max_tokens"] == 1024 and body["thinking"] == {"type": "disabled"}
    assert body["service_tier"] == "standard_only"
    assert "temperature" not in body and "cache_control" not in body


def test_text_plus_tools_is_not_final():
    from agent_security_evaluation.anthropic_provider import LiveProfile, decode_response

    raw = payload(
        content=[
            {"type": "text", "text": "Checking evidence"},
            {
                "type": "tool_use",
                "id": "call_1",
                "name": "get_exception",
                "input": {"exception_id": "A-100"},
            },
        ],
        stop_reason="tool_use",
    )
    reply = decode_response(raw, LiveProfile())
    assert reply.final_text is None
    assert reply.tool_calls == (ToolCall("call_1", "get_exception", {"exception_id": "A-100"}),)
    assert reply.provider_message["content"] == raw["content"]
    assert reply.provider_identity == "anthropic:claude-haiku-5-5"


def test_matching_tool_results_and_operator_decision():
    from dataclasses import asdict

    from agent_security_evaluation.anthropic_provider import (
        LiveProfile,
        decode_response,
        encode_request,
    )

    reply = decode_response(
        payload(
            content=[
                {
                    "type": "tool_use",
                    "id": "c1",
                    "name": "get_exception",
                    "input": {"exception_id": "A-100"},
                }
            ],
            stop_reason="tool_use",
        ),
        LiveProfile(),
    )
    request = ModelRequest(
        [
            {"role": "system", "content": "Trusted"},
            {"role": "user", "content": "Investigate"},
            {"role": "assistant", "content": asdict(reply)},
            {
                "role": "tool",
                "content": {"call_id": "c1", "ok": True, "code": "ok", "data": {"text": "hostile"}},
            },
            {"role": "operator", "approved": False, "proposal_id": "p1"},
        ],
        tool_schemas(),
        Limits(),
    )
    body = encode_request(request, LiveProfile())
    assert all(message["role"] in ("user", "assistant") for message in body["messages"])
    results = body["messages"][-1]["content"]
    assert results[0]["type"] == "tool_result" and results[0]["tool_use_id"] == "c1"
    assert "Trusted operator decision" in results[1]["text"]
    assert "hostile" in results[0]["content"]


def test_truncation_is_incomplete():
    from agent_security_evaluation.anthropic_provider import (
        LiveProfile,
        ProtocolError,
        decode_response,
    )

    with pytest.raises(ProtocolError, match="max_tokens") as caught:
        decode_response(payload(stop_reason="max_tokens"), LiveProfile())
    assert caught.value.receipt["id"] == "msg_fixture"


@pytest.mark.parametrize("change", ["model", "content"])
def test_wrong_model_or_unknown_content_refused(change):
    from agent_security_evaluation.anthropic_provider import (
        LiveProfile,
        ProtocolError,
        decode_response,
    )

    raw = payload()
    if change == "model":
        raw["model"] = "other-model"
    else:
        raw["content"] = [{"type": "thinking", "thinking": "not requested", "signature": "fixture"}]
    with pytest.raises(ProtocolError) as caught:
        decode_response(raw, LiveProfile())
    assert caught.value.receipt["usage"]["output_tokens"] == 20


def test_no_automatic_retry():
    import anthropic
    import httpx2 as httpx

    from agent_security_evaluation.anthropic_provider import (
        LiveProfile,
        encode_request,
        make_client,
    )

    attempts = []

    async def handler(request):
        attempts.append(request)
        return httpx.Response(
            500, json={"type": "error", "error": {"type": "api_error", "message": "fixture"}}
        )

    async def run():
        client = make_client(
            "fixture-not-a-key",
            LiveProfile(),
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        try:
            with pytest.raises(anthropic.APIStatusError):
                await client.messages.create(
                    **encode_request(
                        ModelRequest(
                            [{"role": "user", "content": "Fixture"}], tool_schemas(), Limits()
                        ),
                        LiveProfile(),
                    )
                )
        finally:
            await client.close()

    asyncio.run(run())
    assert len(attempts) == 1
    assert attempts[0].url.host == "api.anthropic.com"


def test_official_sdk_success_roundtrip():
    import httpx2 as httpx

    from agent_security_evaluation.anthropic_provider import (
        LiveProfile,
        decode_response,
        encode_request,
        make_client,
    )

    async def handler(request):
        body = json.loads(request.content)
        assert body["model"] == "claude-haiku-5-5"
        return httpx.Response(200, json=payload(), headers={"request-id": "req-fixture"})

    async def run():
        client = make_client(
            "fixture-not-a-key",
            LiveProfile(),
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        try:
            response = await client.messages.create(
                **encode_request(
                    ModelRequest(
                        [{"role": "user", "content": "Fixture"}], tool_schemas(), Limits()
                    ),
                    LiveProfile(),
                )
            )
            assert decode_response(response.model_dump(), LiveProfile()).final_text
        finally:
            await client.close()

    asyncio.run(run())


def test_client_refuses_environment_header_overrides(monkeypatch):
    from agent_security_evaluation.anthropic_provider import LiveProfile, make_client

    monkeypatch.setenv("ANTHROPIC_CUSTOM_HEADERS", "anthropic-beta: unapproved-mode")
    with pytest.raises(ValueError, match="custom_headers_not_allowed"):
        make_client("fixture-not-a-key", LiveProfile())
