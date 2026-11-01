from dataclasses import dataclass, replace
from typing import Protocol

from .domain import Limits, ToolCall


@dataclass(frozen=True)
class ModelReply:
    tool_calls: tuple[ToolCall, ...] = ()
    final_text: str | None = None
    usage: dict | None = None
    provider_identity: str = "offline_fake"
    provider_message: dict | None = None
    stop_reason: str | None = None
    request_id: str | None = None


@dataclass(frozen=True)
class ModelRequest:
    messages: list[dict]
    tools: list[dict]
    limits: Limits
    run_id: str | None = None
    case_id: str | None = None
    request_ordinal: int | None = None


class Provider(Protocol):
    async def complete(self, request: ModelRequest) -> ModelReply: ...


class ScriptedFakeProvider:
    """Deterministic software fixture. This is never measured model behavior."""

    def __init__(self, replies: list[ModelReply]):
        self.replies = replies

    async def complete(self, request: ModelRequest) -> ModelReply:
        index = sum(message["role"] == "assistant" for message in request.messages)
        reply = self.replies[index]
        latest = None
        for message in request.messages:
            if message["role"] == "tool":
                latest = message["content"].get("data", {}).get("proposal_id", latest)
        calls = tuple(
            replace(
                call,
                arguments={
                    key: latest if value == "$latest_proposal" and latest else value
                    for key, value in call.arguments.items()
                },
            )
            for call in reply.tool_calls
        )
        return replace(reply, tool_calls=calls, provider_identity="offline_fake")
