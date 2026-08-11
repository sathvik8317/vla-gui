"""Planner: one schema-constrained action per step (click/type/scroll/done).

Reuses the grounder's own VLM (settings.grounder_model) rather than a second
model — only one VLM is allowed resident on GPU at a time (4 GB budget).
"""

import base64
import json
import urllib.request
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .config import settings


class PlannedStep(BaseModel):
    action_type: Literal["click", "type", "scroll", "done"]
    target_description: str | None = None  # NL description for the grounder (click/type)
    value: str | None = None  # text to type, or "up"/"down" for scroll
    reasoning: str = ""


def plan(screenshot_path: Path, task_instruction: str, history: list[str], steps_remaining: int) -> PlannedStep:
    """Calls the VLM for the single next action, constrained to PlannedStep's JSON schema."""
    history_text = "\n".join(f"- {h}" for h in history) or "(none yet)"
    prompt = (
        f"You are operating a GUI to complete this task: {task_instruction}\n"
        f"Steps taken so far:\n{history_text}\n"
        f"Steps remaining: {steps_remaining}\n\n"
        "Decide the single next action.\n"
        "- click: target_description names the element to click, in plain language.\n"
        "- type: target_description names the input field to click first, value is the text to type into it.\n"
        "- scroll: value is 'up' or 'down'.\n"
        "- done: the task is already complete, no further action needed.\n"
        "Respond with JSON matching the schema."
    )
    body = json.dumps(
        {
            "model": settings.grounder_model,
            "prompt": prompt,
            "images": [base64.b64encode(Path(screenshot_path).read_bytes()).decode("ascii")],
            "stream": False,
            "format": PlannedStep.model_json_schema(),
            "options": {"temperature": 0},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{settings.ollama_host}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        response_text = json.loads(resp.read())["response"]
    return PlannedStep.model_validate_json(response_text)
