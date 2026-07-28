"""Scrapes public engagement counts (views/likes/comments/shares) from a
TikTok account's videos via Playwright. By default does NOT open or store
individual comment text or commenter identities - pass collect_comments=True
to opt into that (see README: this materially changes the tool's privacy
footprint).

TikTok's anti-bot measures are aggressive against anonymous/headless traffic
(it will often serve a generic "Something went wrong" block page instead of
a login wall or captcha). A logged-in session (storage_state) significantly
reduces how often this happens, similar to the Facebook crawler.

TikTok's DOM changes over time; the data-e2e attributes used below are the
common, relatively stable hooks used across most public TikTok scrapers, but
may need adjusting if TikTok ships a redesign. The comment-list selectors in
particular are UNTESTED - TikTok's bot detection blocked every attempt to
reach a video page in the environment this was built in, so there was no
live comment section to verify against. Validate before relying on this.
"""
import re

from playwright.sync_api import sync_playwright

from src.utils import parse_count

BLOCK_PAGE_MARKERS = [
    "something went wrong",
    "đã xảy ra lỗi",
    "please try again later",
]


def _is_blocked(page_text):
    lowered = page_text.lower()
    return any(marker in lowered for marker in BLOCK_PAGE_MARKERS)


def _extract_comments(page):
    """Best-effort, UNTESTED (see module docstring)."""
    comments = []
    items = page.locator('[data-e2e="comment-item"]')
    n = items.count()
    for i in range(n):
        c = items.nth(i)
        try:
            handle_el = c.locator('[data-e2e="comment-username-1"]').first
            handle = handle_el.inner_text().strip() if handle_el.count() > 0 else None
            text_el = c.locator('[data-e2e="comment-level-1"]').first
            text = text_el.inner_text().strip() if text_el.count() > 0 else ""
            if not text:
                continue
            comments.append({"commenter_handle": handle, "comment_text": text, "posted_at": None})
        except Exception:
            continue
    return comments


def crawl_tiktok_user(handle, limit=20, storage_state=None, collect_comments=False):
    """Returns a list of dicts: video_id, url, posted_at, views, likes,
    comments, shares, and (only when collect_comments=True) a "comments_data"
    key holding a list of {commenter_handle, comment_text, posted_at}."""
    handle = handle.lstrip("@")
    profile_url = f"https://www.tiktok.com/@{handle}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=storage_state)
        page = context.new_page()
        page.goto(profile_url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(3000)

        body_text = page.inner_text("body")
        if _is_blocked(body_text):
            browser.close()
            raise RuntimeError(
                f"TikTok blocked automated access to {profile_url} (bot check, "
                "not a certificate/config issue). Providing a logged-in "
                "storage_state session (see README) reduces how often this "
                "happens, but TikTok's block is not guaranteed to be avoidable."
            )

        items = page.locator('div[data-e2e="user-post-item"]')
        stagnant_rounds = 0
        while items.count() < limit and stagnant_rounds < 5:
            before = items.count()
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(1500)
            after = items.count()
            stagnant_rounds = stagnant_rounds + 1 if after == before else 0

        video_stubs = []
        count = min(items.count(), limit)
        for i in range(count):
            item = items.nth(i)
            link = item.locator("a").first
            href = link.get_attribute("href") if link.count() > 0 else None
            if not href:
                continue
            views_el = item.locator('[data-e2e="video-views"]').first
            views_text = views_el.inner_text() if views_el.count() > 0 else ""
            video_id_match = re.search(r"/video/(\d+)", href)
            video_stubs.append(
                {
                    "video_id": video_id_match.group(1) if video_id_match else href,
                    "url": href,
                    "views": parse_count(views_text),
                }
            )

        results = []
        for stub in video_stubs:
            try:
                page.goto(stub["url"], wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(2000)

                if _is_blocked(page.inner_text("body")):
                    # Best-effort per-video: skip this one rather than aborting
                    # the whole crawl, same pattern as the Facebook crawler.
                    continue

                def _count_for(e2e_name):
                    el = page.locator(f'[data-e2e="{e2e_name}"]').first
                    return parse_count(el.inner_text()) if el.count() > 0 else 0

                video = {
                    "video_id": stub["video_id"],
                    "url": stub["url"],
                    "posted_at": None,
                    "views": stub["views"],
                    "likes": _count_for("like-count"),
                    "comments": _count_for("comment-count"),
                    "shares": _count_for("share-count"),
                }
                if collect_comments:
                    video["comments_data"] = _extract_comments(page)
                results.append(video)
            except Exception:
                continue

        browser.close()
        return results
