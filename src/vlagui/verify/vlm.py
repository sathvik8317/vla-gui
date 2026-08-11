"""VLM-based verifier — ablation arm only, not used by default (see rules.py)."""

import base64
import json
import re
import urllib.request
from pathlib import Path

from ..config import settings
from ..schema import VerifierResult

_VALID = {"success", "failure", "uncertain"}


def verify(
    before_screenshot: Path,
    after_screenshot: Path,
    task_assertion: str,
    dom_before: str | None = None,
    dom_after: str | None = None,
) -> VerifierResult:
    """dom_before/dom_after accepted, not used: this arm judges from screenshots
    only, so its call signature matches rules.verify and either can be swapped
    into orchestrate.py's verify_fn."""
    prompt = (
        "You see two screenshots, BEFORE and AFTER an action taken toward this goal: "
        f"{task_assertion}\n"
        "Did the action succeed? Respond with only one word: success, failure, or uncertain."
    )
    body = json.dumps(
        {
            "model": settings.grounder_model,
            "prompt": prompt,
            "images": [
                base64.b64encode(Path(before_screenshot).read_bytes()).decode("ascii"),
                base64.b64encode(Path(after_screenshot).read_bytes()).decode("ascii"),
            ],
            "stream": False,
            "options": {"temperature": 0},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{settings.ollama_host}/api/generate", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        response = json.loads(resp.read())["response"].strip().lower()

    match = re.search(r"success|failure|uncertain", response)
    result = match.group() if match else "uncertain"
    return result if result in _VALID else "uncertain"
