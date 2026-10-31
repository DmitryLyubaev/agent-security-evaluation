import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]


def cli(tmp_path, *args, check=True):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_security_evaluation.cli",
            *args,
            "--db",
            str(tmp_path / "api.sqlite3"),
            "--private-dir",
            str(tmp_path / "private"),
            "--cases-dir",
            str(ROOT / "cases"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if check:
        assert result.returncode == 0, result.stdout + result.stderr
    return result


def test_api_cli_approval_and_readback(tmp_path):
    from agent_security_evaluation.api import create_app

    app = create_app(tmp_path / "api.sqlite3", tmp_path / "private", ROOT / "cases")

    async def create():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://fixture"
        ) as client:
            response = await client.post("/runs", json={"case_id": "B01"})
            assert response.status_code == 200
            assert response.json()["status"] == "waiting_approval"
            return response.json()

    waiting = asyncio.run(create())
    cli(tmp_path, "approve", "--proposal", waiting["pending_proposal_id"])
    resumed = json.loads(cli(tmp_path, "resume", "--run", waiting["run_id"]).stdout)
    assert resumed["status"] == "completed"
    assert resumed["model_requests"] == 4

    async def read():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://fixture"
        ) as client:
            response = await client.get(f"/runs/{waiting['run_id']}")
            assert response.json()["status"] == "completed"
            assert "messages" not in response.json()

    asyncio.run(read())


@pytest.mark.parametrize("field", ["account_id", "role", "provider_url", "approved"])
def test_api_rejects_identity_and_provider_override(tmp_path, field):
    from agent_security_evaluation.api import create_app

    app = create_app(tmp_path / "api.sqlite3", tmp_path / "private", ROOT / "cases")

    async def request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://fixture"
        ) as client:
            assert (
                await client.post("/runs", json={"case_id": "B01", field: "override"})
            ).status_code == 422
            assert (await client.post("/approve", json={})).status_code == 404
            assert (await client.get("/runs/unknown")).status_code == 404

    asyncio.run(request())


def test_cli_withhold_and_policy_exit(tmp_path):
    from agent_security_evaluation.store import Store

    waiting = json.loads(cli(tmp_path, "run", "--case", "B02").stdout)
    cli(tmp_path, "withhold", "--proposal", waiting["pending_proposal_id"])
    assert (
        json.loads(cli(tmp_path, "resume", "--run", waiting["run_id"]).stdout)["status"]
        == "completed"
    )
    store = Store(tmp_path / "api.sqlite3")
    assert store.get_record(waiting["run_id"], "A-100").status == "open"
    assert cli(tmp_path, "show", "--run", "unknown", check=False).returncode == 2


def test_study_live_is_side_effect_free(tmp_path, monkeypatch, capsys):
    import socket

    from agent_security_evaluation.cli import main

    def tripwire(*args, **kwargs):
        raise AssertionError("unexpected network or environment lookup")

    monkeypatch.setattr(socket, "create_connection", tripwire)
    monkeypatch.setattr(os, "getenv", tripwire)
    monkeypatch.setenv("PROVIDER_API_KEY", "FAKE-KEY-CANARY")
    db = tmp_path / "never.sqlite3"
    assert main(["study-live", "--db", str(db), "--private-dir", str(tmp_path / "never")]) == 2
    assert not db.exists()
    assert not (tmp_path / "never").exists()
    assert "FAKE-KEY-CANARY" not in capsys.readouterr().out


def test_cli_help():
    result = subprocess.run(
        [sys.executable, "-m", "agent_security_evaluation.cli", "--help"],
        text=True,
        check=False,
        capture_output=True,
    )
    assert result.returncode == 0
    assert "study-offline" in result.stdout
