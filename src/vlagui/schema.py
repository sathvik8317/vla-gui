"""StepRecord / RunRecord — the structured step log. Nothing writes ad hoc logs."""

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

ActionType = Literal["click", "type", "scroll", "done"]
VerifierResult = Literal["success", "failure", "uncertain"]
Outcome = Literal["success", "failure", "uncertain", "step_budget_exceeded"]


class Action(BaseModel):
    type: ActionType
    target: str | None = None  # SoM element id or "x,y" raw coords
    value: str | None = None  # typed text / scroll amount


class StepRecord(BaseModel):
    step_index: int
    timestamp: datetime
    screenshot_path: str
    action: Action
    verifier_result: VerifierResult | None = None
    notes: str = ""


class RunRecord(BaseModel):
    run_id: str
    task_id: str
    model: str
    started_at: datetime
    ended_at: datetime | None = None
    outcome: Outcome | None = None
    termination_reason: str = ""
    steps: list[StepRecord] = []

    def to_jsonl(self, path: Path) -> None:
        header = self.model_dump(mode="json", exclude={"steps"})
        with open(path, "w") as f:
            f.write(json.dumps({"record_type": "run", **header}) + "\n")
            for step in self.steps:
                f.write(json.dumps({"record_type": "step", **step.model_dump(mode="json")}) + "\n")

    @classmethod
    def from_jsonl(cls, path: Path) -> "RunRecord":
        lines = [json.loads(line) for line in open(path) if line.strip()]
        header = next(line for line in lines if line["record_type"] == "run")
        header = {k: v for k, v in header.items() if k != "record_type"}
        steps = [
            StepRecord(**{k: v for k, v in line.items() if k != "record_type"})
            for line in lines
            if line["record_type"] == "step"
        ]
        return cls(**header, steps=steps)
