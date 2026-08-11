"""Component-level grounding eval: hit-rate is primary, median normalized
distance is secondary (S4). Both grounder modes (SoM element-ID, raw x,y) run
against both sets, so the report gives a real same-benchmark SoM-vs-raw
comparison rather than two numbers that differ in benchmark *and* mode:
  - ScreenSpot — clean, read-only, never trained on. SoM boxes here come from
    the OmniParser detector (it works on any screenshot, no DOM needed) —
    there's no oracle for a static benchmark image, only for the live targets.
  - A DOM-oracle-derived local set — live targets, exact ground-truth boxes.

Cross-benchmark comparisons (e.g. ScreenSpot-raw vs local_oracle-som) are NOT
a clean ablation read — they differ in benchmark difficulty as well as mode.
Only same-benchmark, cross-mode numbers isolate the SoM-vs-raw effect.
"""

import json
import statistics
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .. import ground
from ..browser import Executor
from ..config import settings
from ..detect import omniparser
from ..oracle import get_ground_truth_boxes
from ..protocols import Box
from . import screenspot

REPORTS_DIR = Path(__file__).resolve().parents[3] / "reports"
FIXTURES_DIR = Path(__file__).resolve().parents[3] / "fixtures"


@dataclass
class GroundingResult:
    hit: bool
    normalized_distance: float | None  # None only if the grounder call itself failed
    instruction: str
    benchmark: str
    mode: str  # "raw" | "som"


def _hit_and_distance(
    px: float, py: float, bbox: tuple[float, float, float, float], img_w: int, img_h: int
) -> tuple[bool, float]:
    x, y, w, h = bbox
    hit = x <= px <= x + w and y <= py <= y + h
    cx, cy = x + w / 2, y + h / 2
    diag = (img_w**2 + img_h**2) ** 0.5
    dist = ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5 / diag
    return hit, dist


def _ground_and_score(
    mode: str,
    image_path: Path,
    instruction: str,
    bbox: tuple[float, float, float, float],
    width: int,
    height: int,
    boxes: list[Box] | None = None,
    som_path: Path | None = None,
) -> tuple[bool, float | None]:
    try:
        if mode == "raw":
            action = ground.ground_raw(image_path, instruction, width, height)
            px, py = (float(v) for v in action.target.split(","))
        elif mode == "som":
            action = ground.ground_som(image_path, instruction, boxes, som_path)
            picked = boxes[int(action.target)]
            px, py = picked.x + picked.width / 2, picked.y + picked.height / 2
        else:
            raise ValueError(f"unknown mode {mode!r}")
        return _hit_and_distance(px, py, bbox, width, height)
    except Exception:
        return False, None


def eval_screenspot(mode: str, limit_per_split: int = 5) -> list[GroundingResult]:
    """mode='raw': direct coordinate prediction. mode='som': OmniParser detector
    supplies candidate boxes (no DOM/oracle available for a static benchmark image)."""
    results = []
    for split in screenspot.SPLITS:
        for ex in screenspot.load(split, limit=limit_per_split):
            width, height = Image.open(ex.image_path).size
            boxes, som_path = None, None
            if mode == "som":
                boxes = omniparser.detect_boxes(ex.image_path)
                som_path = FIXTURES_DIR / f"screenspot_{split}_som.png"
            hit, dist = _ground_and_score(mode, ex.image_path, ex.instruction, ex.bbox, width, height, boxes, som_path)
            results.append(
                GroundingResult(hit=hit, normalized_distance=dist, instruction=ex.instruction, benchmark=f"screenspot/{split}", mode=mode)
            )
    return results


def _center(box: dict) -> tuple[float, float]:
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def eval_local_oracle(mode: str, url: str = "http://localhost:8081") -> list[GroundingResult]:
    """mode='som': pick the SoM box matching the labeled target out of every
    oracle-verified candidate. mode='raw': predict (x, y) directly, no boxes."""
    results = []
    with Executor(url) as ex:
        ex.reset()
        for title in ["Buy milk", "Walk the dog", "Write tests"]:
            ex.click(*_center(ex.page.locator("#new-todo").bounding_box()))
            ex.type(title)
            ex.press("Enter")

        shot_path = FIXTURES_DIR / "eval_local.png"
        ex.screenshot(shot_path)
        boxes = get_ground_truth_boxes(ex.page)
        width, height = Image.open(shot_path).size

        for box in boxes:
            if not box.label:
                continue
            instruction = f'click the element labeled "{box.label}"'
            bbox = (box.x, box.y, box.width, box.height)
            hit, dist = _ground_and_score(
                mode, shot_path, instruction, bbox, width, height, boxes, FIXTURES_DIR / "eval_local_som.png"
            )
            results.append(GroundingResult(hit=hit, normalized_distance=dist, instruction=instruction, benchmark="local_oracle/todomvc", mode=mode))
    return results


def summarize(results: list[GroundingResult]) -> dict:
    n = len(results)
    hits = sum(r.hit for r in results)
    distances = [r.normalized_distance for r in results if r.normalized_distance is not None]
    return {
        "n": n,
        "hit_rate": hits / n if n else 0.0,
        "median_normalized_distance": statistics.median(distances) if distances else None,
    }


def run(limit_per_split: int = 5, report_path: Path | None = None) -> dict:
    screenspot_raw = eval_screenspot("raw", limit_per_split)
    screenspot_som = eval_screenspot("som", limit_per_split)
    local_raw = eval_local_oracle("raw")
    local_som = eval_local_oracle("som")

    report = {
        "model": settings.grounder_model,
        "comparability_note": (
            "Compare modes only within the same benchmark row (screenspot.raw vs "
            "screenspot.som, or local_oracle.raw vs local_oracle.som) — that isolates "
            "the SoM-vs-raw effect. Comparing across benchmarks (e.g. screenspot.raw vs "
            "local_oracle.som) conflates benchmark difficulty with mode and is not a "
            "valid ablation read."
        ),
        "screenspot": {
            "note": (
                f"sample of {limit_per_split} examples per split (mobile/desktop/web) from "
                "the clean, read-only ScreenSpot benchmark, not the full ~1.2k set. SoM "
                "boxes here come from the OmniParser detector, not an oracle — ScreenSpot "
                "images are static, there's no DOM to query."
            ),
            "raw": {
                **summarize(screenspot_raw),
                "by_split": {
                    split: summarize([r for r in screenspot_raw if r.benchmark == f"screenspot/{split}"])
                    for split in screenspot.SPLITS
                },
            },
            "som": {
                **summarize(screenspot_som),
                "by_split": {
                    split: summarize([r for r in screenspot_som if r.benchmark == f"screenspot/{split}"])
                    for split in screenspot.SPLITS
                },
            },
        },
        "local_oracle": {
            "note": "DOM-oracle-derived local set from the live todomvc target; boxes are oracle ground truth, not detector output",
            "raw": summarize(local_raw),
            "som": summarize(local_som),
        },
    }

    report_path = report_path or (REPORTS_DIR / "grounding_eval.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
