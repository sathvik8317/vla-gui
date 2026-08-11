"""Fast checks for harness.py's own logic (task loading, ablation wiring,
report rendering) — no live Ollama/Docker. Live end-to-end task runs are
already covered by test_orchestrate.py."""

import inspect
from datetime import datetime, timezone

from vlagui.eval import harness
from vlagui.orchestrate import Orchestrator
from vlagui.schema import Action, RunRecord, StepRecord


def test_load_tasks_matches_suite_design() -> None:
    tasks = harness.load_tasks()
    assert len(tasks) == 20
    assert {t.app for t in tasks} == {"todomvc", "gitea", "juice-shop", "grafana"}
    for t in tasks:
        assert 1 <= t.optimal_steps <= 3


def test_ablations_match_orchestrator_kwargs() -> None:
    valid_params = set(inspect.signature(Orchestrator.__init__).parameters)
    for name, kwargs in harness.ABLATIONS.items():
        assert set(kwargs).issubset(valid_params), f"{name} passes unknown kwarg(s) {set(kwargs) - valid_params}"


def _fake_record(task_id: str, outcome: str, n_steps: int) -> RunRecord:
    now = datetime.now(timezone.utc)
    steps = [
        StepRecord(step_index=i, timestamp=now, screenshot_path="x.png", action=Action(type="click", target="0"))
        for i in range(n_steps)
    ]
    return RunRecord(run_id="r", task_id=task_id, model="test-model", started_at=now, outcome=outcome, steps=steps)


def test_render_report_reflects_outcomes() -> None:
    tasks = harness.load_tasks()[:2]
    runs = {tasks[0].id: _fake_record(tasks[0].id, "success", 1), tasks[1].id: _fake_record(tasks[1].id, "failure", 2)}
    result = harness.ArmResult(model="base", arm="baseline", runs=runs)

    summary = harness.summarize_arm(result)
    assert summary["n"] == 2
    assert summary["completion_rate"] == 0.5
    assert summary["avg_steps_to_completion"] == 1

    report = harness.render_report([result], tasks)
    assert tasks[0].id in report
    assert tasks[1].id in report
    assert "50%" in report


def test_format_run_cell_surfaces_termination_reason() -> None:
    record = _fake_record("t1", "failure", 0)
    record.termination_reason = "error: bad | table-breaking char\nand a newline"
    cell = harness._format_run_cell(record)
    assert "failure (0 steps)" in cell
    assert "bad" in cell
    assert "|" not in cell  # sanitized, won't break the markdown table
    assert "\n" not in cell
