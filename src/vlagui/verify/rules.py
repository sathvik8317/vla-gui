"""Rule-based verifier (primary): DOM delta + perceptual hash + task assertion.

Deliberately does NOT import oracle.py — orchestrate.py must never reach the
DOM through the oracle module (see CLAUDE.md invariants). DOM state instead
comes in as plain strings (dom_before/dom_after, e.g. page.content()) that the
caller captures itself; this module never touches Playwright.
"""

import hashlib
from pathlib import Path

from PIL import Image

from ..schema import VerifierResult


def _perceptual_hash(image_path: Path, hash_size: int = 8) -> str:
    """Cheap perceptual hash: downsample to grayscale, threshold each pixel vs the mean."""
    img = Image.open(image_path).convert("L").resize((hash_size, hash_size))
    pixels = list(img.getdata())
    avg = sum(pixels) / len(pixels)
    bits = "".join("1" if p > avg else "0" for p in pixels)
    return hashlib.sha1(bits.encode()).hexdigest()


def verify(
    before_screenshot: Path,
    after_screenshot: Path,
    task_assertion: str,
    dom_before: str | None = None,
    dom_after: str | None = None,
) -> VerifierResult:
    """success: the DOM changed AND task_assertion holds in the after-DOM.
    failure: neither the screen nor the DOM changed at all.
    uncertain: the screen changed but the DOM signal is unavailable or ambiguous.

    task_assertion is a substring that must be present in the after-DOM, or —
    prefixed with "!" — a substring that must be ABSENT (e.g. "!Buy milk" for
    a delete task, since deletion can't be phrased as presence of something).
    """
    visually_changed = _perceptual_hash(before_screenshot) != _perceptual_hash(after_screenshot)

    if dom_before is None or dom_after is None:
        return "uncertain" if visually_changed else "failure"

    dom_changed = hashlib.sha1(dom_before.encode()).hexdigest() != hashlib.sha1(dom_after.encode()).hexdigest()
    if task_assertion.startswith("!"):
        assertion_met = task_assertion[1:] not in dom_after
    else:
        assertion_met = task_assertion in dom_after

    if dom_changed and assertion_met:
        return "success"
    if not dom_changed and not visually_changed:
        return "failure"
    return "uncertain"
