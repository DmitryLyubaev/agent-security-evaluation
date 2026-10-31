import asyncio
import time
from dataclasses import asdict

from .domain import Limits, ToolResult, TrustedContext
from .evidence import write_trace
from .provider import ModelReply, ModelRequest
from .tools import dispatch_tool, tool_schemas


def start_run(store, context, messages, limits):
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
            "final_text": None,
            "error_code": None,
            "provenance": "offline_fake",
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

    if data["in_flight"]:
        return stop("incomplete", "interrupted_request")
    if data["status"] == "waiting_approval":
        decision = store.conn.execute(
            "SELECT approved FROM decisions WHERE proposal_id=?", (data["pending_proposal_id"],)
        ).fetchone()
        if decision is None:
            return store.get_run(run_id)
        data["messages"].append(
            {
                "role": "operator",
                "approved": bool(decision[0]),
                "proposal_id": data["pending_proposal_id"],
            }
        )
        data.update(status="ready", pending_proposal_id=None)
        save()

    while True:
        remaining = limits.case_seconds - (accumulated + time.monotonic() - start)
        if remaining <= 0:
            return stop("incomplete", "case_time_limit")
        if data["model_requests"] >= limits.model_requests:
            return stop("incomplete", "model_request_limit")
        request = ModelRequest(data["messages"], tool_schemas(), limits)
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
            code = "case_time_limit" if remaining <= limits.request_seconds else "provider_timeout"
            return stop("incomplete" if code == "case_time_limit" else "error", code)
        except Exception:  # noqa: BLE001 - provider boundary must not leak provider exception text
            return stop("error", "provider_error")
        if not isinstance(reply, ModelReply):
            return stop("error", "invalid_reply")
        try:
            trace({"kind": "reply", "reply": asdict(reply)})
        except (OSError, ValueError, TypeError):
            return stop("error", "evidence_error")
        if bool(reply.tool_calls) == (reply.final_text is not None):
            return stop("error", "invalid_reply")
        # There is no live adapter in this release. No caller can relabel fake output as live.
        if reply.provider_identity != "offline_fake":
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
                data["pending_proposal_id"] = result.data["proposal_id"]
        data["in_flight"] = False
        if exceeded:
            return stop("incomplete", "tool_dispatch_limit")
        if data["pending_proposal_id"]:
            data["status"] = "waiting_approval"
            save()
            return store.get_run(run_id)
        save()
