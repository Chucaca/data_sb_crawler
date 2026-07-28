"""SQLite storage for crawled engagement counts and per-artist summaries."""
import sqlite3
from pathlib import Path

from src.utils import normalize_comment

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "media.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS fb_posts (
    artist TEXT NOT NULL,
    post_id TEXT NOT NULL,
    url TEXT,
    posted_at TEXT,
    reactions INTEGER,
    comments INTEGER,
    shares INTEGER,
    collected_at TEXT NOT NULL,
    PRIMARY KEY (artist, post_id)
);

CREATE TABLE IF NOT EXISTS tiktok_videos (
    artist TEXT NOT NULL,
    video_id TEXT NOT NULL,
    url TEXT,
    posted_at TEXT,
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
    shares INTEGER,
    collected_at TEXT NOT NULL,
    PRIMARY KEY (artist, video_id)
);

CREATE TABLE IF NOT EXISTS threads_posts (
    artist TEXT NOT NULL,
    post_id TEXT NOT NULL,
    url TEXT,
    posted_at TEXT,
    likes INTEGER,
    comments INTEGER,
    reposts INTEGER,
    shares INTEGER,
    collected_at TEXT NOT NULL,
    PRIMARY KEY (artist, post_id)
);

CREATE TABLE IF NOT EXISTS comments (
    artist TEXT NOT NULL,
    platform TEXT NOT NULL,
    post_id TEXT NOT NULL,
    commenter_handle TEXT,
    comment_text TEXT,
    comment_normalized TEXT,
    posted_at TEXT,
    collected_at TEXT NOT NULL,
    PRIMARY KEY (artist, platform, post_id, commenter_handle, comment_text)
);

CREATE TABLE IF NOT EXISTS engagement_snapshots (
    artist TEXT NOT NULL,
    platform TEXT NOT NULL,
    post_id TEXT NOT NULL,
    likes INTEGER,
    comments INTEGER,
    shares INTEGER,
    views INTEGER,
    snapshot_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS summary (
    artist TEXT NOT NULL,
    fb_total INTEGER,
    tiktok_total INTEGER,
    tiktok_views INTEGER,
    threads_total INTEGER,
    grand_total INTEGER,
    generated_at TEXT NOT NULL,
    PRIMARY KEY (artist, generated_at)
);
"""


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def upsert_fb_posts(conn, artist, posts, collected_at):
    conn.executemany(
        """
        INSERT INTO fb_posts (artist, post_id, url, posted_at, reactions, comments, shares, collected_at)
        VALUES (:artist, :post_id, :url, :posted_at, :reactions, :comments, :shares, :collected_at)
        ON CONFLICT(artist, post_id) DO UPDATE SET
            url=excluded.url,
            posted_at=excluded.posted_at,
            reactions=excluded.reactions,
            comments=excluded.comments,
            shares=excluded.shares,
            collected_at=excluded.collected_at
        """,
        [{**p, "artist": artist, "collected_at": collected_at} for p in posts],
    )
    conn.commit()


def upsert_tiktok_videos(conn, artist, videos, collected_at):
    conn.executemany(
        """
        INSERT INTO tiktok_videos (artist, video_id, url, posted_at, views, likes, comments, shares, collected_at)
        VALUES (:artist, :video_id, :url, :posted_at, :views, :likes, :comments, :shares, :collected_at)
        ON CONFLICT(artist, video_id) DO UPDATE SET
            url=excluded.url,
            posted_at=excluded.posted_at,
            views=excluded.views,
            likes=excluded.likes,
            comments=excluded.comments,
            shares=excluded.shares,
            collected_at=excluded.collected_at
        """,
        [{**v, "artist": artist, "collected_at": collected_at} for v in videos],
    )
    conn.commit()


def upsert_threads_posts(conn, artist, posts, collected_at):
    conn.executemany(
        """
        INSERT INTO threads_posts (artist, post_id, url, posted_at, likes, comments, reposts, shares, collected_at)
        VALUES (:artist, :post_id, :url, :posted_at, :likes, :comments, :reposts, :shares, :collected_at)
        ON CONFLICT(artist, post_id) DO UPDATE SET
            url=excluded.url,
            posted_at=excluded.posted_at,
            likes=excluded.likes,
            comments=excluded.comments,
            reposts=excluded.reposts,
            shares=excluded.shares,
            collected_at=excluded.collected_at
        """,
        [{**p, "artist": artist, "collected_at": collected_at} for p in posts],
    )
    conn.commit()


def insert_comments(conn, artist, platform, post_id, comments, collected_at):
    """comments: list of dicts with commenter_handle, comment_text, posted_at.
    Duplicate (artist, platform, post_id, commenter_handle, comment_text) rows
    from re-crawling the same post are silently skipped, not updated - a
    comment's text doesn't change once posted."""
    conn.executemany(
        """
        INSERT OR IGNORE INTO comments
            (artist, platform, post_id, commenter_handle, comment_text, comment_normalized, posted_at, collected_at)
        VALUES (:artist, :platform, :post_id, :commenter_handle, :comment_text, :comment_normalized, :posted_at, :collected_at)
        """,
        [
            {
                "artist": artist,
                "platform": platform,
                "post_id": post_id,
                "commenter_handle": c.get("commenter_handle"),
                "comment_text": c.get("comment_text"),
                "comment_normalized": normalize_comment(c.get("comment_text")),
                "posted_at": c.get("posted_at"),
                "collected_at": collected_at,
            }
            for c in comments
        ],
    )
    conn.commit()


def insert_snapshot(conn, artist, platform, post_id, likes, comments, shares, views, snapshot_at):
    """Append-only - every crawl run adds a new row so velocity_anomalies()
    has history to compare against, unlike the upsert-based *_posts/*_videos
    tables which only ever hold the latest reading."""
    conn.execute(
        """
        INSERT INTO engagement_snapshots (artist, platform, post_id, likes, comments, shares, views, snapshot_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (artist, platform, post_id, likes, comments, shares, views, snapshot_at),
    )
    conn.commit()


def insert_summary(
    conn, artist, fb_total, tiktok_total, tiktok_views, threads_total, grand_total, generated_at
):
    conn.execute(
        """
        INSERT INTO summary (artist, fb_total, tiktok_total, tiktok_views, threads_total, grand_total, generated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (artist, fb_total, tiktok_total, tiktok_views, threads_total, grand_total, generated_at),
    )
    conn.commit()


def latest_summary(conn, artist):
    row = conn.execute(
        """
        SELECT artist, fb_total, tiktok_total, tiktok_views, threads_total, grand_total, generated_at
        FROM summary WHERE artist = ?
        ORDER BY generated_at DESC LIMIT 1
        """,
        (artist,),
    ).fetchone()
    if row is None:
        return None
    cols = ["artist", "fb_total", "tiktok_total", "tiktok_views", "threads_total", "grand_total", "generated_at"]
    return dict(zip(cols, row))


def top_fb_posts(conn, artist, limit=5):
    cols = ["url", "posted_at", "reactions", "comments", "shares"]
    rows = conn.execute(
        f"""
        SELECT {', '.join(cols)} FROM fb_posts
        WHERE artist = ?
        ORDER BY (reactions + comments + shares) DESC LIMIT ?
        """,
        (artist, limit),
    ).fetchall()
    return [dict(zip(cols, r)) for r in rows]


def top_tiktok_videos(conn, artist, limit=5):
    cols = ["url", "posted_at", "views", "likes", "comments", "shares"]
    rows = conn.execute(
        f"""
        SELECT {', '.join(cols)} FROM tiktok_videos
        WHERE artist = ?
        ORDER BY (likes + comments + shares) DESC LIMIT ?
        """,
        (artist, limit),
    ).fetchall()
    return [dict(zip(cols, r)) for r in rows]


def top_threads_posts(conn, artist, limit=5):
    cols = ["url", "posted_at", "likes", "comments", "reposts", "shares"]
    rows = conn.execute(
        f"""
        SELECT {', '.join(cols)} FROM threads_posts
        WHERE artist = ?
        ORDER BY (likes + comments + reposts + shares) DESC LIMIT ?
        """,
        (artist, limit),
    ).fetchall()
    return [dict(zip(cols, r)) for r in rows]
