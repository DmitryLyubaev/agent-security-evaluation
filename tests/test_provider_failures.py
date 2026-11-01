"""Real SDK diagnostics using synthetic credentials and local/mocked HTTP only."""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import anthropic
import httpx2
import pytest
from test_allowance import approved_ledger
from test_anthropic_provider import payload

from agent_security_evaluation.anthropic_provider import (
    AnthropicProvider,
    LiveProfile,
    make_client,
    verified_context,
)
from agent_security_evaluation.domain import Limits, TrustedContext
from agent_security_evaluation.provider import ModelRequest

KEY = "fixture-private-credential"


def request():
    return ModelRequest([{"role": "user", "content": "fixture"}], [], Limits(), "run-B01", "B01", 1)


@pytest.mark.parametrize("status", [400, 402, 429, 500])
def test_http_failure_keeps_redacted_diagnostics_and_full_reserve(tmp_path, status):
    ledger, _ = approved_ledger(tmp_path)
    calls = []

    async def handler(req):
        calls.append(req.url.path)
        if req.url.path.endswith("count_tokens"):
            return httpx2.Response(200, json={"input_tokens": 100})
        return httpx2.Response(
            status,
            json={
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": f"Invalid field. key={KEY} Bearer sk-ant-hidden",
                },
            },
            headers={"request-id": "req-fixture-failed", "x-private-header": KEY},
        )

    async def run():
        client = make_client(
            KEY,
            LiveProfile(),
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
        )
        provider = AnthropicProvider(client, LiveProfile(), ledger)
        try:
            with pytest.raises(anthropic.APIStatusError):
                await provider.complete(request())
        finally:
            await client.close()

    asyncio.run(run())
    row = json.loads(ledger.receipts()[0]["receipt"])
    diagnostic = row["diagnostic"]
    assert diagnostic["stage"] == "generation"
    assert diagnostic["http_status"] == status
    assert diagnostic["request_id"] == "req-fixture-failed"
    assert diagnostic["error_type"] == "invalid_request_error"
    assert "Invalid field" in diagnostic["message"]
    assert KEY not in json.dumps(row) and "sk-ant-hidden" not in json.dumps(row)
    assert "x-private-header" not in json.dumps(row)
    assert calls == ["/v1/messages/count_tokens", "/v1/messages"]
    assert ledger.summary()["uncertain_micro_usd"] == 1_051_136
    assert ledger.summary()["state"] == "stopped"
    ledger.close()


def test_receipt_reading_failure_keeps_stage_status_and_request_id(tmp_path):
    ledger, _ = approved_ledger(tmp_path)

    async def handler(req):
        if req.url.path.endswith("count_tokens"):
            return httpx2.Response(200, json={"input_tokens": 100})
        return httpx2.Response(200, content=b"not JSON", headers={"request-id": "req-bad-json"})

    async def run():
        client = make_client(
            KEY,
            LiveProfile(),
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
        )
        try:
            with pytest.raises(ValueError):
                await AnthropicProvider(client, LiveProfile(), ledger).complete(request())
        finally:
            await client.close()

    asyncio.run(run())
    diagnostic = json.loads(ledger.receipts()[0]["receipt"])["diagnostic"]
    assert diagnostic["stage"] == "receipt"
    assert diagnostic["exception_type"] == "JSONDecodeError"
    assert diagnostic["http_status"] == 200 and diagnostic["request_id"] == "req-bad-json"
    assert ledger.summary()["uncertain_micro_usd"] == 1_051_136
    ledger.close()


def test_real_loopback_http_can_deliver_and_settle_official_sdk_response(tmp_path):
    ledger, _ = approved_ledger(tmp_path)
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(self.path)
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert body["model"] == "claude-haiku-5-5"
            data = {"input_tokens": 100} if self.path.endswith("count_tokens") else payload()
            encoded = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("request-id", "req-loopback")
            self.send_header("anthropic-workspace-id", "fixture-workspace")
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    class LoopbackTransport(httpx2.AsyncBaseTransport):
        def __init__(self):
            self.inner = httpx2.AsyncHTTPTransport(verify=verified_context(), trust_env=False)

        async def handle_async_request(self, req):
            assert req.url.host == "api.anthropic.com"
            req.url = req.url.copy_with(scheme="http", host="127.0.0.1", port=server.server_port)
            return await self.inner.handle_async_request(req)

        async def aclose(self):
            await self.inner.aclose()

    async def run():
        client = make_client(
            KEY, LiveProfile(), http_client=httpx2.AsyncClient(transport=LoopbackTransport())
        )
        try:
            result = await AnthropicProvider(client, LiveProfile(), ledger).complete(request())
            assert result.final_text and result.request_id == "req-loopback"
        finally:
            await client.close()

    try:
        asyncio.run(run())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert calls == ["/v1/messages/count_tokens", "/v1/messages"]
    assert ledger.summary()["settled_micro_usd"] == 20
    ledger.close()


def test_runner_reports_http_error_without_losing_the_trace_or_releasing_money(tmp_path):
    from agent_security_evaluation.runner import advance_run, start_run
    from agent_security_evaluation.store import Store

    ledger, _ = approved_ledger(tmp_path)
    store = Store(tmp_path / "runs.sqlite3")
    start_run(
        store,
        TrustedContext("run-B01", "operator-a", "A"),
        [{"role": "user", "content": "fixture"}],
        Limits(),
        expected_provider=LiveProfile().provider_identity,
        provenance="test_fixture",
    )
    data = store.run_data("run-B01")
    data["case"] = {"case_id": "B01"}
    store.save_run_data(data)

    async def handler(req):
        if req.url.path.endswith("count_tokens"):
            return httpx2.Response(200, json={"input_tokens": 100})
        return httpx2.Response(
            402,
            json={
                "type": "error",
                "error": {"type": "billing_error", "message": "Fixture billing rejection"},
            },
            headers={"request-id": "req-billing-fixture"},
        )

    async def run():
        client = make_client(
            KEY,
            LiveProfile(),
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
        )
        try:
            return await advance_run(
                store,
                AnthropicProvider(client, LiveProfile(), ledger),
                "run-B01",
                tmp_path / "traces",
            )
        finally:
            await client.close()

    result = asyncio.run(run())
    assert result.status == "error" and result.error_code == "provider_request_uncertain"
    diagnostic = store.run_data("run-B01")["provider_failure"]
    assert diagnostic["http_status"] == 402 and diagnostic["error_type"] == "billing_error"
    trace = "".join(p.read_text() for p in (tmp_path / "traces").glob("*.jsonl"))
    assert "req-billing-fixture" in trace and KEY not in trace
    assert ledger.summary()["uncertain_micro_usd"] == 1_051_136
    ledger.close()
    store.close()


def test_report_exposes_safe_failure_details_without_claiming_completed_output(tmp_path):
    from pathlib import Path

    from live_helpers import live_fixture, sdk_fixture_for

    from agent_security_evaluation.live import run_live_study
    from agent_security_evaluation.report import build_report
    from agent_security_evaluation.store import Store

    _, mp, gp, manifest = live_fixture(tmp_path)
    paths = manifest["content"]["paths"]
    server = sdk_fixture_for(manifest)
    original = server.handler

    async def fail(req):
        if req.url.path == "/v1/messages":
            return httpx2.Response(
                402,
                json={
                    "type": "error",
                    "error": {"type": "billing_error", "message": "Fixture credit rejection"},
                },
                headers={"request-id": "req-report-fixture"},
            )
        return await original(req)

    server.handler = fail
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
    report = build_report(store, result.study_id, tmp_path / "failure-report.json")
    row = next(r for r in report["case_outcomes"] if r["case_id"] == "B01")
    assert row["provider_failure"]["http_status"] == 402
    assert row["provider_failure"]["request_id"] == "req-report-fixture"
    assert report["counts"]["completed"] == 0 and report["counts"]["unrun"] == 11
    assert report["usage"]["cost"] is None
    assert report["usage"]["uncertain_reserved_micro_usd"] == 1_051_136
    store.close()


def test_cancelled_generation_keeps_diagnostic_and_reserved_money(tmp_path):
    ledger, _ = approved_ledger(tmp_path)

    async def run():
        entered = asyncio.Event()

        async def handler(req):
            if req.url.path.endswith("count_tokens"):
                return httpx2.Response(200, json={"input_tokens": 100})
            entered.set()
            await asyncio.Future()

        client = make_client(
            KEY,
            LiveProfile(),
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
        )
        try:
            task = asyncio.create_task(
                AnthropicProvider(client, LiveProfile(), ledger).complete(request())
            )
            await asyncio.wait_for(entered.wait(), timeout=3)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            await client.close()

    asyncio.run(run())
    diagnostic = json.loads(ledger.receipts()[0]["receipt"])["diagnostic"]
    assert diagnostic["stage"] == "generation" and diagnostic["exception_type"] == "CancelledError"
    assert ledger.summary()["state"] == "stopped"
    assert ledger.summary()["uncertain_micro_usd"] == 1_051_136
    ledger.close()


@pytest.mark.parametrize("stage", ["token_count", "generation"])
@pytest.mark.parametrize("malformed_type", [[], {"unexpected": "object"}])
def test_malformed_error_type_cannot_bypass_financial_stop(tmp_path, stage, malformed_type):
    ledger, _ = approved_ledger(tmp_path)

    async def handler(req):
        if req.url.path.endswith("count_tokens") and stage == "generation":
            return httpx2.Response(200, json={"input_tokens": 100})
        return httpx2.Response(
            400, json={"error": {"type": malformed_type, "message": "Malformed fixture error"}}
        )

    async def run():
        client = make_client(
            KEY,
            LiveProfile(),
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
        )
        provider = AnthropicProvider(client, LiveProfile(), ledger)
        try:
            with pytest.raises(anthropic.APIStatusError):
                await provider.complete(request())
            assert provider.last_diagnostic["error_type"] is None
        finally:
            await client.close()

    asyncio.run(run())
    assert ledger.summary()["state"] == "stopped"
    assert ledger.summary()["uncertain_micro_usd"] == (1_051_136 if stage == "generation" else 0)
    ledger.close()


@pytest.mark.parametrize("stage", ["token_count", "generation"])
def test_diagnostic_formatter_failure_cannot_mask_error_or_skip_stop(tmp_path, monkeypatch, stage):
    ledger, _ = approved_ledger(tmp_path)

    def broken(*a, **kw):
        raise ValueError(f"Diagnostic failed with {KEY}")

    monkeypatch.setattr("agent_security_evaluation.anthropic_provider.failure_diagnostic", broken)

    async def handler(req):
        if req.url.path.endswith("count_tokens") and stage == "generation":
            return httpx2.Response(200, json={"input_tokens": 100})
        return httpx2.Response(
            400, json={"error": {"type": "invalid_request_error", "message": "Fixture"}}
        )

    async def run():
        client = make_client(
            KEY,
            LiveProfile(),
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
        )
        provider = AnthropicProvider(client, LiveProfile(), ledger)
        try:
            with pytest.raises(anthropic.APIStatusError):
                await provider.complete(request())
            assert provider.last_diagnostic["diagnostic_error"] == "capture_failed"
            assert KEY not in json.dumps(provider.last_diagnostic)
        finally:
            await client.close()

    asyncio.run(run())
    assert ledger.summary()["state"] == "stopped"
    assert ledger.summary()["uncertain_micro_usd"] == (1_051_136 if stage == "generation" else 0)
    ledger.close()


def test_cancelled_runner_persists_failure_before_reraising(tmp_path):
    from agent_security_evaluation.runner import advance_run, start_run
    from agent_security_evaluation.store import Store

    ledger, _ = approved_ledger(tmp_path)
    store = Store(tmp_path / "cancelled.sqlite3")
    start_run(
        store,
        TrustedContext("run-B01", "operator-a", "A"),
        [{"role": "user", "content": "fixture"}],
        Limits(),
        expected_provider=LiveProfile().provider_identity,
        provenance="test_fixture",
    )
    data = store.run_data("run-B01")
    data["case"] = {"case_id": "B01"}
    store.save_run_data(data)

    async def run():
        entered = asyncio.Event()

        async def handler(req):
            if req.url.path.endswith("count_tokens"):
                return httpx2.Response(200, json={"input_tokens": 100})
            entered.set()
            await asyncio.Future()

        client = make_client(
            KEY,
            LiveProfile(),
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
        )
        try:
            task = asyncio.create_task(
                advance_run(
                    store,
                    AnthropicProvider(client, LiveProfile(), ledger),
                    "run-B01",
                    tmp_path / "traces",
                )
            )
            await asyncio.wait_for(entered.wait(), timeout=3)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            await client.close()

    asyncio.run(run())
    data = store.run_data("run-B01")
    assert data["provider_failure"]["exception_type"] == "CancelledError"
    assert data["status"] == "incomplete" and data["in_flight"] is False
    assert data["error_code"] == "interrupted_request"
    assert len(data["trace_hashes"]) == 2
    assert ledger.summary()["uncertain_micro_usd"] == 1_051_136
    store.close()
    ledger.close()
