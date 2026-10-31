import hashlib
import json
from dataclasses import asdict, dataclass


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class TrustedContext:
    run_id: str
    actor_id: str
    account_id: str


@dataclass(frozen=True)
class TrustedApprover:
    actor_id: str
    account_id: str


@dataclass(frozen=True)
class Evidence:
    source_id: str
    kind: str
    text: str


@dataclass(frozen=True)
class ExceptionRecord:
    exception_id: str
    account_id: str
    status: str
    version: int
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    ok: bool
    code: str
    data: dict

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class Limits:
    model_requests: int = 6
    tool_dispatches: int = 12
    request_seconds: float = 30
    case_seconds: float = 180

    def __post_init__(self):
        if any(value <= 0 for value in asdict(self).values()):
            raise ValueError("limits_must_be_positive")


@dataclass(frozen=True)
class RunSnapshot:
    run_id: str
    status: str
    model_requests: int
    tool_dispatches: int
    active_seconds: float
    pending_proposal_id: str | None
    final_text: str | None
    error_code: str | None
    provenance: str
    trace_hashes: list[dict]
