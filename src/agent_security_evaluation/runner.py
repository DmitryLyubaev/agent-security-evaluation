import asyncio
import time
from dataclasses import asdict

from .domain import Limits, ToolResult, TrustedContext
from .evidence import write_trace
from .provider import ModelReply, ModelRequest
from .tools import dispatch_tool, tool_schemas


def start_run(
    store, context, messages, limits, *, expected_provider="offline_fake", provenance="offline_fake"
):
    if store.conn.execute("SELECT 1 FROM runs WHERE id=?", (context.run_id,)).fetchone():
        raise ValueError("run_already_exists")
    store.save_run_data(
        {
            **asdict(context),
            "status": "ready",
            "messages": messages,
            "limits": asdict(limits),
            "model_requests": 0,
            "tool_dispatches": 0,
            "active_seconds": 0.0,
            "pending_proposal_id": None,
            "pending_proposal_ids": [],
            "final_text": None,
            "error_code": None,
            "provenance": provenance,
            "expected_provider": expected_provider,
            "trace_hashes": [],
            "seen_call_ids": [],
            "in_flight": False,
            "usage": [],
            "started_at": time.time(),
            "finished_at": None,
        }
    )
    return context.run_id


async def advance_run(store, provider, run_id, trace_dir):
    data = store.run_data(run_id)
    if data["status"] in ("completed", "error", "incomplete"):
        return store.get_run(run_id)
    limits = Limits(**data["limits"])
    context = TrustedContext(run_id, data["actor_id"], data["account_id"])
    start = time.monotonic()
    accumulated = data["active_seconds"]

    def save():
        data["active_seconds"] = accumulated + time.monotonic() - start
        store.save_run_data(data)

    def stop(status, code):
        data.update(status=status, error_code=code, in_flight=False, finished_at=time.time())
        save()
        return store.get_run(run_id)

    def trace(payload):
        sequence = len(data["trace_hashes"])
        sha = write_trace(trace_dir, run_id, sequence, payload)
        data["trace_hashes"].append({"path": f"{run_id}-{sequence:04d}.jsonl", "sha256": sha})

    def capture_provider_failure():
        diagnostic = getattr(provider, "last_diagnostic", None)
        if diagnostic:
            data["provider_failure"] = diagnostic
            trace({"kind": "provider_failure", "diagnostic": diagnostic})
        receipt = getattr(provider, "last_receipt", None)
        if receipt:
            trace({"kind": "provider_error_reply", "reply": receipt})

    if data["in_flight"]:
        return stop("incomplete", "interrupted_request")
    if data["status"] == "waiting_approval":
        pending = data.get("pending_proposal_ids", [data["pending_proposal_id"]])
        while pending:
            data["pending_proposal_id"] = pending[0]
            decision = store.conn.execute(
                "SELECT approved FROM decisions WHERE proposal_id=?", (pending[0],)
            ).fetchone()
            if decision is None:
                save()
                return store.get_run(run_id)
            data["messages"].append(
                {"role": "operator", "approved": bool(decision[0]), "proposal_id": pending[0]}
            )
            pending.pop(0)
            data["pending_proposal_ids"] = pending
            save()
        data.update(status="ready", pending_proposal_id=None)
        save()

    while True:
        remaining = limits.case_seconds - (accumulated + time.monotonic() - start)
        if remaining <= 0:
            return stop("incomplete", "case_time_limit")
        if data["model_requests"] >= limits.model_requests:
            return stop("incomplete", "model_request_limit")
        request = ModelRequest(
            data["messages"],
            tool_schemas(),
            limits,
            run_id,
            data.get("case", {}).get("case_id"),
            data["model_requests"] + 1,
        )
        data["model_requests"] += 1
        data["in_flight"] = True
        save()
        try:
            trace({"kind": "request", "request": asdict(request)})
            save()
        except (OSError, ValueError):
            return stop("error", "evidence_error")
        try:
            reply = await asyncio.wait_for(
                provider.complete(request), timeout=min(limits.request_seconds, remaining)
            )
        except TimeoutError:
            try:
                capture_provider_failure()
            except (OSError, ValueError, TypeError):
                return stop("error", "evidence_error")
            code = "case_time_limit" if remaining <= limits.request_seconds else "provider_timeout"
            return stop("incomplete" if code == "case_time_limit" else "error", code)
        except asyncio.CancelledError:
            try:
                capture_provider_failure()
            except (OSError, ValueError, TypeError):
                stop("error", "evidence_error")
            else:
                stop("incomplete", "interrupted_request")
            raise
        except Exception as exc:  # noqa: BLE001 - provider boundary normalizes errors, not secret text
            try:
                capture_provider_failure()
            except (OSError, ValueError, TypeError):
                return stop("error", "evidence_error")
            code = (
                str(exc)
                if hasattr(exc, "receipt")
                else getattr(provider, "last_error_code", None) or "provider_error"
            )
            return stop("incomplete" if code.startswith("provider_stop_") else "error", code)
        if not isinstance(reply, ModelReply):
            return stop("error", "invalid_reply")
        try:
            trace({"kind": "reply", "reply": asdict(reply)})
        except (OSError, ValueError, TypeError):
            return stop("error", "evidence_error")
        if bool(reply.tool_calls) == (reply.final_text is not None):
            return stop("error", "invalid_reply")
        if reply.provider_identity != data.get("expected_provider", "offline_fake"):
            return stop("error", "unsupported_provider")
        data["messages"].append({"role": "assistant", "content": asdict(reply)})
        data["usage"].append(reply.usage)
        if reply.final_text is not None:
            data.update(
                final_text=reply.final_text,
                status="completed",
                in_flight=False,
                finished_at=time.time(),
            )
            save()
            return store.get_run(run_id)
        ids = [call.call_id for call in reply.tool_calls]
        if len(set(ids)) != len(ids) or set(ids).intersection(data["seen_call_ids"]):
            return stop("error", "duplicate_call_id")
        exceeded = False
        for call in reply.tool_calls:
            if data["tool_dispatches"] >= limits.tool_dispatches:
                result = ToolResult(call.call_id, False, "tool_dispatch_limit", {})
                store.audit(context, call, result)
                exceeded = True
            else:
                data["tool_dispatches"] += 1
                result = dispatch_tool(store, context, call)
            data["seen_call_ids"].append(call.call_id)
            data["messages"].append({"role": "tool", "content": result.to_dict()})
            if call.name == "propose_status_change" and result.ok:
                data.setdefault("pending_proposal_ids", []).append(result.data["proposal_id"])
                data["pending_proposal_id"] = data["pending_proposal_ids"][0]
        data["in_flight"] = False
        if exceeded:
            return stop("incomplete", "tool_dispatch_limit")
        if data["pending_proposal_id"]:
            data["status"] = "waiting_approval"
            save()
            return store.get_run(run_id)
        save()
