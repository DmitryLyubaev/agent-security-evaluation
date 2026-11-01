import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("scenario", ["complete", "interrupted", "expired"])
def test_official_sdk_cli_subprocess_without_external_generation(tmp_path, scenario):
    child = Path(__file__).with_name("live_acceptance_child.py")
    result = subprocess.run(
        [sys.executable, str(child), str(tmp_path), scenario],
        capture_output=True,
        text=True,
        timeout=75,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads(result.stdout.splitlines()[-1])
    assert receipt["external_requests"] == 0
    assert receipt["provenance"] == "test_fixture"
    assert receipt["scenario"] == scenario
