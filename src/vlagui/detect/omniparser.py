"""OmniParser v2 detector: icon-detect (YOLO) + Florence-2 captioner.

Hard constraint (see CLAUDE.md): the icon-detect half is the only detector
component allowed on GPU at agent runtime. Florence-2 never runs on GPU —
CPU-only, offline, loaded lazily since it's only needed to label boxes, not
to find them.
"""

from pathlib import Path

import torch
from PIL import Image
from ultralytics import YOLO

from ..protocols import Box

_WEIGHTS_DIR = Path(__file__).resolve().parents[3] / "models" / "omniparser"
_ICON_DETECT_WEIGHTS = _WEIGHTS_DIR / "icon_detect" / "model.pt"
_ICON_CAPTION_DIR = _WEIGHTS_DIR / "icon_caption"

_DETECT_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

_yolo: YOLO | None = None
_caption_model = None
_caption_processor = None


def _get_yolo() -> YOLO:
    global _yolo
    if _yolo is None:
        _yolo = YOLO(str(_ICON_DETECT_WEIGHTS))
    return _yolo


def _get_captioner():
    global _caption_model, _caption_processor
    if _caption_model is None:
        from transformers import AutoModelForCausalLM, AutoProcessor

        _caption_model = (
            AutoModelForCausalLM.from_pretrained(
                str(_ICON_CAPTION_DIR), torch_dtype=torch.float32, trust_remote_code=True
            )
            .to("cpu")
            .eval()
        )
        _caption_processor = AutoProcessor.from_pretrained(
            "microsoft/Florence-2-base", trust_remote_code=True
        )
    return _caption_model, _caption_processor


def detect_boxes(screenshot_path: Path, conf: float = 0.05) -> list[Box]:
    """Icon-detect only (GPU-eligible): real bounding boxes, no label yet."""
    result = _get_yolo().predict(str(screenshot_path), device=_DETECT_DEVICE, conf=conf, verbose=False)[0]
    return [
        Box(x=x1, y=y1, width=x2 - x1, height=y2 - y1, label="")
        for x1, y1, x2, y2 in result.boxes.xyxy.tolist()
    ]


def caption_box(image: Image.Image, box: Box) -> str:
    """Florence-2 caption for one cropped icon region. CPU-only."""
    model, processor = _get_captioner()
    crop = image.crop((box.x, box.y, box.x + box.width, box.y + box.height))
    inputs = processor(text="<CAPTION>", images=crop, return_tensors="pt")
    with torch.no_grad():
        generated_ids = model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=inputs["pixel_values"],
            max_new_tokens=20,
            num_beams=1,
        )
    return processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()


def detect(screenshot_path: Path, max_boxes: int = 20) -> list[Box]:
    """Detector protocol: icon-detect boxes (GPU) each labeled by Florence-2 (CPU).

    max_boxes caps how many crops get captioned — captioning is the CPU-bound
    step, so this bounds latency on screenshots with many detections.
    """
    boxes = detect_boxes(screenshot_path)[:max_boxes]
    image = Image.open(screenshot_path)
    return [
        Box(x=b.x, y=b.y, width=b.width, height=b.height, label=caption_box(image, b)) for b in boxes
    ]
