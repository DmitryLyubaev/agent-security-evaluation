from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from .runner import advance_run
from .store import Store
from .study import create_case_run, fake_provider, load_cases


class SubmitRun(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    case_id: str


def run_view(snapshot):
    result = asdict(snapshot)
    result.pop("trace_hashes")
    return result


def create_app(db_path: Path, evidence_dir: Path, cases_dir: Path) -> FastAPI:
    app = FastAPI(title="Synthetic agent security study (offline fake)")

    @app.post("/runs")
    async def submit(body: SubmitRun):
        cases = {case.case_id: case for case in load_cases(cases_dir)}
        if body.case_id not in cases:
            raise HTTPException(404, "unknown_case")
        case = cases[body.case_id]
        prompt = (cases_dir.parent / "prompts/assistant.txt").read_text(encoding="utf-8")
        store = Store(db_path)
        try:
            run_id = create_case_run(store, case, prompt)
            result = await advance_run(store, fake_provider(case), run_id, evidence_dir / "traces")
            return run_view(result)
        finally:
            store.close()

    @app.get("/runs/{run_id}")
    async def read(run_id: str):
        store = Store(db_path)
        try:
            return run_view(store.get_run(run_id))
        except KeyError as exc:
            raise HTTPException(404, "unknown_run") from exc
        finally:
            store.close()

    return app
