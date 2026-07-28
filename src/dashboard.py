"""Renders a static HTML report for an artist's aggregated engagement summary."""
from pathlib import Path

REPORT_PATH = Path(__file__).resolve().parent.parent / "report.html"

_TEMPLATE = """<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<title>Media Buzz Report - {artist}</title>
<style>
  body {{
    font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
    background: #0b1e3d;
    color: #fff;
    margin: 0;
    padding: 40px;
  }}
  .card {{
    max-width: 640px;
    margin: 0 auto;
    background: #12294f;
    border-radius: 16px;
    padding: 32px;
  }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .subtitle {{ color: #9fb3d1; font-size: 13px; margin-bottom: 24px; }}
  .metric-row {{ display: flex; justify-content: space-between; margin: 12px 0; }}
  .metric-label {{ color: #9fb3d1; font-size: 13px; }}
  .metric-value {{ font-size: 20px; font-weight: 700; }}
  .bar-track {{ background: #0b1e3d; border-radius: 6px; height: 10px; overflow: hidden; margin-top: 6px; }}
  .bar-fill {{ height: 100%; border-radius: 6px; }}
  .fb-fill {{ background: #3b82f6; }}
  .tt-fill {{ background: #ec4899; }}
  .th-fill {{ background: #f59e0b; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 13px; }}
  th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #1e3a63; }}
  th {{ color: #9fb3d1; font-weight: 500; }}
  a {{ color: #93c5fd; text-decoration: none; }}
  .generated {{ color: #64748b; font-size: 11px; margin-top: 24px; }}
  .seeding-section {{ margin-top: 28px; padding-top: 20px; border-top: 1px solid #1e3a63; }}
  .seeding-caveat {{ color: #9fb3d1; font-size: 12px; margin-bottom: 12px; }}
  .signal {{ margin-bottom: 14px; }}
  .signal-label {{ font-size: 13px; color: #9fb3d1; }}
  .signal-value {{ font-size: 18px; font-weight: 700; }}
  .signal-flag {{ color: #f87171; }}
  .signal-ok {{ color: #4ade80; }}
  .signal-na {{ color: #64748b; font-style: italic; font-size: 13px; }}
</style>
</head>
<body>
  <div class="card">
    <h1>{artist}</h1>
    <div class="subtitle">Media buzz - tổng hợp tương tác</div>

    <div class="metric-row">
      <div>
        <div class="metric-label">Tổng tương tác (Facebook)</div>
        <div class="metric-value">{fb_total:,}</div>
        <div class="bar-track"><div class="bar-fill fb-fill" style="width:{fb_pct}%"></div></div>
      </div>
    </div>
    <div class="metric-row">
      <div>
        <div class="metric-label">Tổng tương tác (TikTok)</div>
        <div class="metric-value">{tiktok_total:,}</div>
        <div class="bar-track"><div class="bar-fill tt-fill" style="width:{tt_pct}%"></div></div>
      </div>
    </div>
    <div class="metric-row">
      <div>
        <div class="metric-label">Tổng tương tác (Threads)</div>
        <div class="metric-value">{threads_total:,}</div>
        <div class="bar-track"><div class="bar-fill th-fill" style="width:{th_pct}%"></div></div>
      </div>
    </div>
    <div class="metric-row">
      <div class="metric-label">Lượt xem TikTok</div>
      <div class="metric-value">{tiktok_views:,}</div>
    </div>
    <div class="metric-row">
      <div class="metric-label">Tổng cộng</div>
      <div class="metric-value">{grand_total:,}</div>
    </div>

    <h3>Top bài viết Facebook</h3>
    <table>
      <tr><th>URL</th><th>Reactions</th><th>Comments</th><th>Shares</th></tr>
      {fb_rows}
    </table>

    <h3>Top video TikTok</h3>
    <table>
      <tr><th>URL</th><th>Views</th><th>Likes</th><th>Comments</th><th>Shares</th></tr>
      {tt_rows}
    </table>

    <h3>Top bài viết Threads</h3>
    <table>
      <tr><th>URL</th><th>Likes</th><th>Comments</th><th>Reposts</th><th>Shares</th></tr>
      {th_rows}
    </table>

    {seeding_section}

    <div class="generated">Generated at {generated_at}</div>
  </div>
</body>
</html>
"""

_SEEDING_TEMPLATE = """
<div class="seeding-section">
  <h3>Seeding Signals (heuristic - not proof)</h3>
  <div class="seeding-caveat">
    Dấu hiệu nghi ngờ buzz bị bơm thổi, dựa trên comment/tài khoản đã thu thập.
    Đây là gợi ý để xem xét thêm, không phải kết luận chắc chắn - một fanclub
    thật cũng có thể tạo ra pattern tương tự.
  </div>

  <div class="signal">
    <div class="signal-label">Tỉ lệ comment trùng lặp/gần giống nhau</div>
    <div class="signal-value {dup_class}">{dup_pct} ({dup_total} comment đã thu thập)</div>
  </div>

  <div class="signal">
    <div class="signal-label">Mức độ tập trung vào top 5 người bình luận nhiều nhất</div>
    <div class="signal-value {conc_class}">{conc_pct}</div>
  </div>

  <div class="signal">
    <div class="signal-label">Bài viết có tốc độ tăng tương tác bất thường</div>
    <div class="signal-value {vel_class}">{vel_count} bài</div>
  </div>

  <div class="signal">
    <div class="signal-label">Đối chiếu Google Trends</div>
    <div class="signal-value signal-na">{trends_status}</div>
  </div>
</div>
"""


def _render_seeding_section(seeding_signals):
    if not seeding_signals:
        return ""

    dup = seeding_signals["duplicate_comments"]
    conc = seeding_signals["commenter_concentration"]
    vel = seeding_signals["velocity_anomalies"]
    trends = seeding_signals["trends"]

    dup_pct = f"{dup['ratio']:.0%}"
    conc_pct = f"{conc['ratio']:.0%}"

    return _SEEDING_TEMPLATE.format(
        dup_pct=dup_pct,
        dup_total=dup["total_comments"],
        dup_class="signal-flag" if dup["ratio"] >= 0.3 else "signal-ok",
        conc_pct=conc_pct,
        conc_class="signal-flag" if conc["ratio"] >= 0.5 else "signal-ok",
        vel_count=len(vel["anomalies"]),
        vel_class="signal-flag" if vel["anomalies"] else "signal-ok",
        trends_status=(
            f"Có dữ liệu ({len(trends['series'])} điểm) - xem thủ công để so sánh với timeline tương tác ở trên"
            if trends["available"]
            else f"Không lấy được ({trends['reason']})"
        ),
    )


def _fb_row(post):
    return (
        f"<tr><td><a href='{post['url']}'>{(post['url'] or '')[:40]}</a></td>"
        f"<td>{post['reactions']:,}</td><td>{post['comments']:,}</td><td>{post['shares']:,}</td></tr>"
    )


def _tt_row(video):
    return (
        f"<tr><td><a href='{video['url']}'>{(video['url'] or '')[:40]}</a></td>"
        f"<td>{video['views']:,}</td><td>{video['likes']:,}</td>"
        f"<td>{video['comments']:,}</td><td>{video['shares']:,}</td></tr>"
    )


def _th_row(post):
    return (
        f"<tr><td><a href='{post['url']}'>{(post['url'] or '')[:40]}</a></td>"
        f"<td>{post['likes']:,}</td><td>{post['comments']:,}</td>"
        f"<td>{post['reposts']:,}</td><td>{post['shares']:,}</td></tr>"
    )


def render_report(
    summary, top_fb_posts, top_tiktok_videos, top_threads_posts=None, seeding_signals=None, output_path=None
):
    top_threads_posts = top_threads_posts or []
    fb_total = summary["fb_total"] or 0
    tiktok_total = summary["tiktok_total"] or 0
    threads_total = summary.get("threads_total") or 0
    denom = max(fb_total + tiktok_total + threads_total, 1)
    fb_pct = round(100 * fb_total / denom)
    tt_pct = round(100 * tiktok_total / denom)
    th_pct = round(100 * threads_total / denom)

    html = _TEMPLATE.format(
        artist=summary["artist"],
        fb_total=fb_total,
        tiktok_total=tiktok_total,
        tiktok_views=summary["tiktok_views"] or 0,
        threads_total=threads_total,
        grand_total=summary["grand_total"] or 0,
        generated_at=summary["generated_at"],
        fb_pct=fb_pct,
        tt_pct=tt_pct,
        th_pct=th_pct,
        fb_rows="\n".join(_fb_row(p) for p in top_fb_posts) or "<tr><td colspan='4'>No data</td></tr>",
        tt_rows="\n".join(_tt_row(v) for v in top_tiktok_videos) or "<tr><td colspan='5'>No data</td></tr>",
        th_rows="\n".join(_th_row(p) for p in top_threads_posts) or "<tr><td colspan='5'>No data</td></tr>",
        seeding_section=_render_seeding_section(seeding_signals),
    )

    path = output_path or REPORT_PATH
    path.write_text(html, encoding="utf-8")
    return path
