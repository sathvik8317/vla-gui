"""Phase 2 check: both detectors return boxes on a fixture screenshot;
SoM render produces a valid image with N visibly numbered labels."""

from pathlib import Path

import pytest
from PIL import Image

from vlagui.browser import Executor
from vlagui.detect import omniparser, opencv
from vlagui.protocols import Box
from vlagui.som import render_som

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"


def _center(box: dict) -> tuple[float, float]:
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


@pytest.fixture(scope="module")
def fixture_screenshot() -> Path:
    """A real screenshot of the live todomvc target with a few todos on it."""
    FIXTURES_DIR.mkdir(exist_ok=True)
    path = FIXTURES_DIR / "todomvc.png"
    with Executor("http://localhost:8081") as ex:
        ex.reset()
        for title in ["Buy milk", "Walk the dog", "Write tests"]:
            ex.click(*_center(ex.page.locator("#new-todo").bounding_box()))
            ex.type(title)
            ex.press("Enter")
        ex.screenshot(path)
    return path


def _assert_valid_boxes(boxes: list[Box]) -> None:
    assert len(boxes) > 0
    for b in boxes:
        assert b.width > 0
        assert b.height > 0


def test_opencv_detector_returns_boxes(fixture_screenshot: Path) -> None:
    _assert_valid_boxes(opencv.detect(fixture_screenshot))


def test_omniparser_detector_returns_boxes(fixture_screenshot: Path) -> None:
    _assert_valid_boxes(omniparser.detect_boxes(fixture_screenshot))


def test_omniparser_captions_are_nonempty(fixture_screenshot: Path) -> None:
    """Full Detector-protocol path: icon-detect (GPU-eligible) + Florence-2 caption (CPU)."""
    boxes = omniparser.detect(fixture_screenshot, max_boxes=5)
    _assert_valid_boxes(boxes)
    assert any(b.label.strip() for b in boxes), "Florence-2 produced no non-empty captions"


def test_som_render_produces_numbered_image(fixture_screenshot: Path) -> None:
    boxes = opencv.detect(fixture_screenshot)
    out = FIXTURES_DIR / "todomvc_som.png"
    render_som(fixture_screenshot, boxes, out)

    assert out.exists()
    img = Image.open(out)
    assert img.size == Image.open(fixture_screenshot).size
    print(f"SoM render: {len(boxes)} numbered boxes -> {out}")
