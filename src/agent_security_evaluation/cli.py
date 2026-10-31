import argparse
import asyncio
import json
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path

from .domain import TrustedApprover
from .runner import advance_run
from .store import Store
from .study import (
    CaseSpec,
    create_case_run,
    fake_provider,
    freeze_study,
    git,
    load_cases,
    run_offline_study,
)
from .tools import record_approval

LOCAL_APPROVER = TrustedApprover("local-reviewer-a", "A")


def parser():
    root = argparse.ArgumentParser(description="Bounded local study; fake provider only")
    commands = root.add_subparsers(dest="command", required=True)
    for name in (
        "serve",
        "run",
        "show",
        "approve",
        "withhold",
        "resume",
        "freeze",
        "study-offline",
        "study-live",
        "review-export",
        "labels-import",
        "report",
    ):
        command = commands.add_parser(name)
        command.add_argument("--db", type=Path, default=Path("private/demo.sqlite3"))
        command.add_argument("--private-dir", type=Path, default=Path("private/demo"))
        command.add_argument("--cases-dir", type=Path, default=Path("cases"))
        if name == "run":
            command.add_argument("--case", required=True)
        if name in ("show", "resume"):
            command.add_argument("--run", required=True)
        if name in ("approve", "withhold"):
            command.add_argument("--proposal", required=True)
        if name in ("freeze", "review-export", "report"):
            command.add_argument("--output", type=Path, required=True)
        if name == "study-offline":
            command.add_argument("--manifest", type=Path, required=True)
        if name in ("review-export", "report"):
            command.add_argument("--study", required=True)
        if name == "labels-import":
            command.add_argument("--packet", type=Path, required=True)
            command.add_argument("--labels", type=Path, required=True)
            command.add_argument("--provenance", choices=("human", "test_fixture"), required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "study-live":
        print(
            json.dumps(
                {"error": "live_not_implemented_or_authorized", "provenance": "offline_fake"}
            )
        )
        return 2
    store = None
    try:
        if args.command == "serve":
            import socket

            import uvicorn

            from .api import create_app

            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 8025))
            uvicorn.run(
                create_app(args.db, args.private_dir, args.cases_dir), host="127.0.0.1", port=8025
            )
            return 0
        if args.command == "freeze":
            root = args.cases_dir.resolve().parent
            value = freeze_study(
                args.cases_dir,
                root / "prompts/assistant.txt",
                root / "rubric.json",
                git(root, "rev-parse", "HEAD"),
                args.output,
            )
            print(json.dumps({"manifest_sha256": value}))
            return 0
        store = Store(args.db)
        if args.command == "run":
            cases = {case.case_id: case for case in load_cases(args.cases_dir)}
            if args.case not in cases:
                raise ValueError("unknown_case")
            case = cases[args.case]
            prompt = (args.cases_dir.parent / "prompts/assistant.txt").read_text(encoding="utf-8")
            run_id = create_case_run(store, case, prompt)
            result = asyncio.run(
                advance_run(store, fake_provider(case), run_id, args.private_dir / "traces")
            )
            print(json.dumps(asdict(result)))
            return 1 if result.status in ("error", "incomplete") else 0
        if args.command in ("show", "resume"):
            if args.command == "show":
                result = store.get_run(args.run)
            else:
                case = CaseSpec.model_validate(store.run_data(args.run)["case"])
                result = asyncio.run(
                    advance_run(store, fake_provider(case), args.run, args.private_dir / "traces")
                )
            print(json.dumps(asdict(result)))
            return 1 if result.status in ("error", "incomplete") else 0
        if args.command in ("approve", "withhold"):
            decision = record_approval(
                store, args.proposal, LOCAL_APPROVER, approve=args.command == "approve"
            )
            print(json.dumps({"decision": decision, "approval_type": "local_fixture_operator"}))
            return 0
        if args.command == "study-offline":
            result = asyncio.run(run_offline_study(store, args.manifest, args.private_dir))
            print(json.dumps(asdict(result)))
            return 1 if result.errored or result.incomplete or result.unrun else 0
        if args.command == "review-export":
            from .review import export_review

            print(json.dumps({"packet_sha256": export_review(store, args.study, args.output)}))
            return 0
        if args.command == "labels-import":
            from .review import import_labels

            print(
                json.dumps(
                    {
                        "batch_id": import_labels(
                            store, args.packet, args.labels, provenance=args.provenance
                        )
                    }
                )
            )
            return 0
        if args.command == "report":
            from .report import build_report

            print(json.dumps(build_report(store, args.study, args.output)))
            return 0
        raise ValueError("command_not_implemented")
    except (ValueError, KeyError, OSError, sqlite3.Error) as exc:
        # CLI errors are stable local codes, never raw provider messages or input payloads.
        code = (
            str(exc).strip("'") if isinstance(exc, (ValueError, KeyError)) else type(exc).__name__
        )
        print(json.dumps({"error": code}), file=sys.stderr)
        return 2
    finally:
        if store is not None:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
