"""Computes an artist's aggregate engagement summary from crawled data."""
from datetime import datetime, timezone

from src import storage


def compute_and_store_summary(conn, artist):
    fb_rows = conn.execute(
        "SELECT reactions, comments, shares FROM fb_posts WHERE artist = ?", (artist,)
    ).fetchall()
    fb_total = sum(sum(row) for row in fb_rows) if fb_rows else 0

    tiktok_rows = conn.execute(
        "SELECT views, likes, comments, shares FROM tiktok_videos WHERE artist = ?", (artist,)
    ).fetchall()
    tiktok_views = sum(row[0] for row in tiktok_rows) if tiktok_rows else 0
    tiktok_total = sum(sum(row[1:]) for row in tiktok_rows) if tiktok_rows else 0

    threads_rows = conn.execute(
        "SELECT likes, comments, reposts, shares FROM threads_posts WHERE artist = ?", (artist,)
    ).fetchall()
    threads_total = sum(sum(row) for row in threads_rows) if threads_rows else 0

    grand_total = fb_total + tiktok_total + threads_total
    generated_at = datetime.now(timezone.utc).isoformat()

    storage.insert_summary(
        conn, artist, fb_total, tiktok_total, tiktok_views, threads_total, grand_total, generated_at
    )
    return {
        "artist": artist,
        "fb_total": fb_total,
        "tiktok_total": tiktok_total,
        "tiktok_views": tiktok_views,
        "threads_total": threads_total,
        "grand_total": grand_total,
        "generated_at": generated_at,
    }
