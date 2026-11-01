import asyncio
import json
import os
import re
import ssl
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from .domain import ToolCall, canonical, digest
from .provider import ModelReply


@dataclass(frozen=True)
class LiveProfile:
    model: str = "claude-haiku-5-5"
    provider_identity: str = "anthropic:claude-haiku-5-5"
    sdk_version: str = "2.3.0"
    api_version: str = "2026-10-21"
    base_url: str = "https://api.anthropic.com"
    output_tokens: int = 1024
    input_estimate_tokens: int = 8192
    context_upper_tokens: int = 1_048_576

    def __post_init__(self):
        if asdict(self) != asdict_default_profile():
            raise ValueError("unsupported_live_profile")


def asdict_default_profile():
    return {
        field: definition.default for field, definition in LiveProfile.__dataclass_fields__.items()
    }


class ProtocolError(ValueError):
    def __init__(self, code, receipt):
        super().__init__(code)
        self.receipt = receipt


def encode_request(request, profile):
    messages = []
    system = []
    for message in request.messages:
        role = message["role"]
        if role == "system":
            system.append(message["content"])
            continue
        if role == "assistant":
            raw = message["content"].get("provider_message")
            if not raw:
                raise ValueError("missing_provider_replay")
            messages.append({"role": "assistant", "content": raw["content"]})
            continue
        if role == "tool":
            result = message["content"]
            blocks = [
                {
                    "type": "tool_result",
                    "tool_use_id": result["call_id"],
                    "content": canonical(result),
                    "is_error": not result["ok"],
                }
            ]
        elif role == "operator":
            blocks = [
                {
                    "type": "text",
                    "text": "Trusted operator decision: "
                    + canonical(
                        {"proposal_id": message["proposal_id"], "approved": message["approved"]}
                    ),
                }
            ]
        elif role == "user":
            blocks = [{"type": "text", "text": message["content"]}]
        else:
            raise ValueError("unsupported_message_role")
        if messages and messages[-1]["role"] == "user":
            messages[-1]["content"].extend(blocks)
        else:
            messages.append({"role": "user", "content": blocks})
    body = {
        "model": profile.model,
        "messages": messages,
        "max_tokens": profile.output_tokens,
        "thinking": {"type": "disabled"},
        "output_config": {"effort": "medium"},
        "service_tier": "standard_only",
        "speed": "standard",
        "inference_geo": "global",
        "tool_choice": {"type": "auto"},
        "tools": [
            {"name": tool["name"], "input_schema": tool["parameters"]} for tool in request.tools
        ],
    }
    if system:
        body["system"] = "\n".join(system)
    return body


def decode_response(payload, profile):
    if payload.get("model") != profile.model:
        raise ProtocolError("provider_model_mismatch", payload)
    blocks = payload.get("content", [])
    if not isinstance(blocks, list) or not blocks:
        raise ProtocolError("empty_provider_content", payload)
    calls, texts = [], []
    for block in blocks:
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            texts.append(block["text"])
        elif (
            block.get("type") == "tool_use"
            and isinstance(block.get("id"), str)
            and isinstance(block.get("name"), str)
            and isinstance(block.get("input"), dict)
        ):
            calls.append(ToolCall(block["id"], block["name"], block["input"]))
        else:
            raise ProtocolError("unsupported_provider_content", payload)
    stop = payload.get("stop_reason")
    if stop not in ("tool_use", "end_turn"):
        raise ProtocolError("provider_stop_" + str(stop), payload)
    if (stop == "tool_use") != bool(calls) or (not calls and not texts):
        raise ProtocolError("provider_stop_content_mismatch", payload)
    if not calls and not "\n".join(texts).strip():
        raise ProtocolError("provider_stop_empty_output", payload)
    return ModelReply(
        tuple(calls),
        None if calls else "\n".join(texts),
        payload.get("usage"),
        profile.provider_identity,
        {"role": "assistant", "content": blocks},
        stop,
        payload.get("_request_id", payload.get("id")),
    )


def verified_context():
    import truststore

    context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
        raise ValueError("tls_verification_required")
    return context


def make_client(api_key, profile, *, http_client=None, workspace_id=None):
    if os.environ.get("ANTHROPIC_CUSTOM_HEADERS"):
        raise ValueError("custom_headers_not_allowed")
    from importlib.metadata import version

    if version("anthropic") != profile.sdk_version:
        raise ValueError("sdk_version_changed")
    import anthropic
    import httpx2

    if http_client is None:
        http_client = httpx2.AsyncClient(
            verify=verified_context(),
            trust_env=False,
            timeout=30,
            follow_redirects=False,
            limits=httpx2.Limits(max_connections=1),
        )
    return anthropic.AsyncAnthropic(
        api_key=api_key,
        base_url=profile.base_url,
        http_client=http_client,
        timeout=30,
        max_retries=0,
        webhook_key="",
        default_headers={
            "anthropic-version": profile.api_version,
            **({"anthropic-workspace-id": workspace_id} if workspace_id else {}),
        },
        open_telemetry=False,
    )


def failure_diagnostic(exc, stage, *, secret="", response=None):
    """Retain useful failure evidence without SDK request objects or raw headers/bodies."""

    def redact(value):
        text = str(value)
        if isinstance(secret, str) and secret:
            text = text.replace(secret, "[REDACTED]")
        text = re.sub(r"sk-ant-[A-Za-z0-9_-]+", "[REDACTED]", text)
        text = re.sub(r"(?i)\b(bearer|basic)\s+[^\s\"']+", r"\1 [REDACTED]", text)
        return text[:1000]

    response = response if response is not None else getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    request_id = getattr(exc, "request_id", None)
    if response is not None:
        request_id = response.headers.get("request-id", request_id)
    request_id = redact(request_id) if request_id else None
    if request_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", request_id):
        request_id = None
    body = getattr(exc, "body", None)
    error = body.get("error", {}) if isinstance(body, dict) else {}
    error = error if isinstance(error, dict) else {}
    error_type = error.get("type")
    if not isinstance(error_type, str) or error_type not in {
        "invalid_request_error",
        "authentication_error",
        "billing_error",
        "permission_error",
        "not_found_error",
        "request_too_large",
        "rate_limit_error",
        "api_error",
        "overloaded_error",
        "timeout_error",
    }:
        error_type = None
    message = error.get("message")
    if not isinstance(message, str):
        # APIStatusError.__str__ includes the complete response body. Never log it.
        message = "HTTP failure without a structured error message" if status else str(exc)
    causes, cause = [], exc.__cause__
    while cause is not None and len(causes) < 3:
        causes.append({"exception_type": type(cause).__name__, "message": redact(cause)})
        cause = cause.__cause__
    return {
        "stage": stage,
        "exception_type": type(exc).__name__,
        "http_status": status if type(status) is int and 100 <= status <= 599 else None,
        "request_id": request_id,
        "error_type": error_type,
        "message": redact(message),
        "causes": causes,
    }


class AnthropicProvider:
    def __init__(self, client, profile, allowance):
        self.client, self.profile, self.allowance = client, profile, allowance
        self.last_receipt = None
        self.last_error_code = None
        self.last_diagnostic = None

    def _capture_failure(self, exc, stage, response=None):
        self.last_diagnostic = {
            "stage": stage,
            "exception_type": type(exc).__name__,
            "diagnostic_error": "capture_failed",
        }
        try:
            self.last_diagnostic = failure_diagnostic(
                exc, stage, secret=getattr(self.client, "api_key", ""), response=response
            )
        except Exception:  # noqa: BLE001, S110 - fallback excludes raw formatter error text
            pass

    async def complete(self, request):
        from .allowance import integer

        self.last_receipt = None
        self.last_error_code = None
        self.last_diagnostic = None

        if not request.run_id or not request.case_id or request.request_ordinal is None:
            raise ValueError("trusted_request_identity_required")
        body = encode_request(request, self.profile)
        body["workspace_id"] = self.allowance.authorization["workspace_id"]
        self.allowance.permit_count(request.case_id, request.request_ordinal)
        count_body = {
            key: value
            for key, value in body.items()
            if key
            in (
                "model",
                "messages",
                "system",
                "thinking",
                "tools",
                "tool_choice",
                "output_config",
                "speed",
                "workspace_id",
            )
        }
        try:
            counted = await self.client.messages.count_tokens(**count_body)
            if integer(counted.input_tokens) > self.profile.input_estimate_tokens:
                raise ValueError("input_estimate_limit")
        except BaseException as exc:
            try:
                self._capture_failure(exc, "token_count")
            finally:
                self.allowance.halt("token_count_failed")
            raise
        reservation = self.allowance.reserve(
            request.case_id,
            request.request_ordinal,
            run_id=request.run_id,
            request_sha256=digest(body),
        )
        stage, http_response = "generation", None
        try:
            response = await self.client.messages.with_raw_response.create(**body)
            http_response = response.http_response
            stage = "receipt"
            raw = json.loads(http_response.text)
            self.last_receipt = raw
            raw["_request_id"] = http_response.headers.get("request-id")
            raw["_workspace_id"] = http_response.headers.get("anthropic-workspace-id")
            raw["_request_body"] = json.loads(http_response.request.content)
            self.last_receipt = raw
            if raw["_workspace_id"] != self.allowance.authorization["workspace_id"]:
                raise ProtocolError("provider_workspace_mismatch", raw)
        except (
            BaseException
        ) as exc:  # financial reservation survives cancellation or unknown acceptance
            self.last_error_code = "provider_request_uncertain"
            try:
                self._capture_failure(exc, stage, http_response)
            finally:
                self.allowance.mark_uncertain(
                    reservation.reservation_id,
                    self.last_error_code,
                    diagnostic=self.last_diagnostic,
                )
            raise
        self.allowance.settle(reservation.reservation_id, raw)
        try:
            return decode_response(raw, self.profile)
        except ProtocolError as exc:
            if str(exc) not in ("provider_stop_max_tokens", "provider_stop_empty_output"):
                self.allowance.halt("provider_protocol_error")
            raise


async def _tls_probe():
    import httpx2

    context = verified_context()
    async with httpx2.AsyncClient(
        verify=context, trust_env=False, timeout=30, follow_redirects=False
    ) as client:
        response = await client.get("https://api.anthropic.com/v1/models")
        return {
            "tls_verified": True,
            "hostname_verified": context.check_hostname,
            "certificate_required": context.verify_mode == ssl.CERT_REQUIRED,
            "http_status": response.status_code,
            "authenticated": False,
            "model_access": "not_checked",
            "generation_requests": 0,
            "backend": "httpx2 with native truststore",
        }


def tls_preflight(output_path: Path):
    result = subprocess.run(
        [sys._base_executable, "-m", "agent_security_evaluation.anthropic_provider", "--tls-child"],
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        capture_output=True,
        text=True,
        timeout=40,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        receipt = (
            json.loads(result.stdout)
            if result.returncode == 0
            else {
                "tls_verified": False,
                "error": "tls_subprocess_failed",
                "exit_code": result.returncode,
                "stderr": result.stderr[-1500:],
                "generation_requests": 0,
            }
        )
    except json.JSONDecodeError:
        receipt = {"tls_verified": False, "error": "invalid_tls_receipt", "generation_requests": 0}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical(receipt) + "\n")
    return receipt


if __name__ == "__main__" and sys.argv[1:] == ["--tls-child"]:
    try:
        print(canonical(asyncio.run(_tls_probe())))
    except Exception as exc:  # noqa: BLE001 - bounded diagnostic subprocess, no credentials used
        print(
            canonical(
                {"tls_verified": False, "error": type(exc).__name__, "generation_requests": 0}
            )
        )
        raise SystemExit(1) from None
