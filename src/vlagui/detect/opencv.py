"""Contour-based fallback detector — no ML weights, also the ablation arm for "no OmniParser"."""

from pathlib import Path

import cv2
import numpy as np

from ..protocols import Box


def detect(screenshot_path: Path, min_area: int = 200, max_area_ratio: float = 0.25) -> list[Box]:
    image = cv2.imread(str(screenshot_path))
    if image is None:
        raise FileNotFoundError(screenshot_path)
    height, width = image.shape[:2]

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.dilate(cv2.Canny(gray, 50, 150), np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    boxes: list[Box] = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h
        if area < min_area or area > max_area_ratio * width * height:
            continue
        boxes.append(Box(x=float(x), y=float(y), width=float(w), height=float(h), label=""))
    return boxes
