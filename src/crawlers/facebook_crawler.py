"""Scrapes public engagement counts (reactions/comments/shares) from a Facebook
page's timeline. By default does NOT open or store individual comments/
commenter identities - pass collect_comments=True to opt into that (see
README: this materially changes the tool's privacy footprint).

Facebook's markup changes frequently and isn't a documented API surface, so
the selectors below are best-effort and may need adjusting when Facebook
ships a layout change. Anonymous access almost always hits a login wall,
hence the optional storage_state session.

Facebook reuses div[role="article"] for BOTH top-level posts and each
comment nested inside a post - naively treating every match as a separate
post double-counts comments as posts. Top-level posts are the ones with no
article ancestor; anything nested inside is a comment.
"""
import re
from playwright.sync_api import sync_playwright

from src.utils import parse_count

LOGIN_WALL_MARKERS = [
    "log in to continue",
    "đăng nhập để tiếp tục",
    "you must log in",
]

_RELATIVE_TIME_RE = re.compile(
    r"^\d+\s*(giây|phút|giờ|ngày|tuần|tháng|năm|s|sec|m|min|h|hr|d|w|mo|y|yr)s?\b",
    re.IGNORECASE,
)


def _is_login_wall(page_text):
    lowered = page_text.lower()
    return any(marker in lowered for marker in LOGIN_WALL_MARKERS)


def _is_top_level(article):
    return article.locator('xpath=ancestor::div[@role="article"]').count() == 0


def _extract_comments(post_article):
    """Best-effort: only picks up comments already rendered in the DOM (an
    anonymous view typically shows one or two per post) - doesn't click
    through reply threads."""
    comments = []
    comment_articles = post_article.locator('div[role="article"]')
    n = comment_articles.count()
    for i in range(n):
        c = comment_articles.nth(i)
        try:
            name_links = c.locator('a[role="link"]')
            commenter_handle = None
            for j in range(name_links.count()):
                text = name_links.nth(j).inner_text().strip()
                if text and not _RELATIVE_TIME_RE.match(text):
                    commenter_handle = text
                    break

            text_el = c.locator('div[dir="auto"]').first
            comment_text = text_el.inner_text().strip() if text_el.count() > 0 else ""
            if not comment_text:
                continue

            comments.append(
                {
                    "commenter_handle": commenter_handle,
                    "comment_text": comment_text,
                    "posted_at": None,
                }
            )
        except Exception:
            continue
    return comments


def crawl_facebook_page(page_url, limit=20, storage_state=None, collect_comments=False):
    """Returns a list of dicts: post_id, url, posted_at, reactions, comments,
    shares, and (only when collect_comments=True) a "comments" key holding a
    list of {commenter_handle, comment_text, posted_at}."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=storage_state)
        page = context.new_page()
        page.goto(page_url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(3000)

        body_text = page.inner_text("body")
        if _is_login_wall(body_text):
            browser.close()
            raise RuntimeError(
                f"Hit a Facebook login wall at {page_url}. Provide a valid "
                "storage_state session (see README) to scrape this page."
            )

        all_articles = page.locator('div[role="article"]')
        stagnant_rounds = 0
        while all_articles.count() < limit and stagnant_rounds < 5:
            before = all_articles.count()
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(1500)
            after = all_articles.count()
            stagnant_rounds = stagnant_rounds + 1 if after == before else 0

        top_level_indices = [i for i in range(all_articles.count()) if _is_top_level(all_articles.nth(i))]

        results = []
        for i in top_level_indices[:limit]:
            article = all_articles.nth(i)
            try:
                post_url = None
                link = article.locator('a[href*="/posts/"], a[href*="/videos/"], a[href*="story_fbid"]').first
                if link.count() > 0:
                    post_url = link.get_attribute("href")

                reactions_text = ""
                reactions_el = article.locator('[aria-label*="reactions" i], [aria-label*="cảm xúc" i]').first
                if reactions_el.count() > 0:
                    reactions_text = reactions_el.get_attribute("aria-label") or ""

                comments_text = ""
                comments_el = article.locator('[aria-label*="comment" i], [aria-label*="bình luận" i]').first
                if comments_el.count() > 0:
                    comments_text = comments_el.get_attribute("aria-label") or ""

                shares_text = ""
                shares_el = article.locator('[aria-label*="share" i], [aria-label*="chia sẻ" i]').first
                if shares_el.count() > 0:
                    shares_text = shares_el.get_attribute("aria-label") or ""

                post_id_match = re.search(r"(?:posts|videos)/(\w+)", post_url or "")
                post_id = post_id_match.group(1) if post_id_match else f"unknown-{i}-{hash(post_url) if post_url else i}"

                post = {
                    "post_id": post_id,
                    "url": post_url,
                    "posted_at": None,
                    "reactions": parse_count(reactions_text),
                    "comments": parse_count(comments_text),
                    "shares": parse_count(shares_text),
                }
                if collect_comments:
                    post["comments_data"] = _extract_comments(article)
                results.append(post)
            except Exception:
                # Best-effort per-post extraction; skip a post that doesn't match
                # the expected markup rather than failing the whole crawl.
                continue

        browser.close()
        return results
