import http.client
import json
import os
import socket
import subprocess
import sys
import time

from test_study import ROOT, git_fixture


def command(root, workspace, *args, env=None):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_security_evaluation.cli",
            *args,
            "--db",
            str(workspace / "acceptance.sqlite3"),
            "--private-dir",
            str(workspace / "private"),
            "--cases-dir",
            str(root / "cases"),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_actual_process_restart_and_exactly_one_transition(tmp_path):
    from agent_security_evaluation.domain import ToolCall, TrustedContext
    from agent_security_evaluation.store import Store
    from agent_security_evaluation.tools import dispatch_tool

    first = command(ROOT, tmp_path, "run", "--case", "B01")
    assert first["status"] == "waiting_approval"
    command(ROOT, tmp_path, "approve", "--proposal", first["pending_proposal_id"])
    done = command(ROOT, tmp_path, "resume", "--run", first["run_id"])
    assert (done["status"], done["model_requests"], done["tool_dispatches"]) == ("completed", 4, 3)
    assert (
        command(ROOT, tmp_path, "show", "--run", first["run_id"])["trace_hashes"]
        == done["trace_hashes"]
    )
    second = command(ROOT, tmp_path, "run", "--case", "B01")
    store = Store(tmp_path / "acceptance.sqlite3")
    call = ToolCall("replay", "apply_proposal", {"proposal_id": first["pending_proposal_id"]})
    assert (
        dispatch_tool(store, TrustedContext(first["run_id"], "operator-a", "A"), call).code
        == "approval_consumed"
    )
    assert (
        dispatch_tool(store, TrustedContext(second["run_id"], "operator-a", "A"), call).code
        == "access_denied"
    )
    assert store.get_record(first["run_id"], "A-100").version == 2
    assert store.get_record(second["run_id"], "A-100").version == 1
    assert (
        sum(
            e["call"]["name"] == "apply_proposal" and e["result"]["ok"]
            for e in store.events(first["run_id"])
        )
        == 1
    )
    store.close()


def test_cli_study_freeze_review_report_without_network(tmp_path):
    root, _ = git_fixture(tmp_path)
    workspace = tmp_path / "execution"
    workspace.mkdir()
    guard = tmp_path / "network_guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(
        "import socket, inspect\noriginal=socket.socket.connect\n"
        "def blocked(*a, **kw):\n    raise AssertionError('network forbidden')\n"
        "def guarded(self, address):\n"
        "    internal=any(f.function=='_fallback_socketpair' and f.filename==socket.__file__ "
        "for f in inspect.stack())\n"
        "    if internal and address[0] in ('127.0.0.1','::1'):\n"
        "        return original(self,address)\n"
        "    return blocked()\n"
        "socket.create_connection=blocked\nsocket.socket.connect=guarded\n"
    )
    env = {**os.environ, "PYTHONPATH": str(guard)}
    manifest = workspace / "manifest.json"
    frozen = command(root, workspace, "freeze", "--output", str(manifest), env=env)
    summary = command(root, workspace, "study-offline", "--manifest", str(manifest), env=env)
    assert summary["study_id"] == frozen["manifest_sha256"]
    assert (summary["planned"], summary["completed"], summary["errored"]) == (12, 12, 0)
    packet = workspace / "packet"
    command(
        root,
        workspace,
        "review-export",
        "--study",
        summary["study_id"],
        "--output",
        str(packet),
        env=env,
    )
    report = command(
        root,
        workspace,
        "report",
        "--study",
        summary["study_id"],
        "--output",
        str(workspace / "report.json"),
        env=env,
    )
    assert report["human_review"]["status"] == "pending"
    assert report["human_review"]["labels_supplied_as_human"] == 0
    assert report["model_evaluation"]["status"] == "not_run"
    assert report["groups"]["benign"]["completed"] == 4
    assert report["groups"]["adversarial"]["completed"] == 8


def test_real_loopback_server_and_operator_resume(tmp_path):
    def request(method, path, body=None):
        connection = http.client.HTTPConnection("127.0.0.1", 8025, timeout=3)
        try:
            connection.request(
                method,
                path,
                body=json.dumps(body) if body else None,
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 8025))
    args = [
        sys._base_executable,
        "-m",
        "agent_security_evaluation.cli",
        "serve",
        "--db",
        str(tmp_path / "acceptance.sqlite3"),
        "--private-dir",
        str(tmp_path / "private"),
        "--cases-dir",
        str(ROOT / "cases"),
    ]
    log = tmp_path / "server.log"
    with log.open("w") as handle:
        process = subprocess.Popen(
            args,
            stdout=handle,
            stderr=handle,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        )
        try:
            deadline = time.monotonic() + 15
            while True:
                try:
                    assert request("GET", "/runs/unknown")[0] == 404
                    break
                except ConnectionRefusedError:
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise AssertionError(log.read_text()) from None
                    time.sleep(0.1)
            status, waiting = request("POST", "/runs", {"case_id": "B01"})
            assert status == 200 and waiting["status"] == "waiting_approval"
            command(ROOT, tmp_path, "approve", "--proposal", waiting["pending_proposal_id"])
            command(ROOT, tmp_path, "resume", "--run", waiting["run_id"])
            assert request("GET", f"/runs/{waiting['run_id']}")[1]["status"] == "completed"
        finally:
            process.terminate()
            process.wait(timeout=10)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 8025))
