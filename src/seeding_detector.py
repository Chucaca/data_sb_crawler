"""Heuristic signals for whether an artist's/topic's buzz looks organic or
artificially inflated ("bơm nước" - bot padding, paid seeding, a small
cluster of accounts cranking engagement).

These are heuristics, not proof. Each function returns its raw evidence
(the specific posts/handles involved) alongside a headline number so a human
can judge context - a real fan club naturally reposting the same
congratulatory message looks similar to seeding in these numbers alone.

Requires data collected with collect_comments=True (for duplicate_comment_
ratio and commenter_concentration) and/or multiple crawl runs over time (for
velocity_anomalies, which reads engagement_snapshots - an append-only table
that accumulates one row per post per run).
"""
from datetime import datetime
from statistics import median


def duplicate_comment_ratio(conn, artist, min_cluster_size=3):
    """% of collected comments that belong to a duplicate/near-duplicate
    text cluster of size >= min_cluster_size. High ratio suggests copy-paste
    seeding rather than organic discussion."""
    rows = conn.execute(
        """
        SELECT comment_normalized, COUNT(*) as n
        FROM comments
        WHERE artist = ? AND comment_normalized != ''
        GROUP BY comment_normalized
        """,
        (artist,),
    ).fetchall()

    total_comments = sum(n for _, n in rows)
    if total_comments == 0:
        return {"ratio": 0.0, "total_comments": 0, "clusters": []}

    clusters = [
        {"text_sample": text, "count": n} for text, n in rows if n >= min_cluster_size
    ]
    duplicate_count = sum(c["count"] for c in clusters)
    clusters.sort(key=lambda c: c["count"], reverse=True)

    return {
        "ratio": round(duplicate_count / total_comments, 3),
        "total_comments": total_comments,
        "clusters": clusters[:10],
    }


def commenter_concentration(conn, artist, top_n=5):
    """% of total comment volume contributed by the top_n most frequent
    commenter handles. High concentration suggests a small group (or bot
    network) driving most of the visible activity."""
    rows = conn.execute(
        """
        SELECT commenter_handle, COUNT(*) as n
        FROM comments
        WHERE artist = ? AND commenter_handle IS NOT NULL AND commenter_handle != ''
        GROUP BY commenter_handle
        ORDER BY n DESC
        """,
        (artist,),
    ).fetchall()

    total_comments = sum(n for _, n in rows)
    if total_comments == 0:
        return {"ratio": 0.0, "total_comments": 0, "top_commenters": []}

    top = rows[:top_n]
    top_total = sum(n for _, n in top)

    return {
        "ratio": round(top_total / total_comments, 3),
        "total_comments": total_comments,
        "top_commenters": [{"handle": h, "count": n} for h, n in top],
    }


def velocity_anomalies(conn, artist, growth_multiple=3.0):
    """Per post, computes interactions-per-hour between consecutive
    engagement_snapshots rows and flags posts whose max growth rate is an
    outlier relative to their own median growth rate. Needs at least 3
    snapshots for a post to compute a meaningful median - posts with fewer
    are skipped, not flagged."""
    posts = conn.execute(
        """
        SELECT DISTINCT platform, post_id FROM engagement_snapshots WHERE artist = ?
        """,
        (artist,),
    ).fetchall()

    anomalies = []
    for platform, post_id in posts:
        rows = conn.execute(
            """
            SELECT likes, comments, shares, views, snapshot_at
            FROM engagement_snapshots
            WHERE artist = ? AND platform = ? AND post_id = ?
            ORDER BY snapshot_at ASC
            """,
            (artist, platform, post_id),
        ).fetchall()

        if len(rows) < 3:
            continue

        rates = []
        for (l1, c1, s1, v1, t1), (l2, c2, s2, v2, t2) in zip(rows, rows[1:]):
            dt_hours = (datetime.fromisoformat(t2) - datetime.fromisoformat(t1)).total_seconds() / 3600
            if dt_hours <= 0:
                continue
            total_delta = (l2 + c2 + s2) - (l1 + c1 + s1)
            rates.append(total_delta / dt_hours)

        if len(rates) < 2:
            continue

        med = median(rates)
        max_rate = max(rates)
        if med > 0 and max_rate > med * growth_multiple:
            anomalies.append(
                {
                    "platform": platform,
                    "post_id": post_id,
                    "median_rate_per_hour": round(med, 1),
                    "max_rate_per_hour": round(max_rate, 1),
                    "snapshots_count": len(rows),
                }
            )

    return {"anomalies": anomalies}


def trends_correlation(query, timeframe="now 7-d", geo=""):
    """Best-effort cross-check against Google Trends search interest.
    Google Trends (via pytrends) is known to aggressively rate-limit/block
    non-browser traffic - this returned HTTP 429 consistently while building
    this feature, both from the sandboxed dev environment and against a
    generic unrelated query, suggesting it's not specific to this network.
    Returns available=False with the reason rather than raising, since this
    signal being unavailable shouldn't block the other 3."""
    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="vi-VN", tz=420)
        pytrends.build_payload([query], timeframe=timeframe, geo=geo)
        df = pytrends.interest_over_time()
        if df.empty:
            return {"available": False, "reason": "No Trends data returned for this query/timeframe."}
        return {
            "available": True,
            "series": [
                {"date": str(idx), "interest": int(row[query])} for idx, row in df.iterrows()
            ],
        }
    except Exception as e:
        return {"available": False, "reason": f"{type(e).__name__}: {e}"}
