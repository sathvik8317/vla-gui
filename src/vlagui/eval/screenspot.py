"""ScreenSpot: a clean, held-out GUI-grounding benchmark. READ-ONLY.

Invariant (see CLAUDE.md): ScreenSpot is never included in fine-tuning data,
never touched by data/build.py or anything resembling a training path. It is
cached under benchmarks/ (gitignored), deliberately outside data/, so there is
no code path from the dataset pipeline that could reach it.
"""

import json
from pathlib import Path
from typing import NamedTuple

from huggingface_hub import hf_hub_download

BENCHMARKS_DIR = Path(__file__).resolve().parents[3] / "benchmarks" / "screenspot"
REPO_ID = "KevinQHLin/ScreenSpot"
SPLITS = ["screenspot_mobile", "screenspot_desktop", "screenspot_web"]


class ScreenSpotExample(NamedTuple):
    image_path: Path
    instruction: str
    bbox: tuple[float, float, float, float]  # x, y, w, h in image pixels
    data_type: str
    data_source: str


def load(split: str, limit: int | None = None) -> list[ScreenSpotExample]:
    """Loads one split, downloading only what's needed (metadata + the sampled images)."""
    meta_path = hf_hub_download(
        REPO_ID, f"metadata/{split}.json", repo_type="dataset", local_dir=BENCHMARKS_DIR
    )
    records = json.loads(Path(meta_path).read_text())
    if limit is not None:
        records = records[:limit]

    examples = []
    for r in records:
        img_path = hf_hub_download(
            REPO_ID, f"images/{r['img_filename']}", repo_type="dataset", local_dir=BENCHMARKS_DIR
        )
        examples.append(
            ScreenSpotExample(
                image_path=Path(img_path),
                instruction=r["instruction"],
                bbox=tuple(r["bbox"]),
                data_type=r["data_type"],
                data_source=r["data_source"],
            )
        )
    return examples
