"""
Core flow engine for the Karumi Rollout QA Kit.

Reads a JSON "flow" file describing a sequence of browser actions against a
target product, drives a real Playwright browser through it, and records
per-step timing, pass/fail status, a screenshot, and (on failure) a
best-effort root-cause suggestion.

This mirrors the shape of what a Forward Deployed Engineer needs before/after
a customer rollout: confirm the agent's planned path through *this specific
product's* UI still works, and get a readable artifact to hand to
product/engineering when it doesn't.
"""
from __future__ import annotations

import base64
import dataclasses
import json
import time
from pathlib import Path
from typing import Any, Optional

from playwright.sync_api import Page, TimeoutError as PWTimeoutError, sync_playwright

DEFAULT_TIMEOUT_MS = 8000


@dataclasses.dataclass
class StepResult:
    index: int
    action: str
    description: str
    selector: Optional[str]
    status: str  # "pass" | "fail" | "skipped"
    duration_ms: int
    screenshot_b64: Optional[str] = None
    error: Optional[str] = None
    suggestion: Optional[str] = None
    attempts: int = 1


@dataclasses.dataclass
class RunResult:
    name: str
    base_url: str
    started_at: str
    total_duration_ms: int
    steps: list[StepResult]

    @property
    def passed(self) -> int:
        return sum(1 for s in self.steps if s.status == "pass")

    @property
    def failed(self) -> int:
        return sum(1 for s in self.steps if s.status == "fail")

    @property
    def skipped(self) -> int:
        return sum(1 for s in self.steps if s.status == "skipped")

    @property
    def ok(self) -> bool:
        return self.failed == 0


def _suggest_fix(action: str, selector: Optional[str], error: Exception) -> str:
    """Best-effort, heuristic root-cause hints. Not magic — just the first
    three things a human would check, so a teammate has somewhere to start."""
    msg = str(error)
    is_timeout = isinstance(error, PWTimeoutError) or "Timeout" in msg

    if action == "assert_text":
        return (
            "The element was found but its text didn't match what the flow config "
            "expected. Either the UI copy differs from what was assumed when the "
            "flow was written, or the underlying data changed. Confirm the actual "
            "text in a live browser and update the flow config's `contains` value."
        )

    if is_timeout and action in ("click", "fill"):
        return (
            f"Selector '{selector}' never became actionable within the timeout. "
            "Most common causes: (1) an overlay/modal is still on screen and "
            "intercepting clicks — add a `dismiss_if_present` step before this one, "
            "(2) the element loads asynchronously and needs a preceding `wait_for`, "
            "or (3) the selector doesn't match this page state — re-inspect the DOM."
        )

    if is_timeout and action == "wait_for":
        return (
            f"Selector '{selector}' never appeared. Check whether this page requires "
            "a prior step (e.g. login, navigation) that didn't complete, whether the "
            "selector is correct for this specific customer's build, or whether the "
            "timeout needs to be longer for a genuinely slow-loading page."
        )

    if "intercepts pointer events" in msg or "outside of the viewport" in msg:
        return (
            "The click target is blocked or off-screen — almost always a modal, "
            "banner, or fixed header sitting on top of it. Dismiss overlays first, "
            "or scroll the element into view before clicking."
        )

    return (
        "Unexpected error for this step. Re-run with --headed to watch it live, "
        "or open the saved screenshot to see the page state at the moment of failure."
    )


def _dismiss_if_present(page: Page, selector: str, wait_ms: int) -> bool:
    """Best-effort dismiss: waits briefly for the element; if it shows up,
    clicks it. If it never appears, that's fine — not every page has a popup
    every time, and this step is never a failure either way."""
    try:
        page.wait_for_selector(selector, timeout=wait_ms, state="visible")
        page.click(selector, timeout=1500)
        return True
    except PWTimeoutError:
        return False


def _run_step(page: Page, step: dict[str, Any]) -> None:
    action = step["action"]
    selector = step.get("selector")
    timeout_ms = step.get("timeout_ms", DEFAULT_TIMEOUT_MS)

    if action == "navigate":
        page.goto(step["_full_url"])
        page.wait_for_load_state("networkidle", timeout=timeout_ms)

    elif action == "click":
        page.click(selector, timeout=timeout_ms)

    elif action == "fill":
        page.fill(selector, step.get("value", ""), timeout=timeout_ms)

    elif action == "wait_for":
        page.wait_for_selector(selector, timeout=timeout_ms, state=step.get("state", "visible"))

    elif action == "dismiss_if_present":
        _dismiss_if_present(page, selector, step.get("wait_ms", 1500))

    elif action == "assert_text":
        expected = step["contains"]
        deadline = time.monotonic() + (timeout_ms / 1000)
        last_seen = ""
        while time.monotonic() < deadline:
            try:
                last_seen = page.inner_text(selector, timeout=1000)
            except PWTimeoutError:
                last_seen = ""
            if expected in last_seen:
                return
            time.sleep(0.2)
        raise AssertionError(f"expected text containing {expected!r}, last saw {last_seen!r}")

    else:
        raise ValueError(f"Unknown step action: {action!r}")


def run_flow(flow: dict[str, Any], headless: bool = True, screenshot_dir: Optional[Path] = None) -> RunResult:
    base_url = flow["base_url"].rstrip("/")
    results: list[StepResult] = []
    run_start = time.monotonic()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        page = browser.new_page(viewport={"width": 1280, "height": 860})

        for i, step in enumerate(flow["steps"], start=1):
            action = step["action"]
            description = step.get("description", action)
            selector = step.get("selector")
            retries = step.get("retries", 0)
            retry_delay_ms = step.get("retry_delay_ms", 800)

            if action == "navigate":
                step = {**step, "_full_url": base_url + step["path"]}

            attempt = 0
            step_start = time.monotonic()
            status, error, suggestion = "pass", None, None

            while True:
                attempt += 1
                try:
                    _run_step(page, step)
                    status = "pass"
                    error = None
                    break
                except Exception as exc:  # noqa: BLE001 - we deliberately catch broadly per-step
                    if attempt <= retries:
                        time.sleep(retry_delay_ms / 1000)
                        continue
                    status = "fail"
                    error = f"{type(exc).__name__}: {exc}"
                    suggestion = _suggest_fix(action, selector, exc)
                    break

            duration_ms = int((time.monotonic() - step_start) * 1000)

            screenshot_b64 = None
            try:
                png_bytes = page.screenshot(type="png")
                screenshot_b64 = base64.b64encode(png_bytes).decode("ascii")
                if screenshot_dir is not None:
                    screenshot_dir.mkdir(parents=True, exist_ok=True)
                    (screenshot_dir / f"step-{i:02d}.png").write_bytes(png_bytes)
            except Exception:  # noqa: BLE001 - screenshots are best-effort
                pass

            results.append(
                StepResult(
                    index=i,
                    action=action,
                    description=description,
                    selector=selector,
                    status=status,
                    duration_ms=duration_ms,
                    screenshot_b64=screenshot_b64,
                    error=error,
                    suggestion=suggestion,
                    attempts=attempt,
                )
            )

            if status == "fail" and step.get("stop_on_fail", True):
                break

        browser.close()

    total_duration_ms = int((time.monotonic() - run_start) * 1000)
    return RunResult(
        name=flow.get("name", "Unnamed flow"),
        base_url=base_url,
        started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        total_duration_ms=total_duration_ms,
        steps=results,
    )


def load_flow(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())
