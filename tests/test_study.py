import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def git_fixture(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    for name in ("cases", "prompts"):
        shutil.copytree(ROOT / name, root / name)
    shutil.copy(ROOT / "rubric.json", root / "rubric.json")
    (root / ".gitignore").write_text("private/\n")
    for args in (
        ["init", "-b", "main"],
        ["add", "."],
        [
            "-c",
            "user.name=Test Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-m",
            "synthetic fixture",
        ],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    sha = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    return root, sha


def freeze(tmp_path):
    from agent_security_evaluation.study import freeze_study

    root, sha = git_fixture(tmp_path)
    path = root / "private" / "manifest.json"
    identity = freeze_study(
        root / "cases", root / "prompts/assistant.txt", root / "rubric.json", sha, path
    )
    return root, sha, path, identity


def test_case_inventory_and_surfaces():
    from agent_security_evaluation.study import load_cases

    cases = load_cases(ROOT / "cases")
    assert {c.case_id for c in cases} == {f"B{i:02}" for i in range(1, 5)} | {
        f"A{i:02}" for i in range(1, 9)
    }
    for attack in ("instruction_override", "fabricated_approval", "cross_account", "exfiltration"):
        group = [c for c in cases if c.attack_class == attack]
        assert len(group) == 2
        assert {c.surface for c in group} == {"document", "tool_result"}
        assert all(c.task and c.attacker_success for c in group)
    for case in cases[-2:]:
        assert case.forbidden_disclosures[0] in json.dumps(case.records)


def test_duplicate_case_rejected(tmp_path):
    from agent_security_evaluation.study import load_cases

    root, _ = git_fixture(tmp_path)
    shutil.copy(root / "cases/B01.json", root / "cases/duplicate.json")
    with pytest.raises(ValueError, match="case_inventory"):
        load_cases(root / "cases")


def test_freeze_equal_identity_and_no_overwrite(tmp_path):
    from agent_security_evaluation.study import freeze_study

    root, sha, path, identity = freeze(tmp_path)
    second = root / "private/second.json"
    assert (
        freeze_study(
            root / "cases", root / "prompts/assistant.txt", root / "rubric.json", sha, second
        )
        == identity
    )
    with pytest.raises(FileExistsError):
        freeze_study(
            root / "cases", root / "prompts/assistant.txt", root / "rubric.json", sha, path
        )


@pytest.mark.parametrize("target", ["cases/A01.json", "prompts/assistant.txt", "rubric.json"])
def test_changed_frozen_bytes_rejected(tmp_path, target):
    from agent_security_evaluation.study import verify_manifest

    root, _, path, _ = freeze(tmp_path)
    with (root / target).open("a") as handle:
        handle.write(" ")
    with pytest.raises(ValueError, match="frozen_bytes_changed"):
        verify_manifest(path)


def test_changed_tool_schema_rejected(tmp_path, monkeypatch):
    from agent_security_evaluation.study import verify_manifest

    _, _, path, _ = freeze(tmp_path)
    monkeypatch.setattr("agent_security_evaluation.study.tool_schemas", list)
    with pytest.raises(ValueError, match="tool_schema_changed"):
        verify_manifest(path)


def test_dirty_source_cannot_freeze(tmp_path):
    from agent_security_evaluation.study import freeze_study

    root, sha = git_fixture(tmp_path)
    (root / "untracked.txt").write_text("uncommitted")
    with pytest.raises(ValueError, match="source_not_clean"):
        freeze_study(
            root / "cases",
            root / "prompts/assistant.txt",
            root / "rubric.json",
            sha,
            root / "private/freeze.json",
        )


def test_bounded_offline_study_and_no_favorable_retry(tmp_path, monkeypatch):
    from agent_security_evaluation.store import Store
    from agent_security_evaluation.study import run_offline_study

    _, _, path, _ = freeze(tmp_path)
    store = Store(tmp_path / "study.sqlite3")
    summary = asyncio.run(run_offline_study(store, path, tmp_path / "evidence"))
    assert (summary.planned, summary.attempted, summary.completed) == (12, 12, 12)
    assert summary.provenance == "offline_fake"
    assert len(summary.run_ids) == 12
    assert all(store.get_run(run).model_requests <= 6 for run in summary.run_ids)
    with pytest.raises(ValueError, match="study_already_attempted"):
        asyncio.run(run_offline_study(store, path, tmp_path / "evidence"))


def test_provider_failure_retains_case_and_continues(tmp_path, monkeypatch):
    from agent_security_evaluation import study
    from agent_security_evaluation.store import Store

    _, _, path, _ = freeze(tmp_path)
    original = study.fake_provider

    class Broken:
        async def complete(self, request):
            raise RuntimeError("fixture failure")

    monkeypatch.setattr(
        study, "fake_provider", lambda case: Broken() if case.case_id == "A01" else original(case)
    )
    summary = asyncio.run(
        study.run_offline_study(Store(tmp_path / "study.sqlite3"), path, tmp_path / "evidence")
    )
    assert (summary.planned, summary.attempted, summary.completed, summary.errored) == (
        12,
        12,
        11,
        1,
    )
