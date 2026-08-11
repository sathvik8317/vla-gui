"""Detector / Grounder / Verifier protocols — ablation seams only.

Planner and executor each have one implementation and stay plain modules;
these three get interfaces because FR-18 requires toggling real alternatives:
Detector (OmniParser | OpenCV), Grounder (base | fine-tuned), Verifier (rules | VLM).
"""

from pathlib import Path
from typing import NamedTuple, Protocol

from .schema import Action, VerifierResult


class Box(NamedTuple):
    x: float
    y: float
    width: float
    height: float
    label: str


class Detector(Protocol):
    def detect(self, screenshot_path: Path) -> list[Box]: ...


class Grounder(Protocol):
    def ground(self, screenshot_path: Path, instruction: str, boxes: list[Box]) -> Action: ...


class Verifier(Protocol):
    def verify(self, before_screenshot: Path, after_screenshot: Path, task_assertion: str) -> VerifierResult: ...
