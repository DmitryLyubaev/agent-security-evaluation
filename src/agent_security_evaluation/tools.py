import uuid
from dataclasses import asdict

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .domain import ToolResult, canonical, digest


class ReadArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    exception_id: str = Field(min_length=1, max_length=100)


class ProposeArgs(ReadArgs):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)
    evidence_ids: list[str] = Field(min_length=1, max_length=20)


class ApplyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    proposal_id: str = Field(min_length=1, max_length=100)


ARGUMENTS = {
    "get_exception": ReadArgs,
    "propose_status_change": ProposeArgs,
    "apply_proposal": ApplyArgs,
}


def tool_schemas():
    return [
        {"name": name, "parameters": cls.model_json_schema()} for name, cls in ARGUMENTS.items()
    ]


def record_approval(store, proposal_id, approver, *, approve):
    with store.transaction():
        proposal = store.get_proposal(proposal_id)
        if not proposal or approver.account_id != proposal["account_id"]:
            raise ValueError("access_denied")
        row = store.conn.execute(
            "SELECT digest FROM proposals WHERE id=?", (proposal_id,)
        ).fetchone()
        if row[0] != digest(proposal):
            raise ValueError("proposal_altered")
        if store.conn.execute(
            "SELECT 1 FROM decisions WHERE proposal_id=?", (proposal_id,)
        ).fetchone():
            raise ValueError("decision_already_recorded")
        store.conn.execute(
            "INSERT INTO decisions VALUES(?,?,?,?,?,0)",
            (proposal_id, row[0], approver.actor_id, approver.account_id, int(approve)),
        )
    return "approved" if approve else "withheld"


def dispatch_tool(store, context, call):
    def result(code, data=None):
        return ToolResult(call.call_id, code == "ok", code, data or {})

    def finish(answer):
        store.audit(context, call, answer)
        return answer

    if call.name not in ARGUMENTS:
        return finish(result("unknown_tool"))
    try:
        args = ARGUMENTS[call.name].model_validate(call.arguments)
    except ValidationError:
        return finish(result("invalid_arguments"))
    if call.name == "apply_proposal":
        with store.transaction():
            proposal = store.get_proposal(args.proposal_id)
            if not proposal or any(
                proposal[k] != getattr(context, k) for k in ("run_id", "actor_id", "account_id")
            ):
                return finish(result("access_denied"))
            saved_digest = store.conn.execute(
                "SELECT digest FROM proposals WHERE id=?", (args.proposal_id,)
            ).fetchone()[0]
            if digest(proposal) != saved_digest:
                return finish(result("proposal_altered"))
            grant = store.conn.execute(
                "SELECT * FROM decisions WHERE proposal_id=?", (args.proposal_id,)
            ).fetchone()
            if not grant or not grant["approved"]:
                return finish(result("approval_required"))
            if grant["consumed"]:
                return finish(result("approval_consumed"))
            if grant["digest"] != saved_digest or grant["account"] != context.account_id:
                return finish(result("proposal_altered"))
            record = store.get_record(context.run_id, proposal["exception_id"])
            if not record or record.account_id != context.account_id:
                return finish(result("access_denied"))
            if record.version != proposal["expected_version"] or record.status != "open":
                return finish(result("stale_proposal"))
            store.conn.execute(
                "UPDATE records SET status='follow_up_requested', version=version+1 "
                "WHERE run_id=? AND id=?",
                (context.run_id, record.exception_id),
            )
            store.conn.execute(
                "UPDATE decisions SET consumed=1 WHERE proposal_id=?", (args.proposal_id,)
            )
            return finish(result("ok", {"status": "follow_up_requested"}))
    record = store.get_record(context.run_id, args.exception_id)
    if not record or record.account_id != context.account_id:
        return finish(result("access_denied"))
    if call.name == "get_exception":
        return finish(result("ok", asdict(record)))
    if record.status != "open" or record.version != args.expected_version:
        return finish(result("stale_proposal"))
    if not set(args.evidence_ids).issubset({e.source_id for e in record.evidence}):
        return finish(result("invalid_evidence"))
    proposal_id = str(uuid.uuid4())
    proposal = {
        **asdict(context),
        **args.model_dump(),
        "status": "follow_up_requested",
        "proposal_id": proposal_id,
    }
    with store.transaction():
        store.conn.execute(
            "INSERT INTO proposals VALUES(?,?,?)",
            (proposal_id, canonical(proposal), digest(proposal)),
        )
        return finish(result("ok", {"proposal_id": proposal_id}))
