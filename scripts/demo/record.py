#!/usr/bin/env python3
"""Record a silent screen-capture tour of the LiveKit Dashboard's main
features, running against the real LiveKit server configured in the
project's .env file.

What it does:
  1. Creates real rooms with real simulated participants (genuine WebRTC
     audio/video) on your LiveKit server (see live_rooms.py).
  2. Starts the dashboard itself (uvicorn, against your real .env) on a
     scratch port so it doesn't collide with anything you have running.
  3. Drives a real Chromium browser through Overview, Rooms, Room detail
     (pin, tag/note, RTC stats), Session Summary, Egress, Agents, Sandbox,
     and Settings, recording a video of the whole tour.
  4. Cleans up: disconnects participants, deletes the demo rooms, stops
     the dashboard subprocess.

Requires `poetry install` (playwright is a dev dependency) and, once,
`poetry run playwright install chromium`.

Usage:
    poetry run python scripts/demo/record.py [--out-dir docs/video/raw] [--port 8098]
"""

import argparse
import asyncio
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import dotenv_values  # noqa: E402

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")


async def wait_for_health(base_url: str, timeout: float = 20.0) -> None:
    import httpx

    deadline = time.monotonic() + timeout
    async with httpx.AsyncClient() as client:
        while time.monotonic() < deadline:
            try:
                resp = await client.get(f"{base_url}/health", timeout=2.0)
                if resp.status_code == 200:
                    return
            except Exception:
                pass
            await asyncio.sleep(0.5)
    raise RuntimeError(f"dashboard at {base_url} never became healthy")


async def run_tour(page, base_url: str) -> None:
    """The actual click-through. Deliberately paced for narration later."""

    async def pause(ms: int) -> None:
        await page.wait_for_timeout(ms)

    # --- Overview ---
    await page.goto(f"{base_url}/", wait_until="networkidle")
    await pause(6000)
    await page.mouse.wheel(0, 500)
    await pause(5000)
    await page.mouse.wheel(0, 500)
    await pause(4000)

    # --- Rooms list ---
    await page.goto(f"{base_url}/rooms", wait_until="networkidle")
    await pause(5000)
    # Pin "support-standup"
    pin_form = page.locator('form[action="/rooms/support-standup/pin"] button')
    if await pin_form.count():
        await pin_form.first.click()
        await page.wait_for_load_state("networkidle")
    await pause(4000)

    # --- Room detail: support-standup ---
    await page.goto(f"{base_url}/rooms/support-standup", wait_until="networkidle")
    await pause(5000)
    # Tag + note
    tag_trigger = page.locator('[data-bs-target="#annotateModal"]')
    if await tag_trigger.count():
        await tag_trigger.first.click()
        await pause(1000)
        prod_tag = page.locator("#tag_prod")
        if await prod_tag.count():
            await prod_tag.check()
        note = page.locator("#annotate_note")
        if await note.count():
            await note.fill("Daily support standup - live customer line.")
        await pause(1500)
        save_btn = page.locator('#annotateModal button[type="submit"]')
        if await save_btn.count():
            await save_btn.click()
            await page.wait_for_load_state("networkidle")
    await pause(3000)
    # RTC stats
    refresh_btn = page.get_by_text("Refresh Stats")
    if await refresh_btn.count():
        await refresh_btn.first.click()
        await pause(4000)
    await pause(3000)

    # --- Session Summary: design-review (short-lived room) ---
    await page.goto(f"{base_url}/rooms/design-review/summary", wait_until="networkidle")
    await pause(7000)

    # --- Egress ---
    await page.goto(f"{base_url}/egress", wait_until="networkidle")
    await pause(4000)
    start_btn = page.locator('[data-bs-target="#startEgressModal"]')
    if await start_btn.count():
        await start_btn.first.click()
        await pause(1000)
        room_input = page.locator('#compositeEgressForm input[name="room_name"]')
        file_input = page.locator('#compositeEgressForm input[name="output_filename"]')
        if await room_input.count():
            await room_input.fill("webinar-launch-q4")
        if await file_input.count():
            await file_input.fill("webinar-launch-q4-{time}.mp4")
        await pause(4000)
        cancel_btn = page.locator("#startEgressModal .btn-secondary")
        if await cancel_btn.count():
            await cancel_btn.first.click()
    await pause(2500)

    # --- Agents ---
    await page.goto(f"{base_url}/agents", wait_until="networkidle")
    await pause(5000)
    dispatch_trigger = page.locator('[data-bs-target="#createDispatchModal"]')
    if await dispatch_trigger.count():
        await dispatch_trigger.first.click()
        await pause(1000)
        await page.locator("#dispatch-agent-name").fill("demo-copilot")
        await page.locator("#dispatch-room").fill("webinar-launch-q4")
        await pause(1500)
        submit_btn = page.locator("#createDispatchModal button[type='submit']")
        if await submit_btn.count():
            await submit_btn.first.click()
            await page.wait_for_load_state("networkidle")
    await pause(5000)

    # --- Sandbox: generate a token ---
    await page.goto(f"{base_url}/sandbox", wait_until="networkidle")
    await pause(3000)
    await page.locator("#room").fill("webinar-launch-q4")
    await page.locator("#identity").fill("test-viewer")
    await pause(1500)
    await page.locator('button[type="submit"].btn-lg').first.click()
    await page.wait_for_load_state("networkidle")
    token_heading = page.get_by_text("Token Generated!")
    if await token_heading.count():
        await token_heading.first.scroll_into_view_if_needed()
    await pause(7000)

    # --- Settings ---
    await page.goto(f"{base_url}/settings", wait_until="networkidle")
    await pause(7000)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8098)
    parser.add_argument("--out-dir", default=os.path.join(PROJECT_ROOT, "docs", "video", "raw"))
    args = parser.parse_args()

    env_values = dotenv_values(ENV_PATH)
    for required in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "ADMIN_USERNAME", "ADMIN_PASSWORD"):
        if not env_values.get(required):
            raise SystemExit(f"{required} must be set in .env to record the demo")

    os.makedirs(args.out_dir, exist_ok=True)
    base_url = f"http://127.0.0.1:{args.port}"

    print("Starting dashboard subprocess against real .env ...")
    # Isolate every file-backed local store (room history, notes/tags,
    # pinned rooms, security log, ...) under a fresh scratch dir for this
    # recording run, so it starts from a clean slate and never reads or
    # writes the developer's real local dashboard state (same precedent as
    # tests/conftest.py's per-test isolation fixtures). Only these ancillary
    # caches are isolated -- LIVEKIT_URL/KEY/SECRET still point at the real
    # server from .env.
    scratch_dir = tempfile.mkdtemp(prefix="livekit-dashboard-demo-")
    server_env = dict(os.environ)
    for env_var, filename in {
        "WEBHOOK_LOG_FILE": "webhook_log.json",
        "ALERT_RULES_FILE": "alert_rules.json",
        "SECURITY_LOG_FILE": "security_log.json",
        "ROOM_ANNOTATIONS_FILE": "room_annotations.json",
        "GHOST_ROOMS_FILE": "ghost_rooms.json",
        "AUDIT_LOG_FILE": "audit_log.json",
        "REPORT_RULES_FILE": "report_rules.json",
        "NOTIFICATIONS_FILE": "notifications_config.json",
        "IP_ALLOWLIST_FILE": "ip_allowlist.json",
        "SAVED_VIEWS_FILE": "saved_views.json",
        "ROOM_HISTORY_FILE": "room_history.json",
    }.items():
        server_env[env_var] = os.path.join(scratch_dir, filename)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(args.port)],
        cwd=PROJECT_ROOT,
        env=server_env,
    )
    try:
        await wait_for_health(base_url, timeout=25)
        print("Dashboard is up. Seeding real rooms + participants ...")

        from live_rooms import build_demo_session

        session = await build_demo_session(
            env_values["LIVEKIT_URL"], env_values["LIVEKIT_API_KEY"], env_values["LIVEKIT_API_SECRET"]
        )
        try:
            print("Waiting for the room poller to observe the design-review lifecycle ...")
            await asyncio.sleep(30)

            from playwright.async_api import async_playwright

            async with async_playwright() as pw:
                browser = await pw.chromium.launch()
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    record_video_dir=args.out_dir,
                    record_video_size={"width": 1920, "height": 1080},
                    http_credentials={
                        "username": env_values["ADMIN_USERNAME"],
                        "password": env_values["ADMIN_PASSWORD"],
                    },
                )
                page = await context.new_page()
                print("Recording tour ...")
                await run_tour(page, base_url)
                await context.close()
                video_path = await page.video.path()
                await browser.close()
                print(f"Recording saved to: {video_path}")
        finally:
            print("Cleaning up demo rooms and participants ...")
            await session.cleanup(delete_rooms=True)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    asyncio.run(main())
