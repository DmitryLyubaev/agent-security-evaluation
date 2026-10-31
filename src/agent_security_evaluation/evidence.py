import hashlib
import re
from pathlib import Path

from .domain import canonical


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_trace(trace_dir: Path, run_id: str, sequence: int, payload: dict) -> str:
    if not re.fullmatch(r"[A-Za-z0-9-]+", run_id):
        raise ValueError("invalid_trace_identity")
    trace_dir.mkdir(parents=True, exist_ok=True)
    path = trace_dir / f"{run_id}-{sequence:04d}.jsonl"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical(payload) + "\n")
        handle.flush()
    return file_sha256(path)


def verify_trace(path: Path, expected_sha256: str) -> bool:
    return path.is_file() and file_sha256(path) == expected_sha256
