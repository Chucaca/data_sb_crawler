"""One-off helper: opens a real (visible) browser window, lets you log in
manually, then saves the session as a Playwright storage_state JSON for use
with main.py's --fb-session / --threads-session / --tiktok-session flags.

Run this yourself in a terminal (not via an automated tool) - you need to
see the browser window and type your own credentials into it.

Usage:
    python scripts/export_session.py threads data/threads_session.json
    python scripts/export_session.py facebook data/fb_session.json
    python scripts/export_session.py tiktok data/tiktok_session.json
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

LOGIN_URLS = {
    "facebook": "https://www.facebook.com/login",
    "threads": "https://www.threads.com/login",
    "tiktok": "https://www.tiktok.com/login",
}


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in LOGIN_URLS:
        print(f"Usage: python {sys.argv[0]} <facebook|threads|tiktok> <output_path.json>")
        sys.exit(1)

    platform, output_path = sys.argv[1], Path(sys.argv[2])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(LOGIN_URLS[platform])
        input(f"\nLog into {platform} in the opened browser window, then press Enter here when done... ")
        context.storage_state(path=str(output_path))
        browser.close()
        print(f"Session saved to {output_path}")


if __name__ == "__main__":
    main()
