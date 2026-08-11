"""DOM/a11y tree -> labeled ground-truth boxes. Eval + labeling ONLY — never imported
by plan.py, ground.py, or orchestrate.py. The agent must never see the DOM."""

from playwright.sync_api import Page

from .protocols import Box

INTERACTIVE_SELECTOR = "button, a, input, select, textarea, [role='button'], [role='link'], [role='checkbox']"


def get_ground_truth_boxes(page: Page) -> list[Box]:
    """Every visible interactive element's real bounding box + accessible label."""
    elements = page.locator(INTERACTIVE_SELECTOR)
    boxes: list[Box] = []
    for i in range(elements.count()):
        el = elements.nth(i)
        if not el.is_visible():
            continue
        box = el.bounding_box()
        if box is None:
            continue
        label = (
            el.get_attribute("aria-label")
            or el.get_attribute("placeholder")
            or el.inner_text().strip()
            or el.get_attribute("name")
            or ""
        )
        boxes.append(Box(x=box["x"], y=box["y"], width=box["width"], height=box["height"], label=label))
    return boxes


def resolve_by_label(page: Page, label: str) -> Box | None:
    """Oracle click-target lookup for eval: exact accessible-label match."""
    for box in get_ground_truth_boxes(page):
        if box.label == label:
            return box
    return None
