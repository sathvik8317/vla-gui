"""Phase 1 check: click a known button via oracle-resolved coordinates, assert the
expected DOM state change; all 4 targets reset cleanly. Needs `docker compose up -d`."""

import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

from vlagui.browser import Executor
from vlagui.oracle import resolve_by_label

REPO_ROOT = Path(__file__).resolve().parents[2]
TODOMVC_URL = "http://localhost:8081"
TARGETS = {
    "todomvc": "http://localhost:8081",
    "gitea": "http://localhost:8082",
    "juice-shop": "http://localhost:8083",
    "grafana": "http://localhost:8084",
}


def _center(box: dict) -> tuple[float, float]:
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def test_oracle_click_updates_dom() -> None:
    with Executor(TODOMVC_URL) as ex:
        ex.reset()

        ex.click(*_center(ex.page.locator("#new-todo").bounding_box()))
        ex.type("Buy milk")
        ex.press("Enter")
        assert ex.page.locator("#todo-list li").count() == 1

        box = resolve_by_label(ex.page, 'Delete "Buy milk"')
        assert box is not None, "oracle could not resolve the destroy button by label"

        ex.click(box.x + box.width / 2, box.y + box.height / 2)
        ex.page.wait_for_timeout(200)

        assert ex.page.locator("#todo-list li").count() == 0


@pytest.mark.parametrize("name,url", TARGETS.items())
def test_target_resets_cleanly(name: str, url: str) -> None:
    subprocess.run(
        ["docker", "compose", "up", "-d", "--force-recreate", name],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    _wait_http_ok(url)


def _wait_http_ok(url: str, timeout: float = 60) -> None:
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            resp = urllib.request.urlopen(url, timeout=3)
            assert resp.status < 500
            return
        except Exception as e:  # noqa: BLE001 - polling until the target comes back up
            last_err = e
            time.sleep(1)
    raise AssertionError(f"{url} did not come back up within {timeout}s: {last_err}")
