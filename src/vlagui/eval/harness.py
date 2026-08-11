"""Task-suite eval harness: runs tasks/*.yaml through Orchestrator across
requested models and ablation arms, writes one comparison report.
FR-15 (task suite), FR-16 (completion rate, steps-to-completion), FR-17
(base vs fine-tuned), FR-18 (ablation flag). T-5.2's check: one CLI
invocation produces a complete comparison/ablation report with zero manual
result collation.

Click accuracy (also part of FR-16) is NOT computed here: a task spec gives
a final task_assertion, not a per-step target box, so there's nothing to
score click precision against at this granularity. That's what
eval/grounding.py (Phase 3) measures, against ScreenSpot and the local
oracle set, where each example IS an (instruction, target box) pair.

None of the 20 tasks mutate persistent server-side state (they navigate,
dismiss banners, or submit forms that fail validation) — a fresh Executor
per task, a new Playwright browser context with no carried-over cookies or
localStorage, is a sufficient reset. No docker compose --force-recreate per
task is needed; see targets/README.md for when that would be required.
"""

import json
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import yaml
from pydantic import BaseModel

from .. import ground
from ..browser import Executor
from ..config import settings
from ..detect import opencv
from ..orchestrate import Orchestrator
from ..protocols import Box
from ..schema import Action, RunRecord
from ..verify import vlm

REPORTS_DIR = Path(__file__).resolve().parents[3] / "reports"
RUNS_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "runs"


class Task(BaseModel):
    id: str
    app: str
    url: str
    seed_actions: list[str] = []
    instruction: str
    task_assertion: str
    optimal_steps: int
    notes: str = ""


def load_tasks(tasks_dir: Path | None = None) -> list[Task]:
    tasks_dir = tasks_dir or settings.tasks_dir
    return [Task(**yaml.safe_load(p.read_text())) for p in sorted(tasks_dir.glob("*.yaml"))]


def _ground_raw(screenshot_path: Path, instruction: str, boxes: list[Box]) -> Action:
    """Adapts ground_raw's (screenshot, instruction, width, height) signature to
    the Grounder protocol's (screenshot, instruction, boxes) so it can be
    swapped in for the "no-som" ablation."""
    return ground.ground_raw(screenshot_path, instruction, settings.viewport.width, settings.viewport.height)


# Each entry isolates one factor from the primary pipeline (OmniParser SoM
# grounding + rule-based verifier) — the standard single-factor ablation
# design, not all factors changed at once.
ABLATIONS: dict[str, dict] = {
    "no-som": {"ground_fn": _ground_raw},
    "no-detector": {"detect_fn": opencv.detect},
    "vlm-verifier": {"verify_fn": vlm.verify},
}


def _model_tag(alias: str) -> str:
    """Maps the CLI's symbolic --model names to real Ollama tags."""
    if alias == "base":
        return settings.grounder_model
    if alias == "ft":
        return "vlagui-grounder"  # Phase 7's `ollama create vlagui-grounder` target
    return alias  # already a literal Ollama tag


def _check_model_available(tag: str) -> None:
    try:
        with urlopen(Request(f"{settings.ollama_host}/api/tags"), timeout=10) as resp:
            available = {m["name"] for m in json.loads(resp.read())["models"]}
    except URLError as e:
        raise RuntimeError(f"could not reach Ollama at {settings.ollama_host}: {e}") from e
    if tag not in available:
        raise RuntimeError(
            f"model tag {tag!r} not found via `ollama list` (have: {sorted(available)}). "
            "If this is the fine-tuned model, it doesn't exist until Phase 7 runs "
            "`ollama create vlagui-grounder`."
        )


def run_task(task: Task, orch_kwargs: dict, run_dir: Path) -> RunRecord:
    with Executor(task.url) as ex:
        if task.app == "todomvc":
            ex.reset()
        orch = Orchestrator(ex, run_dir=run_dir, **orch_kwargs)
        for seed in task.seed_actions:
            # Best-effort setup, not scored: empty task_assertion means the loop
            # stops as soon as anything changes, or at the step budget.
            orch.run(task_instruction=seed, task_assertion="", max_steps=settings.max_steps)
        record = orch.run(
            task_instruction=task.instruction, task_assertion=task.task_assertion, max_steps=settings.max_steps
        )
    record.task_id = task.id
    return record


@dataclass
class ArmResult:
    model: str
    arm: str
    runs: dict[str, RunRecord]  # task_id -> RunRecord


def run_arm(tasks: list[Task], model_alias: str, arm: str) -> ArmResult:
    orch_kwargs = ABLATIONS.get(arm, {})
    runs = {}
    for task in tasks:
        run_dir = RUNS_DIR / f"{model_alias}_{arm}_{task.id}"
        runs[task.id] = run_task(task, orch_kwargs, run_dir)
    return ArmResult(model=model_alias, arm=arm, runs=runs)


def summarize_arm(result: ArmResult) -> dict:
    records = list(result.runs.values())
    n = len(records)
    completed = [r for r in records if r.outcome == "success"]
    return {
        "n": n,
        "completion_rate": len(completed) / n if n else 0.0,
        "avg_steps_to_completion": statistics.mean(len(r.steps) for r in completed) if completed else None,
        "outcomes": dict(Counter(r.outcome for r in records)),
    }


def render_report(arm_results: list[ArmResult], tasks: list[Task]) -> str:
    lines = [
        "# vlagui eval report",
        "",
        f"{len(tasks)} tasks from `tasks/*.yaml`, {len(arm_results)} model/arm combination(s).",
        "",
        "Click accuracy (FR-16) is not reported here: task specs declare a final "
        "task_assertion, not a per-step target box, so there is nothing to score click "
        "precision against at this granularity. See `reports/grounding_eval.json` "
        "(eval/grounding.py) for click-accuracy / hit-rate numbers against ScreenSpot "
        "and the local oracle set.",
        "",
        "## Summary",
        "",
        "| Model | Arm | Completion rate | Avg steps (completed) | Outcomes | n |",
        "|---|---|---|---|---|---|",
    ]
    for res in arm_results:
        s = summarize_arm(res)
        avg = f"{s['avg_steps_to_completion']:.1f}" if s["avg_steps_to_completion"] is not None else "-"
        outcomes = ", ".join(f"{k}={v}" for k, v in sorted(s["outcomes"].items()))
        lines.append(f"| {res.model} | {res.arm} | {s['completion_rate']:.0%} | {avg} | {outcomes} | {s['n']} |")

    lines += ["", "## Per-task detail", ""]
    header = "| Task | " + " | ".join(f"{r.model}/{r.arm}" for r in arm_results) + " |"
    lines.append(header)
    lines.append("|---|" + "---|" * len(arm_results))
    for task in tasks:
        cells = [_format_run_cell(res.runs[task.id]) for res in arm_results]
        lines.append(f"| {task.id} | " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def _format_run_cell(record: RunRecord, max_reason_len: int = 80) -> str:
    """0-step failures come from an exception in Orchestrator.run() (e.g. a
    transient Playwright/CDP error), not a verifier judgment — surface
    termination_reason so those read as distinct from a genuine model failure."""
    reason = " ".join(record.termination_reason.split())[:max_reason_len].replace("|", "/")
    suffix = f": {reason}" if reason else ""
    return f"{record.outcome} ({len(record.steps)} steps){suffix}"


def run(models: list[str], arms: list[str], report_path: Path | None = None, tasks_dir: Path | None = None) -> Path:
    tasks = load_tasks(tasks_dir)
    original_model = settings.grounder_model

    tags = {alias: _model_tag(alias) for alias in models}
    for tag in tags.values():
        _check_model_available(tag)

    arm_results: list[ArmResult] = []
    try:
        for alias, tag in tags.items():
            settings.grounder_model = tag
            for arm in arms:
                arm_results.append(run_arm(tasks, alias, arm))
    finally:
        settings.grounder_model = original_model

    report_path = report_path or (REPORTS_DIR / "eval_report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(arm_results, tasks))

    raw_path = report_path.with_suffix(".json")
    raw_path.write_text(
        json.dumps(
            {
                f"{r.model}/{r.arm}": {tid: rec.model_dump(mode="json") for tid, rec in r.runs.items()}
                for r in arm_results
            },
            indent=2,
        )
    )
    return report_path
