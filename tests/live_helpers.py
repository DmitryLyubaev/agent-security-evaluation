import json
import shutil
import subprocess
import time
from pathlib import Path

from test_anthropic_provider import payload
from test_study import ROOT


def live_fixture(tmp_path):
    from agent_security_evaluation.allowance import AllowanceLedger
    from agent_security_evaluation.anthropic_provider import LiveProfile
    from agent_security_evaluation.live import prepare_live

    root = tmp_path / "source"
    root.mkdir(parents=True)
    for name in ("cases", "prompts", "src"):
        shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("rubric.json", "uv.lock", "pyproject.toml", ".gitignore"):
        shutil.copy(ROOT / name, root / name)
    for args in (
        ["init", "-b", "main"],
        ["add", "."],
        [
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-m",
            "Fixture source",
        ],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    manifest_path = root / "private/proposal.json"
    manifest = prepare_live(
        LiveProfile(),
        manifest_path,
        source_root=root,
        evidence_origin="test_fixture",
        account={
            "account_id": "fixture-personal",
            "workspace_id": "fixture-workspace",
            "personal_account_confirmed": True,
            "budget_alert_confirmed": True,
        },
    )
    body = manifest["content"]
    ledger = AllowanceLedger(Path(body["paths"]["ledger"]))
    ledger.prepare_allowance(manifest["manifest_sha256"])
    grant = {
        "manifest_sha256": manifest["manifest_sha256"],
        "cap_micro_usd": 2_000_000,
        "prices_sha256": body["prices_sha256"],
        "source_commit": body["source_commit"],
        "approval_id": "TEST FIXTURE - no actual authority",
        "personal_account_confirmed": True,
        "budget_alert_confirmed": True,
        "account_id": "fixture-personal",
        "workspace_id": "fixture-workspace",
        "expires_at": time.time() + 3600,
        "evidence_origin": "test_fixture",
        "ledger_path": body["paths"]["ledger"],
        "store_path": body["paths"]["store"],
        "evidence_dir": body["paths"]["evidence"],
    }
    ledger.authorize(grant)
    ledger.close()
    grant_path = root / "private/grant.json"
    grant_path.write_text(json.dumps(grant))
    return root, manifest_path, grant_path, manifest


class SDKFixture:
    """Official SDK HTTP boundary fixture. Never a real model or human reference."""

    def __init__(self, cases, *, oversized=False, fail_case=None, repeat_proposal=False):
        self.cases = cases
        self.case_index = -1
        self.calls = []
        self.oversized = oversized
        self.fail_case = fail_case
        self.repeat_proposal = repeat_proposal

    async def handler(self, request):
        import httpx2

        from agent_security_evaluation.study import fake_provider

        self.calls.append(request.url.path)
        headers = {"request-id": "req-fixture", "anthropic-workspace-id": "fixture-workspace"}
        if request.method == "GET":
            data = {
                "id": "claude-haiku-5-5",
                "type": "model",
                "display_name": "Fixture Haiku",
                "created_at": "2026-10-07T00:00:00Z",
                "lifecycle": "active",
                "max_input_tokens": 1_000_000,
                "max_tokens": 128_000,
                "capabilities": {
                    "thinking": {"types": {"disabled": {"supported": True}}},
                    "effort": {"medium": {"supported": True}},
                },
            }
            return httpx2.Response(200, json=data, headers=headers)
        body = json.loads(request.content)
        if request.url.path.endswith("count_tokens"):
            return httpx2.Response(
                200, json={"input_tokens": 8193 if self.oversized else 100}, headers=headers
            )
        turns = sum(m["role"] == "assistant" for m in body["messages"])
        if turns == 0:
            self.case_index += 1
        case = self.cases[self.case_index]
        if case.case_id == self.fail_case:
            raise httpx2.ReadTimeout("fixture uncertain request")
        replies = list(fake_provider(case).replies)
        if self.repeat_proposal and case.case_id == "B02":
            from dataclasses import replace

            from agent_security_evaluation.domain import ToolCall

            repeats = replace(
                replies[1],
                tool_calls=(
                    ToolCall(
                        "propose-again", "propose_status_change", replies[1].tool_calls[0].arguments
                    ),
                ),
            )
            replies.insert(2, repeats)
        reply = replies[turns]
        latest = None
        for message in body["messages"]:
            for block in message["content"]:
                if block["type"] == "tool_result":
                    latest = json.loads(block["content"]).get("data", {}).get("proposal_id", latest)
        if reply.tool_calls:
            content = [
                {
                    "type": "tool_use",
                    "id": c.call_id,
                    "name": c.name,
                    "input": {
                        key: latest if value == "$latest_proposal" else value
                        for key, value in c.arguments.items()
                    },
                }
                for c in reply.tool_calls
            ]
            raw = payload(content=content, stop_reason="tool_use")
        else:
            raw = payload(content=[{"type": "text", "text": reply.final_text}])
        return httpx2.Response(200, json=raw, headers=headers)

    def factory(self, api_key, profile, *, workspace_id):
        import httpx2

        from agent_security_evaluation.anthropic_provider import make_client

        return make_client(
            api_key,
            profile,
            workspace_id=workspace_id,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(self.handler)),
        )


def sdk_fixture_for(manifest, **kwargs):
    from agent_security_evaluation.allowance import CASE_IDS
    from agent_security_evaluation.study import load_cases

    cases = {c.case_id: c for c in load_cases(Path(manifest["source_root"]) / "cases")}
    return SDKFixture([cases[cid] for cid in CASE_IDS], **kwargs)
