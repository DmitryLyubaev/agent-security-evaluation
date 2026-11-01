import json
import os
import sqlite3
import sys
import time
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

from .allowance import CAP, CASE_IDS, RESERVATION, AllowanceLedger, pricing_snapshot
from .anthropic_provider import AnthropicProvider, LiveProfile, encode_request, make_client
from .domain import Limits, canonical, digest
from .evidence import file_sha256
from .provider import ModelRequest
from .runner import advance_run
from .study import (
    StudySummary,
    create_case_run,
    git,
    load_cases,
    resolve_fixture_approval,
    save_study,
)
from .tools import tool_schemas

CODE_ROOT = Path(__file__).resolve().parents[2]


def runtime_versions():
    return {
        "python": sys.version.split()[0],
        **{name: version(name) for name in ("anthropic", "httpx2", "truststore")},
    }


def _wire_tools(profile):
    return encode_request(ModelRequest([], tool_schemas(), Limits()), profile)["tools"]


def prepare_live(
    profile,
    output_path,
    *,
    source_root=None,
    private_root=None,
    evidence_origin="live_model",
    account=None,
):
    root = Path(source_root or CODE_ROOT).resolve()
    private = Path(private_root or root / "private/p25-live").resolve()
    if not private.is_relative_to(root / "private"):
        raise ValueError("live_paths_must_be_project_private")
    if git(root, "status", "--porcelain"):
        raise ValueError("source_not_clean")
    load_cases(root / "cases")
    if evidence_origin not in ("live_model", "test_fixture"):
        raise ValueError("invalid_live_origin")
    files = list((root / "src").rglob("*.py")) + list((root / "cases").glob("*.json"))
    files += [
        root / name
        for name in ("prompts/assistant.txt", "rubric.json", "pyproject.toml", "uv.lock")
    ]
    body = {
        "kind": "p25-live-v1",
        "cases_dir": "cases",
        "prompt_path": "prompts/assistant.txt",
        "rubric_path": "rubric.json",
        "source_commit": git(root, "rev-parse", "HEAD"),
        "files": {p.relative_to(root).as_posix(): file_sha256(p) for p in sorted(files)},
        "tools": tool_schemas(),
        "provider_tools": _wire_tools(profile),
        "profile": asdict(profile),
        "versions": runtime_versions(),
        "backend": "httpx2 with native truststore",
        "prices": pricing_snapshot(),
        "prices_sha256": digest(pricing_snapshot()),
        "limits": asdict(Limits()),
        "case_order": list(CASE_IDS),
        "generation_cap": 72,
        "count_cap": 72,
        "cap_micro_usd": CAP,
        "reservation_micro_usd": RESERVATION,
        "evidence_origin": evidence_origin,
        "paths": {
            "ledger": str(private / "allowance.sqlite3"),
            "store": str(private / "runs.sqlite3"),
            "evidence": str(private),
        },
        "account": account
        or {
            "account_id": None,
            "workspace_id": None,
            "personal_account_confirmed": False,
            "budget_alert_confirmed": False,
        },
    }
    result = {
        "content": body,
        "manifest_sha256": digest(body),
        "source_root": str(root),
        "created_at": time.time(),
        "authorized": False,
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical(result) + "\n")
    return result


def validate_manifest(manifest_path):
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    body = manifest["content"]
    if digest(body) != manifest["manifest_sha256"] or body.get("kind") != "p25-live-v1":
        raise ValueError("live_manifest_changed")
    profile = LiveProfile(**body["profile"])
    if (
        body["prices"] != pricing_snapshot()
        or body["prices_sha256"] != digest(pricing_snapshot())
        or body["versions"] != runtime_versions()
        or body["limits"] != asdict(Limits())
        or body["case_order"] != list(CASE_IDS)
        or body["generation_cap"] != 72
        or body["count_cap"] != 72
        or body["cap_micro_usd"] != CAP
        or body["reservation_micro_usd"] != RESERVATION
        or body["tools"] != tool_schemas()
        or body["provider_tools"] != _wire_tools(profile)
        or body["backend"] != "httpx2 with native truststore"
        or body["cases_dir"] != "cases"
        or body["prompt_path"] != "prompts/assistant.txt"
        or body["rubric_path"] != "rubric.json"
    ):
        raise ValueError("live_configuration_changed")
    root = Path(manifest["source_root"]).resolve()
    if git(root, "rev-parse", "HEAD") != body["source_commit"] or git(
        root, "status", "--porcelain"
    ):
        raise ValueError("source_not_clean")
    for name, sha in body["files"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or file_sha256(path) != sha:
            raise ValueError("frozen_files_changed")
        if name.startswith("src/") and file_sha256(CODE_ROOT / name) != sha:
            raise ValueError("loaded_runtime_source_mismatch")
    private = Path(body["paths"]["evidence"]).resolve()
    if (
        not private.is_relative_to(root / "private")
        or Path(body["paths"]["ledger"]).resolve() != private / "allowance.sqlite3"
        or Path(body["paths"]["store"]).resolve() != private / "runs.sqlite3"
    ):
        raise ValueError("live_path_binding_changed")
    return manifest


def validate_live_authority(manifest_path, grant_path, ledger_path):
    manifest = validate_manifest(manifest_path)
    body = manifest["content"]
    grant = json.loads(Path(grant_path).read_text(encoding="utf-8"))
    ledger_path = Path(ledger_path).resolve()
    if ledger_path != Path(body["paths"]["ledger"]):
        raise ValueError("ledger_path_mismatch")
    if not ledger_path.is_file():
        raise ValueError("allowance_not_authorized")
    with sqlite3.connect(ledger_path.as_uri() + "?mode=ro", uri=True) as connection:
        stored = {
            key: json.loads(value)
            for key, value in connection.execute("SELECT key,value FROM meta")
        }
    if stored.get("grant") != grant or stored.get("state") != "authorized":
        raise ValueError("grant_not_authorized_or_already_started")
    if (
        grant["manifest_sha256"] != manifest["manifest_sha256"]
        or grant["source_commit"] != body["source_commit"]
        or grant["cap_micro_usd"] != CAP
        or grant["prices_sha256"] != body["prices_sha256"]
        or grant["ledger_path"] != body["paths"]["ledger"]
        or grant["store_path"] != body["paths"]["store"]
        or grant["evidence_dir"] != body["paths"]["evidence"]
        or grant["evidence_origin"] != body["evidence_origin"]
        or not time.time() < grant["expires_at"] <= time.time() + 86400
    ):
        raise ValueError("grant_configuration_mismatch_or_expired")
    for field in (
        "account_id",
        "workspace_id",
        "personal_account_confirmed",
        "budget_alert_confirmed",
    ):
        if not body["account"].get(field) or grant.get(field) != body["account"][field]:
            raise ValueError("personal_account_or_alert_unconfirmed")
    return {"manifest": manifest, "grant": grant}


def readiness(manifest_path):
    manifest = validate_manifest(manifest_path)
    account = manifest["content"]["account"]
    return {
        "manifest_sha256": manifest["manifest_sha256"],
        "configuration_valid": True,
        "paid_execution_authorized": False,
        "personal_account_confirmed": account.get("personal_account_confirmed") is True,
        "workspace_confirmed": bool(account.get("workspace_id")),
        "budget_alert_confirmed": account.get("budget_alert_confirmed") is True,
        "generation_requests": 0,
    }


def _check_metadata(raw, profile, workspace):
    if raw.get("id") != profile.model or raw.get("lifecycle") != "active":
        raise ValueError("model_access_or_lifecycle_mismatch")
    context, output = raw.get("max_input_tokens"), raw.get("max_tokens")
    if (
        type(context) is not int
        or not 8192 <= context <= profile.context_upper_tokens
        or type(output) is not int
        or output < profile.output_tokens
    ):
        raise ValueError("model_context_or_output_capability_mismatch")
    caps = raw.get("capabilities") or {}
    if (
        caps.get("thinking", {}).get("types", {}).get("disabled", {}).get("supported") is not True
        or caps.get("effort", {}).get("medium", {}).get("supported") is not True
        or raw.get("_workspace_id") != workspace
    ):
        raise ValueError("model_mode_or_workspace_mismatch")


async def run_live_study(
    store, manifest_path, grant_path, ledger_path, evidence_dir, *, client_factory=None
):
    authority = validate_live_authority(manifest_path, grant_path, ledger_path)
    manifest, grant = authority["manifest"], authority["grant"]
    body = manifest["content"]
    if store.path.resolve() != Path(body["paths"]["store"]) or Path(evidence_dir).resolve() != Path(
        body["paths"]["evidence"]
    ):
        raise ValueError("live_store_or_evidence_path_mismatch")
    if body["evidence_origin"] == "test_fixture" and client_factory is None:
        raise ValueError("fixture_requires_injected_client")
    if client_factory is not None and body["evidence_origin"] != "test_fixture":
        raise ValueError("injected_transport_must_be_fixture")
    key = "fixture-not-a-key" if client_factory else os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError("missing_personal_credential")
    ledger = AllowanceLedger(Path(ledger_path))
    profile = LiveProfile(**body["profile"])
    client = None
    study_id = manifest["manifest_sha256"]
    study = {
        "study_id": study_id,
        "manifest": manifest,
        "evidence_dir": str(Path(evidence_dir).resolve()),
        "runs": {cid: None for cid in CASE_IDS},
        "provenance": body["evidence_origin"],
        "provider_identity": profile.provider_identity,
        "created_at": time.time(),
    }
    if store.conn.execute("SELECT 1 FROM studies WHERE id=?", (study_id,)).fetchone():
        ledger.close()
        raise ValueError("study_already_attempted")
    try:
        ledger.begin_study(study_id)
        save_study(store, study)
        client = (client_factory or make_client)(key, profile, workspace_id=grant["workspace_id"])
        ledger.permit_metadata()
        metadata = await client.models.with_raw_response.retrieve(
            profile.model, workspace_id=grant["workspace_id"]
        )
        raw = json.loads(metadata.http_response.text)
        raw["_workspace_id"] = metadata.http_response.headers.get("anthropic-workspace-id")
        raw["_request_id"] = metadata.http_response.headers.get("request-id")
        study["model_metadata"] = raw
        _check_metadata(raw, profile, grant["workspace_id"])
        root = Path(manifest["source_root"])
        cases = {case.case_id: case for case in load_cases(root / "cases")}
        prompt = (root / "prompts/assistant.txt").read_text(encoding="utf-8")
        provider = AnthropicProvider(client, profile, ledger)
        for case_id in CASE_IDS:
            if ledger.summary()["state"] != "running":
                break
            case = cases[case_id]
            run_id = create_case_run(
                store,
                case,
                prompt,
                expected_provider=profile.provider_identity,
                provenance=body["evidence_origin"],
            )
            study["runs"][case_id] = run_id
            save_study(store, study)
            grants = 0
            while True:
                result = await advance_run(store, provider, run_id, Path(evidence_dir) / "traces")
                if result.status != "waiting_approval" or ledger.summary()["state"] != "running":
                    break
                decision = resolve_fixture_approval(
                    store, case, result.pending_proposal_id, prior_grants=grants
                )
                grants += int(decision == "approved")
            save_study(store, study)
    except Exception as exc:  # noqa: BLE001 - save partial planned slots, never raw credential errors
        study["stop_reason"] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        ledger.halt("study_preflight_or_execution_error")
    finally:
        study["allowance"] = ledger.summary()
        study["allowance_receipts"] = ledger.receipts()
        states = [store.get_run(run).status for run in study["runs"].values() if run]
        summary = StudySummary(
            study_id,
            body["evidence_origin"],
            12,
            len(states),
            states.count("completed"),
            states.count("error"),
            sum(s in ("ready", "waiting_approval", "incomplete") for s in states),
            12 - len(states),
            list(study["runs"].values()),
        )
        study["summary"] = asdict(summary)
        save_study(store, study)
        ledger.close()
        if client is not None:
            await client.close()
    return summary
