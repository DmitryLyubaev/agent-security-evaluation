import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

from .anthropic_provider import LiveProfile
from .domain import canonical, digest

CAP = 2_000_000
RESERVATION = 1_051_136
CASE_IDS = tuple([f"B{i:02}" for i in range(1, 5)] + [f"A{i:02}" for i in range(1, 9)])


def validate_cap(cap_micro_usd):
    if type(cap_micro_usd) is not int or not RESERVATION <= cap_micro_usd <= CAP:
        raise ValueError("unsupported_allowance")
    return cap_micro_usd


def pricing_snapshot():
    return {
        "date": "2026-11-01",
        "model": "claude-haiku-5-5",
        "currency": "USD",
        "threshold": 100_000,
        "small": {
            "input": "0.10",
            "output": "0.50",
            "write5": "0.125",
            "write1h": "0.20",
            "read": "0.01",
        },
        "large": {
            "input": "0.50",
            "output": "2.50",
            "write5": "0.625",
            "write1h": "1.00",
            "read": "0.05",
        },
    }


def integer(value):
    if type(value) is not int or value < 0:
        raise ValueError("invalid_usage_integer")
    return value


def optional_integer(value):
    return 0 if value is None else integer(value)


def parse_usage(payload, profile):
    if payload.get("model") != profile.model or not isinstance(payload.get("usage"), dict):
        raise ValueError("missing_or_wrong_model_usage")
    usage = payload["usage"]
    allowed = {
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
        "cache_creation",
        "output_tokens_details",
        "server_tool_use",
        "speed",
        "service_tier",
        "inference_geo",
        "iterations",
    }
    if any(value is not None for key, value in usage.items() if key not in allowed):
        raise ValueError("unsupported_usage_category")
    # Haiku rejects the speed request field. Its optional usage annotation may be null.
    if usage.get("speed") not in (None, "standard") or usage.get("service_tier") != "standard":
        raise ValueError("unsupported_service_class")
    if usage.get("inference_geo") != "global" or usage.get("iterations"):
        raise ValueError("unsupported_usage_scope")
    for key, value in (usage.get("server_tool_use") or {}).items():
        if key not in ("web_fetch_requests", "web_search_requests") or integer(value):
            raise ValueError("server_tool_charge_not_allowed")
    inp, out = integer(usage.get("input_tokens")), integer(usage.get("output_tokens"))
    creation = optional_integer(usage.get("cache_creation_input_tokens"))
    read = optional_integer(usage.get("cache_read_input_tokens"))
    cache = usage.get("cache_creation") or {}
    write5 = integer(cache.get("ephemeral_5m_input_tokens", 0))
    write1h = integer(cache.get("ephemeral_1h_input_tokens", 0))
    if (
        set(cache) - {"ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens"}
        or creation != write5 + write1h
    ):
        raise ValueError("unknown_cache_breakdown")
    total = inp + creation + read
    if total > profile.context_upper_tokens or out > profile.output_tokens:
        raise ValueError("usage_exceeds_reserved_contract")
    thinking = integer((usage.get("output_tokens_details") or {}).get("thinking_tokens", 0))
    if thinking > out:
        raise ValueError("invalid_thinking_breakdown")
    rates = pricing_snapshot()["small" if total <= 100_000 else "large"]
    quantities = {"input": inp, "output": out, "write5": write5, "write1h": write1h, "read": read}
    amount = sum(Decimal(number) * Decimal(rates[key]) for key, number in quantities.items())
    return {
        "micro_usd": int(amount.to_integral_value(rounding=ROUND_CEILING)),
        "total_input_tokens": total,
        "output_tokens": out,
        "thinking_tokens": thinking,
        "categories": quantities,
        "profile_deviation": bool(
            creation or read or thinking or total > profile.input_estimate_tokens
        ),
    }


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    micro_usd: int = RESERVATION


class AllowanceLedger:
    def __init__(self, path: Path, *, read_only=False):
        self.path = Path(path).resolve()
        if read_only:
            self.conn = sqlite3.connect(
                self.path.as_uri() + "?mode=ro", uri=True, isolation_level=None, timeout=10
            )
            self.conn.row_factory = sqlite3.Row
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, isolation_level=None, timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS counts(case_id TEXT, ordinal INTEGER, PRIMARY KEY(case_id,ordinal));
            CREATE TABLE IF NOT EXISTS calls(id TEXT PRIMARY KEY, case_id TEXT, ordinal INTEGER,
                run_id TEXT, request_sha TEXT, state TEXT, amount INTEGER, receipt TEXT,
                UNIQUE(case_id,ordinal));
            CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY, data TEXT);
        """)

    @contextmanager
    def transaction(self):
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise

    def _get(self, key):
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def _set(self, key, value):
        self.conn.execute(
            "INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, canonical(value)),
        )

    @property
    def authorization(self):
        grant = self._get("grant")
        if not grant:
            raise ValueError("grant_not_authorized")
        return grant

    def prepare_allowance(self, manifest_sha256, cap_micro_usd=CAP):
        validate_cap(cap_micro_usd)
        if not isinstance(manifest_sha256, str) or len(manifest_sha256) != 64:
            raise ValueError("unsupported_allowance")
        with self.transaction():
            if self._get("proposal"):
                raise ValueError("allowance_already_exists")
            proposal = {
                "manifest_sha256": manifest_sha256,
                "cap_micro_usd": cap_micro_usd,
                "prices_sha256": digest(pricing_snapshot()),
                "authorized": False,
            }
            self._set("proposal", proposal)
            self._set("state", "disabled")
        return proposal

    def authorize(self, approval):
        with self.transaction():
            proposal = self._get("proposal")
            if not proposal or self._get("grant"):
                raise ValueError("grant_already_exists_or_no_proposal")
            if approval.get("prices_sha256") != digest(pricing_snapshot()):
                raise ValueError("prices_changed")
            if Path(approval.get("ledger_path", "")).resolve() != self.path:
                raise ValueError("ledger_path_mismatch")
            if any(
                approval.get(key) != proposal[key] for key in ("manifest_sha256", "cap_micro_usd")
            ):
                raise ValueError("grant_proposal_mismatch")
            for key in ("personal_account_confirmed", "budget_alert_confirmed"):
                if approval.get(key) is not True:
                    raise ValueError("missing_owner_confirmation")
            for key in (
                "approval_id",
                "source_commit",
                "account_id",
                "workspace_id",
                "store_path",
                "evidence_dir",
            ):
                if not isinstance(approval.get(key), str) or not approval[key].strip():
                    raise ValueError("incomplete_grant")
            expiry = approval.get("expires_at", 0)
            if not time.time() < expiry <= time.time() + 86400:
                raise ValueError("grant_expired_or_too_long")
            if approval.get("evidence_origin") not in ("live_model", "test_fixture"):
                raise ValueError("invalid_evidence_origin")
            self._set("grant", approval)
            self._set("state", "authorized")
        return digest(approval)

    def _active(self):
        grant = self.authorization
        if time.time() >= grant["expires_at"]:
            raise ValueError("grant_expired")
        if grant["prices_sha256"] != digest(pricing_snapshot()):
            raise ValueError("prices_changed")
        if self._get("state") != "running":
            raise ValueError("grant_not_running")
        return grant

    def begin_study(self, manifest_sha256):
        with self.transaction():
            grant = self.authorization
            if (
                self._get("state") != "authorized"
                or time.time() >= grant["expires_at"]
                or grant["manifest_sha256"] != manifest_sha256
            ):
                raise ValueError("grant_cannot_start_or_expired")
            self._set("state", "running")

    def permit_metadata(self):
        with self.transaction():
            self._active()
            if self._get("metadata_requested"):
                raise ValueError("metadata_already_requested")
            self._set("metadata_requested", True)

    def _room(self):
        s = self.summary()
        if s["outstanding_micro_usd"] or s["uncertain_micro_usd"]:
            raise ValueError("dispatch_in_flight_or_uncertain")
        if s["settled_micro_usd"] + RESERVATION > s["cap_micro_usd"]:
            raise ValueError("insufficient_allowance")

    def permit_count(self, case_id, request_ordinal):
        with self.transaction():
            self._active()
            self._room()
            if (
                case_id not in CASE_IDS
                or type(request_ordinal) is not int
                or not 1 <= request_ordinal <= 6
            ):
                raise ValueError("case_or_request_limit")
            if self.conn.execute("SELECT count(*) FROM counts").fetchone()[0] >= 72:
                raise ValueError("count_request_limit")
            try:
                self.conn.execute("INSERT INTO counts VALUES(?,?)", (case_id, request_ordinal))
            except sqlite3.IntegrityError as exc:
                raise ValueError("count_already_attempted") from exc

    def reserve(self, case_id, request_ordinal, *, run_id, request_sha256):
        with self.transaction():
            self._active()
            self._room()
            if not self.conn.execute(
                "SELECT 1 FROM counts WHERE case_id=? AND ordinal=?", (case_id, request_ordinal)
            ).fetchone():
                raise ValueError("count_permit_required")
            existing = self.conn.execute(
                "SELECT run_id FROM calls WHERE case_id=?", (case_id,)
            ).fetchone()
            if existing and existing[0] != run_id:
                raise ValueError("case_run_mismatch")
            if self.conn.execute("SELECT count(*) FROM calls").fetchone()[0] >= 72:
                raise ValueError("generation_limit")
            item = Reservation(str(uuid.uuid4()))
            try:
                self.conn.execute(
                    "INSERT INTO calls VALUES(?,?,?,?,?,'reserved',?,NULL)",
                    (
                        item.reservation_id,
                        case_id,
                        request_ordinal,
                        run_id,
                        request_sha256,
                        item.micro_usd,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("generation_already_attempted") from exc
        return item

    def _alert(self):
        s = self.summary()
        if s["settled_micro_usd"] + s["uncertain_micro_usd"] >= 1_000_000:
            self.conn.execute(
                "INSERT OR IGNORE INTO alerts VALUES(1,?)",
                (canonical({"code": "project_budget_warning", "threshold_micro_usd": 1_000_000}),),
            )

    def mark_uncertain(self, reservation_id, reason, *, diagnostic=None):
        with self.transaction():
            self.conn.execute(
                "UPDATE calls SET state='uncertain',receipt=? WHERE id=? AND state='reserved'",
                (
                    canonical(
                        {"error_code": reason, **({"diagnostic": diagnostic} if diagnostic else {})}
                    ),
                    reservation_id,
                ),
            )
            self._set("state", "stopped")
            self._alert()

    def halt(self, reason):
        self._set("state", "stopped")
        self._set("stop_reason", reason)

    def settle(self, reservation_id, receipt):
        try:
            parsed = parse_usage(receipt, LiveProfile())
        except ValueError:
            self.mark_uncertain(reservation_id, "unsupported_usage")
            raise
        with self.transaction():
            row = self.conn.execute("SELECT * FROM calls WHERE id=?", (reservation_id,)).fetchone()
            if not row or row["state"] != "reserved":
                raise ValueError("reservation_not_settleable")
            if parsed["micro_usd"] > row["amount"]:
                raise ValueError("receipt_exceeds_reservation")
            self.conn.execute(
                "UPDATE calls SET state='settled',amount=?,receipt=? WHERE id=?",
                (
                    parsed["micro_usd"],
                    canonical({"raw": receipt, "parsed": parsed}),
                    reservation_id,
                ),
            )
            if parsed["profile_deviation"]:
                self._set("state", "stopped")
                self._set("stop_reason", "receipt_profile_deviation")
            self._alert()
        return parsed["micro_usd"]

    def summary(self):
        cap = (self._get("proposal") or {}).get("cap_micro_usd", CAP)
        values = {
            state: total
            for state, total in self.conn.execute(
                "SELECT state,coalesce(sum(amount),0) FROM calls GROUP BY state"
            )
        }
        return {
            "cap_micro_usd": cap,
            "settled_micro_usd": values.get("settled", 0),
            "outstanding_micro_usd": values.get("reserved", 0),
            "uncertain_micro_usd": values.get("uncertain", 0),
            "remaining_micro_usd": cap - sum(values.values()),
            "count_attempts": self.conn.execute("SELECT count(*) FROM counts").fetchone()[0],
            "generation_attempts": self.conn.execute("SELECT count(*) FROM calls").fetchone()[0],
            "alert_triggered": bool(self.conn.execute("SELECT 1 FROM alerts").fetchone()),
            "state": self._get("state"),
            "stop_reason": self._get("stop_reason"),
        }

    def receipts(self):
        return [dict(row) for row in self.conn.execute("SELECT * FROM calls ORDER BY rowid")]

    def close(self):
        self.conn.close()
