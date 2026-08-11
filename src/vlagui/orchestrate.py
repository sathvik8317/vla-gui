"""LangGraph loop: plan -> detect -> ground -> act -> verify, checkpointed, step-budgeted.

Wires plan.py, detect/, ground.py, browser.py, and verify/rules.py — the only
module allowed to import all of them. Must NEVER import oracle.py: the agent's
perception pipeline (plan/detect/ground) stays pure-vision. verify/rules.py
gets DOM state as plain strings the orchestrator captures itself via
browser.py's Playwright Page, not through the oracle module — see CLAUDE.md
invariants.
"""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from . import ground as grounder
from . import plan as planner
from .browser import Executor
from .config import settings
from .detect import omniparser
from .protocols import Box
from .schema import Action, RunRecord, StepRecord, VerifierResult
from .verify import rules as rules_verifier

DetectFn = Callable[[Path], list[Box]]
GroundFn = Callable[[Path, str, list[Box]], Action]
VerifyFn = Callable[..., VerifierResult]

RUNS_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "runs"


class AgentState(TypedDict, total=False):
    task_instruction: str
    task_assertion: str
    step_index: int
    max_steps: int
    history: list[str]
    steps: list[StepRecord]
    done: bool
    outcome: str | None
    termination_reason: str
    # scratch space for the step currently in flight
    before_shot: Path
    dom_before: str
    planned_action_type: str
    planned_target: str | None
    planned_value: str | None
    planned_submit: bool
    boxes: list[Box]
    resolved_action: Action
    after_shot: Path
    dom_after: str


class Orchestrator:
    """detect_fn/ground_fn/verify_fn default to the primary implementation of each
    ablation seam (OmniParser, set-of-marks grounding, rule-based verifier). Pass
    alternatives (e.g. detect/opencv.detect, a raw-coordinate grounder, verify/vlm.verify)
    to run the same loop under an ablation — this is FR-18's swap point, used by
    eval/harness.py."""

    def __init__(
        self,
        executor: Executor,
        run_dir: Path | None = None,
        detect_fn: DetectFn = omniparser.detect_boxes,
        ground_fn: GroundFn = grounder.ground,
        verify_fn: VerifyFn = rules_verifier.verify,
    ):
        self.ex = executor
        self.run_dir = run_dir or RUNS_DIR
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.detect_fn = detect_fn
        self.ground_fn = ground_fn
        self.verify_fn = verify_fn
        self._graph = self._build_graph()

    def _shot(self, name: str) -> Path:
        path = self.run_dir / name
        self.ex.screenshot(path)
        return path

    def _plan_node(self, state: AgentState) -> dict:
        shot = self._shot(f"step{state['step_index']}_before.png")
        dom_before = self.ex.page.content()
        step = planner.plan(
            shot, state["task_instruction"], state["history"], state["max_steps"] - state["step_index"]
        )
        return {
            "before_shot": shot,
            "dom_before": dom_before,
            "planned_action_type": step.action_type,
            "planned_target": step.target_description,
            "planned_value": step.value,
            "planned_submit": step.submit,
        }

    def _detect_node(self, state: AgentState) -> dict:
        if state["planned_action_type"] not in ("click", "type"):
            return {"boxes": []}
        return {"boxes": self.detect_fn(state["before_shot"])}

    def _ground_node(self, state: AgentState) -> dict:
        action_type = state["planned_action_type"]
        if action_type not in ("click", "type"):
            return {"resolved_action": Action(type=action_type, value=state["planned_value"])}
        resolved = self.ground_fn(state["before_shot"], state["planned_target"] or "", state["boxes"])
        return {
            "resolved_action": Action(
                type=action_type, target=resolved.target, value=state["planned_value"], submit=state["planned_submit"]
            )
        }

    def _act_node(self, state: AgentState) -> dict:
        action = state["resolved_action"]
        if action.type in ("click", "type"):
            box = state["boxes"][int(action.target)]
            x, y = box.x + box.width / 2, box.y + box.height / 2
            self.ex.click(x, y)
            if action.type == "type" and action.value:
                self.ex.type(action.value)
                if action.submit:
                    self.ex.press("Enter")
        elif action.type == "scroll":
            dy = 300 if action.value == "down" else -300
            self.ex.scroll(dy=dy)
        # "done": no browser action

        after_shot = self._shot(f"step{state['step_index']}_after.png")
        dom_after = self.ex.page.content()
        return {"after_shot": after_shot, "dom_after": dom_after}

    def _verify_node(self, state: AgentState) -> dict:
        after_shot = state["after_shot"]
        dom_after = state["dom_after"]
        result = self.verify_fn(
            state["before_shot"],
            after_shot,
            state["task_assertion"],
            dom_before=state["dom_before"],
            dom_after=dom_after,
        )
        record = StepRecord(
            step_index=state["step_index"],
            timestamp=datetime.now(timezone.utc),
            screenshot_path=str(after_shot),
            action=state["resolved_action"],
            verifier_result=result,
            notes=f"planned={state['planned_action_type']} target={state['planned_target']!r}",
        )
        steps = state["steps"] + [record]
        history = state["history"] + [f"{state['resolved_action'].type} -> {result}"]

        next_index = state["step_index"] + 1
        if state["planned_action_type"] == "done":
            return {"steps": steps, "history": history, "done": True, "outcome": "success", "termination_reason": "planner declared task done"}
        if result == "success":
            return {"steps": steps, "history": history, "done": True, "outcome": "success", "termination_reason": "verifier confirmed success"}
        if next_index >= state["max_steps"]:
            return {"steps": steps, "history": history, "done": True, "outcome": "step_budget_exceeded", "termination_reason": "step budget exhausted"}
        return {"steps": steps, "history": history, "step_index": next_index, "done": False}

    def _route_after_verify(self, state: AgentState) -> str:
        return END if state["done"] else "plan"

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("plan", self._plan_node)
        graph.add_node("detect", self._detect_node)
        graph.add_node("ground", self._ground_node)
        graph.add_node("act", self._act_node)
        graph.add_node("verify", self._verify_node)

        graph.set_entry_point("plan")
        graph.add_edge("plan", "detect")
        graph.add_edge("detect", "ground")
        graph.add_edge("ground", "act")
        graph.add_edge("act", "verify")
        graph.add_conditional_edges("verify", self._route_after_verify, {"plan": "plan", END: END})

        return graph.compile(checkpointer=MemorySaver())

    def _initial_state(self, task_instruction: str, task_assertion: str, max_steps: int | None) -> tuple[str, AgentState]:
        run_id = str(uuid.uuid4())
        initial_state: AgentState = {
            "task_instruction": task_instruction,
            "task_assertion": task_assertion,
            "step_index": 0,
            "max_steps": max_steps or settings.max_steps,
            "history": [],
            "steps": [],
            "done": False,
            "outcome": None,
            "termination_reason": "",
        }
        return run_id, initial_state

    def run(self, task_instruction: str, task_assertion: str, max_steps: int | None = None) -> RunRecord:
        run_id, initial_state = self._initial_state(task_instruction, task_assertion, max_steps)
        started_at = datetime.now(timezone.utc)

        try:
            final_state = self._graph.invoke(initial_state, config={"configurable": {"thread_id": run_id}})
            outcome = final_state["outcome"]
            steps = final_state["steps"]
            termination_reason = final_state["termination_reason"]
        except Exception as e:
            outcome = "failure"
            steps = []
            termination_reason = f"error: {e}"

        return RunRecord(
            run_id=run_id,
            task_id=task_instruction,
            model=settings.grounder_model,
            started_at=started_at,
            ended_at=datetime.now(timezone.utc),
            outcome=outcome,
            termination_reason=termination_reason,
            steps=steps,
        )

    def run_streaming(self, task_instruction: str, task_assertion: str, max_steps: int | None = None):
        """Same loop as run(), but yields each StepRecord as soon as it's produced
        instead of blocking until the whole run finishes, then a final
        {"outcome", "termination_reason"} dict. Powers api.py's SSE endpoint.

        Uses LangGraph's own .stream(stream_mode="updates") rather than adding
        bespoke per-node instrumentation — it already yields {node_name:
        return_dict} for each node as it executes."""
        run_id, initial_state = self._initial_state(task_instruction, task_assertion, max_steps)
        seen = 0
        try:
            for update in self._graph.stream(initial_state, config={"configurable": {"thread_id": run_id}}, stream_mode="updates"):
                verify_update = update.get("verify")
                if verify_update is None:
                    continue
                steps = verify_update["steps"]
                for step in steps[seen:]:
                    yield step
                seen = len(steps)
                if verify_update.get("done"):
                    yield {"outcome": verify_update["outcome"], "termination_reason": verify_update["termination_reason"]}
        except Exception as e:
            yield {"outcome": "failure", "termination_reason": f"error: {e}"}
