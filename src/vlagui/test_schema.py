from datetime import datetime
from pathlib import Path

from vlagui.schema import Action, RunRecord, StepRecord


def test_run_record_jsonl_round_trip(tmp_path: Path) -> None:
    run = RunRecord(
        run_id="run-1",
        task_id="task-1",
        model="qwen3-vl:2b",
        started_at=datetime(2026, 8, 9, 12, 0, 0),
        ended_at=datetime(2026, 8, 9, 12, 0, 30),
        outcome="success",
        steps=[
            StepRecord(
                step_index=0,
                timestamp=datetime(2026, 8, 9, 12, 0, 5),
                screenshot_path="shots/0.png",
                action=Action(type="click", target="42"),
                verifier_result="uncertain",
            ),
            StepRecord(
                step_index=1,
                timestamp=datetime(2026, 8, 9, 12, 0, 10),
                screenshot_path="shots/1.png",
                action=Action(type="type", target="42", value="hello"),
                verifier_result="success",
            ),
        ],
    )

    path = tmp_path / "run.jsonl"
    run.to_jsonl(path)
    loaded = RunRecord.from_jsonl(path)

    assert loaded == run
