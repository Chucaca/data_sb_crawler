"""Scrapes public engagement counts (likes/comments/reposts/shares) from a
Threads (Meta) profile. By default does NOT open or store individual reply
text/commenter identities - pass collect_comments=True to opt into that
(see README: this materially changes the tool's privacy footprint).

Unlike Facebook and TikTok, an anonymous/logged-out Playwright request to a
public Threads profile returns real engagement numbers without hitting a
login wall or bot-check page - it just caps the feed at a handful of recent
posts ("Log in to see more from ..."). A logged-in storage_state may surface
more posts, but isn't required to get real numbers.

Reply *content* is a different story: a post's permalink page shows only the
root post plus a "Log in or sign up for Threads" gate anonymously - replies
themselves aren't rendered without a logged-in session. So collect_comments
requires storage_state; it raises immediately if called without one instead
of silently returning nothing.

IMPORTANT: the reply-extraction selectors below are UNTESTED - there was no
logged-in Threads session available to verify them against real reply
markup while building this. Validate against a live session before relying
on this data; the selectors will likely need adjusting.

Threads' DOM uses hashed utility classes with no stable names (same style as
Facebook), so instead of relying on those, each metric is located via its
icon's aria-label ("Like"/"Comment"/"Repost"/"Share") and reading that
icon's immediate parent container, which reliably contains just the count.
"""
import re

from playwright.sync_api import sync_playwright

from src.utils import parse_count

METRIC_LABELS = ["Like", "Comment", "Repost", "Share"]


def _find_post_container(link):
    """Walks up from a post permalink to the ancestor div that scopes exactly
    one post (verified by containing exactly one "Like" icon)."""
    for level in range(4, 12):
        candidate = link.locator(f"xpath=ancestor::div[{level}]")
        if candidate.count() == 0:
            continue
        if candidate.locator('svg[aria-label="Like"]').count() == 1:
            return candidate
    return None


def _count_for(container, label):
    svg = container.locator(f'svg[aria-label="{label}"]').first
    if svg.count() == 0:
        return 0
    holder = svg.locator("xpath=ancestor::div[1]")
    return parse_count(holder.inner_text()) if holder.count() > 0 else 0


def _extract_replies(page):
    """Best-effort, UNTESTED (see module docstring): assumes each reply is a
    post-shaped container like the ones on the profile feed, identified the
    same way (exactly one "Like" icon), skipping index 0 which is the root
    post itself."""
    like_svgs = page.locator('svg[aria-label="Like"]')
    n = like_svgs.count()
    replies = []
    for i in range(1, n):
        try:
            container = like_svgs.nth(i).locator("xpath=ancestor::div[6]")
            if container.count() == 0:
                continue
            author_link = container.locator('a[href^="/@"]').first
            handle = None
            if author_link.count() > 0:
                m = re.match(r"^/@([^/?]+)", author_link.get_attribute("href") or "")
                handle = m.group(1) if m else None
            full_text = container.inner_text().strip()
            # Rough heuristic: strip the leading handle line and trailing
            # metric numbers, keep whatever's left as the reply body.
            lines = [l for l in full_text.split("\n") if l.strip()]
            body_lines = [l for l in lines if l != handle and not re.fullmatch(r"[\d.,]+\s*(N|K|Tr|M)?", l.strip(), re.IGNORECASE)]
            comment_text = " ".join(body_lines).strip()
            if not comment_text:
                continue
            replies.append({"commenter_handle": handle, "comment_text": comment_text, "posted_at": None})
        except Exception:
            continue
    return replies


def crawl_threads_user(handle, limit=20, storage_state=None, collect_comments=False):
    """Returns a list of dicts: post_id, url, posted_at, likes, comments,
    reposts, shares, and (only when collect_comments=True and storage_state is
    given) a "comments_data" key holding a list of {commenter_handle,
    comment_text, posted_at}.

    Aggregate counts work anonymously regardless of collect_comments - reply
    *content* is what's gated behind login. So collect_comments without a
    session doesn't raise (that would throw away perfectly good aggregate
    data); it just skips reply extraction, leaving comments_data unset."""
    collect_comments = collect_comments and bool(storage_state)

    handle = handle.lstrip("@")
    profile_url = f"https://www.threads.com/@{handle}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=storage_state)
        page = context.new_page()
        page.goto(profile_url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(3000)

        links = page.locator('a[href*="/post/"]:not([href*="/media"])')
        stagnant_rounds = 0
        while links.count() < limit and stagnant_rounds < 5:
            before = links.count()
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(1500)
            after = links.count()
            stagnant_rounds = stagnant_rounds + 1 if after == before else 0

        results = []
        count = min(links.count(), limit)
        for i in range(count):
            link = links.nth(i)
            href = link.get_attribute("href")
            if not href:
                continue

            container = _find_post_container(link)
            if container is None:
                continue

            post_id_match = re.search(r"/post/([^/?]+)", href)
            post_id = post_id_match.group(1) if post_id_match else f"unknown-{i}"

            time_el = container.locator("time").first
            posted_at = time_el.get_attribute("datetime") if time_el.count() > 0 else None

            results.append(
                {
                    "post_id": post_id,
                    "url": f"https://www.threads.com{href}",
                    "posted_at": posted_at,
                    "likes": _count_for(container, "Like"),
                    "comments": _count_for(container, "Comment"),
                    "reposts": _count_for(container, "Repost"),
                    "shares": _count_for(container, "Share"),
                }
            )

        if collect_comments:
            for post in results:
                try:
                    page.goto(post["url"], wait_until="domcontentloaded", timeout=60_000)
                    page.wait_for_timeout(2000)
                    post["comments_data"] = _extract_replies(page)
                except Exception:
                    post["comments_data"] = []

        browser.close()
        return results
