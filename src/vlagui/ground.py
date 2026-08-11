"""Grounder: qwen3-vl:2b via Ollama. SoM element-ID selection (primary mode) or
raw (x, y) model-space coordinate prediction (fallback / ablation arm)."""

import base64
import json
import re
import urllib.request
from pathlib import Path

from .config import settings
from .coords import model_to_image
from .protocols import Box
from .schema import Action
from .som import render_som


def _call_ollama(image_path: Path, prompt: str) -> str:
    body = json.dumps(
        {
            "model": settings.grounder_model,
            "prompt": prompt,
            "images": [base64.b64encode(Path(image_path).read_bytes()).decode("ascii")],
            "stream": False,
            # deterministic: qwen3-vl:2b-instruct's Modelfile default is temperature=1,
            # which makes eval hit-rates vary run to run on identical input. Ablation
            # comparisons (Phase 5) and base-vs-fine-tuned comparisons (Phase 7) need
            # runs that differ only in the thing being ablated, not in sampling noise.
            "options": {"temperature": 0},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{settings.ollama_host}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read())["response"]


def ground_som(screenshot_path: Path, instruction: str, boxes: list[Box], som_path: Path) -> Action:
    """Primary mode: render numbered boxes, ask the model to pick an element ID."""
    render_som(screenshot_path, boxes, som_path)
    prompt = (
        "You see a UI screenshot with numbered red boxes over interactive elements.\n"
        f"Task: {instruction}\n"
        "Which numbered box should be clicked? Respond with only the number."
    )
    response = _call_ollama(som_path, prompt)
    match = re.search(r"\d+", response)
    if match is None:
        raise ValueError(f"grounder did not return a box number: {response!r}")
    element_id = int(match.group())
    if not 0 <= element_id < len(boxes):
        raise ValueError(f"grounder picked out-of-range box {element_id} (have {len(boxes)})")
    return Action(type="click", target=str(element_id))


def ground_raw(screenshot_path: Path, instruction: str, width: int, height: int) -> Action:
    """Ablation mode: ask the model to predict raw (x, y) directly, normalized to [0, 1000]."""
    prompt = (
        f"You see a UI screenshot, {width}x{height} px.\n"
        f"Task: {instruction}\n"
        "Where should the click land? Respond with only 'x,y' where x and y are each "
        "integers 0-1000, normalized to the image width and height."
    )
    response = _call_ollama(screenshot_path, prompt)
    match = re.search(r"(\d+)\s*,\s*(\d+)", response)
    if match is None:
        raise ValueError(f"grounder did not return coordinates: {response!r}")
    mx, my = float(match.group(1)), float(match.group(2))
    x, y = model_to_image(mx, my, width, height)
    return Action(type="click", target=f"{x:.1f},{y:.1f}")


def ground(screenshot_path: Path, instruction: str, boxes: list[Box]) -> Action:
    """Grounder protocol: SoM element-ID mode (primary)."""
    som_path = screenshot_path.parent / f"{screenshot_path.stem}_som.png"
    return ground_som(screenshot_path, instruction, boxes, som_path)
