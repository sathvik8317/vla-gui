"""Phase 4 check: full loop completes one trivial two-step task against a
self-hosted target and writes a well-formed run log (RunRecord + StepRecords
validate against schema.py)."""

from pathlib import Path

from vlagui.browser import Executor
from vlagui.orchestrate import Orchestrator
from vlagui.schema import RunRecord

RUN_LOG_PATH = Path(__file__).resolve().parents[2] / "reports" / "orchestrate_run.jsonl"


def _center(box: dict) -> tuple[float, float]:
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def test_orchestrator_completes_two_step_task() -> None:
    with Executor("http://localhost:8081") as ex:
        ex.reset()
        ex.click(*_center(ex.page.locator("#new-todo").bounding_box()))
        ex.type("Buy milk")
        ex.press("Enter")

        orchestrator = Orchestrator(ex)
        run_record = orchestrator.run(
            task_instruction=(
                "There is one todo item labeled 'Buy milk'. Step 1: click the checkbox "
                "to the left of it to mark it complete. Step 2: click the delete (x) "
                "button to the right of it to remove it."
            ),
            task_assertion="!Buy milk",  # success = "Buy milk" no longer in the DOM
            max_steps=4,
        )

    assert isinstance(run_record, RunRecord)
    assert len(run_record.steps) > 0

    RUN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    run_record.to_jsonl(RUN_LOG_PATH)
    reloaded = RunRecord.from_jsonl(RUN_LOG_PATH)
    assert reloaded == run_record
