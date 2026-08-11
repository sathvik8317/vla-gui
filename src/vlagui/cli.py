"""`uv run vlagui <command>` entry point: run a single task, or the eval harness."""

import argparse
from pathlib import Path

import yaml

from .browser import Executor
from .eval import harness
from .orchestrate import Orchestrator


def _cmd_run(args: argparse.Namespace) -> None:
    task = harness.Task(**yaml.safe_load(Path(args.task_file).read_text()))
    with Executor(task.url) as ex:
        if task.app == "todomvc":
            ex.reset()
        orch = Orchestrator(ex)
        for seed in task.seed_actions:
            orch.run(task_instruction=seed, task_assertion="", max_steps=6)
        record = orch.run(task_instruction=task.instruction, task_assertion=task.task_assertion, max_steps=6)
    print(record.model_dump_json(indent=2))


def _cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run("vlagui.api:app", host=args.host, port=args.port)


def _cmd_eval(args: argparse.Namespace) -> None:
    models = [m.strip() for m in args.model.split(",") if m.strip()]
    if args.ablate in ("", "none"):
        selected = []
    elif args.ablate == "all":
        selected = list(harness.ABLATIONS)
    else:
        selected = [a.strip() for a in args.ablate.split(",") if a.strip()]
        unknown = set(selected) - set(harness.ABLATIONS)
        if unknown:
            raise SystemExit(f"unknown ablation(s): {sorted(unknown)}. Known: {sorted(harness.ABLATIONS)}")
    arms = ["baseline"] + selected
    report_path = Path(args.report) if args.report else None
    out = harness.run(models=models, arms=arms, report_path=report_path)
    print(f"wrote {out}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="vlagui")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run the agent loop on one task YAML")
    p_run.add_argument("task_file")
    p_run.set_defaults(func=_cmd_run)

    p_eval = sub.add_parser("eval", help="run the task suite across models/ablations, write a report")
    p_eval.add_argument("--model", default="base", help="comma-separated: base, ft, or a literal Ollama tag")
    p_eval.add_argument("--ablate", default="none", help="none | all | comma-separated: no-som,no-detector,vlm-verifier")
    p_eval.add_argument("--report", default=None, help="output .md path (default reports/eval_report.md)")
    p_eval.set_defaults(func=_cmd_eval)

    p_serve = sub.add_parser("serve", help="run the FastAPI demo service (POST /run, GET /runs/{id}, SSE stream)")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.set_defaults(func=_cmd_serve)

    args = parser.parse_args()
    args.func(args)
