"""CLI entrypoint: crawl an artist's public Facebook + TikTok + Threads
engagement counts, store them, aggregate a summary, and render an HTML report.

Usage:
    python main.py --artist Soobin [--limit 20] \\
        [--fb-session data/fb_session.json] \\
        [--tiktok-session data/tiktok_session.json] \\
        [--threads-session data/threads_session.json] \\
        [--collect-comments] [--check-seeding]
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src import aggregator, seeding_detector, storage
from src.crawlers.facebook_crawler import crawl_facebook_page
from src.crawlers.threads_crawler import crawl_threads_user
from src.crawlers.tiktok_crawler import crawl_tiktok_user
from src.dashboard import render_report

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


def load_artist_config(name):
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    for artist in config.get("artists", []):
        if artist["name"].lower() == name.lower():
            return artist
    raise SystemExit(f"Artist '{name}' not found in config.yaml")


def _record_snapshot_and_comments(conn, artist, platform, items, id_key, collected_at):
    """Appends one engagement_snapshots row per item (every run, regardless of
    --collect-comments - this is what lets velocity_anomalies accumulate
    history), and stores any collected comments. Threads' "reposts" is folded
    into "shares" here since engagement_snapshots tracks 4 generic metrics,
    not a per-platform-specific set."""
    for item in items:
        post_id = item[id_key]
        likes = item.get("likes", item.get("reactions", 0)) or 0
        comments_count = item.get("comments", 0) or 0
        shares = (item.get("shares", 0) or 0) + (item.get("reposts", 0) or 0)
        views = item.get("views", 0) or 0
        storage.insert_snapshot(conn, artist, platform, post_id, likes, comments_count, shares, views, collected_at)

        if item.get("comments_data"):
            storage.insert_comments(conn, artist, platform, post_id, item["comments_data"], collected_at)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artist", required=True, help="Artist name as listed in config.yaml")
    parser.add_argument("--limit", type=int, default=20, help="Max recent posts/videos per platform")
    parser.add_argument(
        "--fb-session",
        default=None,
        help="Path to a Playwright storage_state JSON (exported logged-in Facebook session)",
    )
    parser.add_argument(
        "--tiktok-session",
        default=None,
        help="Path to a Playwright storage_state JSON (exported logged-in TikTok session)",
    )
    parser.add_argument(
        "--threads-session",
        default=None,
        help="Path to a Playwright storage_state JSON (exported logged-in Threads session, optional)",
    )
    parser.add_argument(
        "--collect-comments",
        action="store_true",
        help="Also collect commenter handles + comment text (see README: expands the tool's privacy footprint beyond aggregate counts). Threads requires --threads-session when this is set.",
    )
    parser.add_argument(
        "--check-seeding",
        action="store_true",
        help="After crawling, run heuristic checks for artificially inflated ('bơm nước') buzz and include them in the report.",
    )
    args = parser.parse_args()

    artist_cfg = load_artist_config(args.artist)
    artist_name = artist_cfg["name"]
    collected_at = datetime.now(timezone.utc).isoformat()
    conn = storage.get_connection()

    try:
        print(f"[facebook] crawling {artist_cfg['facebook_url']} (limit={args.limit})")
        fb_posts = crawl_facebook_page(
            artist_cfg["facebook_url"],
            limit=args.limit,
            storage_state=args.fb_session,
            collect_comments=args.collect_comments,
        )
        storage.upsert_fb_posts(conn, artist_name, fb_posts, collected_at)
        _record_snapshot_and_comments(conn, artist_name, "facebook", fb_posts, "post_id", collected_at)
        print(f"[facebook] collected and stored {len(fb_posts)} posts")
    except Exception as e:
        print(f"[facebook] FAILED: {e}")

    try:
        print(f"[tiktok] crawling @{artist_cfg['tiktok_handle']} (limit={args.limit})")
        tiktok_videos = crawl_tiktok_user(
            artist_cfg["tiktok_handle"],
            limit=args.limit,
            storage_state=args.tiktok_session,
            collect_comments=args.collect_comments,
        )
        storage.upsert_tiktok_videos(conn, artist_name, tiktok_videos, collected_at)
        _record_snapshot_and_comments(conn, artist_name, "tiktok", tiktok_videos, "video_id", collected_at)
        print(f"[tiktok] collected and stored {len(tiktok_videos)} videos")
    except Exception as e:
        print(f"[tiktok] FAILED: {e}")

    threads_handle = artist_cfg.get("threads_handle")
    if threads_handle:
        if args.collect_comments and not args.threads_session:
            print("[threads] --collect-comments needs --threads-session for replies; collecting aggregate counts only")
        try:
            print(f"[threads] crawling @{threads_handle} (limit={args.limit})")
            threads_posts = crawl_threads_user(
                threads_handle,
                limit=args.limit,
                storage_state=args.threads_session,
                collect_comments=args.collect_comments,
            )
            storage.upsert_threads_posts(conn, artist_name, threads_posts, collected_at)
            _record_snapshot_and_comments(conn, artist_name, "threads", threads_posts, "post_id", collected_at)
            print(f"[threads] collected and stored {len(threads_posts)} posts")
        except Exception as e:
            print(f"[threads] FAILED: {e}")

    summary = aggregator.compute_and_store_summary(conn, artist_name)
    top_fb = storage.top_fb_posts(conn, artist_name)
    top_tt = storage.top_tiktok_videos(conn, artist_name)
    top_th = storage.top_threads_posts(conn, artist_name)

    seeding_signals = None
    if args.check_seeding:
        print("\n[seeding] running heuristic checks...")
        seeding_signals = {
            "duplicate_comments": seeding_detector.duplicate_comment_ratio(conn, artist_name),
            "commenter_concentration": seeding_detector.commenter_concentration(conn, artist_name),
            "velocity_anomalies": seeding_detector.velocity_anomalies(conn, artist_name),
            "trends": seeding_detector.trends_correlation(artist_name),
        }

    report_path = render_report(summary, top_fb, top_tt, top_th, seeding_signals=seeding_signals)
    conn.close()

    print(f"\nSummary for {artist_name}:")
    print(f"  Facebook total interactions: {summary['fb_total']:,}")
    print(f"  TikTok total interactions:   {summary['tiktok_total']:,}")
    print(f"  TikTok views:                {summary['tiktok_views']:,}")
    print(f"  Threads total interactions:  {summary['threads_total']:,}")
    print(f"  Grand total:                 {summary['grand_total']:,}")
    if seeding_signals:
        print(f"  Duplicate comment ratio:     {seeding_signals['duplicate_comments']['ratio']:.0%}")
        print(f"  Top-5 commenter concentration: {seeding_signals['commenter_concentration']['ratio']:.0%}")
        print(f"  Velocity anomalies flagged:  {len(seeding_signals['velocity_anomalies']['anomalies'])}")
    print(f"\nReport written to {report_path}")


if __name__ == "__main__":
    main()
