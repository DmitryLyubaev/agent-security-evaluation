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
