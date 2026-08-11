"""Playwright executor: screenshot, click, type, scroll, reset — all at real screen coordinates."""

from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from .config import settings


class Executor:
    def __init__(self, url: str, headless: bool = True):
        self.start_url = url
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=headless)
        self.page: Page = self._browser.new_page(
            viewport={"width": settings.viewport.width, "height": settings.viewport.height},
            device_scale_factor=settings.viewport.device_scale_factor,
        )
        self.page.goto(url)

    def screenshot(self, path: Path) -> Path:
        self.page.screenshot(path=str(path))
        return path

    def click(self, x: float, y: float) -> None:
        self.page.mouse.click(x, y)

    def type(self, text: str) -> None:
        """Types into whichever element a prior click() focused."""
        self.page.keyboard.type(text)

    def press(self, key: str) -> None:
        self.page.keyboard.press(key)

    def scroll(self, dx: float = 0, dy: float = 0) -> None:
        self.page.mouse.wheel(dx, dy)

    def reset(self) -> None:
        """Client-side reset: clear storage and reload. Server-side target state
        resets via container recreation — see targets/README.md."""
        self.page.evaluate("localStorage.clear(); sessionStorage.clear();")
        self.page.goto(self.start_url)

    def close(self) -> None:
        self._browser.close()
        self._playwright.stop()

    def __enter__(self) -> "Executor":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
