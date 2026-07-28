# Artist Media-Buzz Crawler (Pilot: Soobin)

Collects public engagement counts (likes/reactions, comments, shares, views,
reposts) for an artist's Facebook page, TikTok account, and Threads profile,
aggregates them, and renders an HTML summary report.

## ⚠️ Important disclaimer

**By default**, this tool scrapes **public engagement counts only** — it
does not open, read, or store individual comment text or commenter
identities. An opt-in flag (`--collect-comments`, see below) changes that —
covered in its own section since it's a real expansion of what's collected,
not a minor tweak. Everything below applies regardless of that flag:

- Facebook, TikTok, and Threads don't offer an official public API for this
  use case (reading an arbitrary public figure's engagement metrics — the
  official APIs only expose metrics for accounts you manage yourself). This
  tool works by browser automation instead, which is a **violation of all
  three platforms' Terms of Service**.
- It is intended for **internal/testing use only**.
- It can break at any time if any platform changes its page markup — this
  is not a stable, supported integration.
- TikTok in particular runs active bot detection and will sometimes serve a
  generic "Something went wrong" block page to automated traffic even with a
  valid login session. This is not something the crawler can guarantee its
  way around. Threads has been noticeably more permissive to anonymous
  crawling in testing, but that could change at any time too.
- Using it under an account you don't want at risk of being flagged/limited
  is not recommended; a dedicated/secondary account is safer than a personal
  one, on every platform.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

## Exporting a login session

Anonymous browsing hits a login wall on Facebook, and increases how often
TikTok's bot detection blocks the crawler. For those two, export a real
logged-in session as a Playwright `storage_state`:

1. Run `python scripts/export_session.py <facebook|threads|tiktok> data/<platform>_session.json`
   yourself in a terminal (it needs you to physically log in — don't run it
   through an automated tool). A real Chromium window opens; log in there,
   then press Enter in the terminal when done, and it saves the session.
2. The resulting file lands under `data/` (this directory is gitignored —
   never commit these files, they contain live session cookies. Never share
   them either — anyone with the file can act as your logged-in session).
3. Pass it to the crawler with `--fb-session` / `--tiktok-session` / `--threads-session`.

Threads doesn't require this — anonymous crawling already returns real
numbers for a handful of recent posts. `--threads-session` exists in case a
logged-in session is later needed to see more than that handful, but it's
optional.

## Usage

```bash
python main.py --artist Soobin --limit 20 \
    --fb-session data/fb_session.json \
    --tiktok-session data/tiktok_session.json
```

This will:
1. Crawl the artist's Facebook page, TikTok account, and Threads profile (as configured in `config.yaml`)
2. Store/update rows in `data/media.db` (SQLite)
3. Compute an aggregate summary (total interactions per platform)
4. Write `report.html` in the project root — open it in a browser

Each platform is crawled and stored independently — if one fails (e.g.
TikTok's bot detection kicks in), the others' data is still saved and the
report is still generated from whatever succeeded.

Every run also appends a row per post/video to `engagement_snapshots`
(regardless of the flags below) — this is what lets `--check-seeding`'s
velocity signal see how a post's numbers changed between runs, instead of
only ever seeing the latest reading.

## Detecting artificially inflated buzz ("bơm nước")

Two opt-in flags, meant to answer "does this artist's/topic's buzz look
organic, or is it being padded (bots, paid seeding, a small cluster of
accounts driving most of the activity)?":

### `--collect-comments`

**This expands what the tool collects beyond aggregate counts** — it opens
each post/video's visible comments and stores the **commenter's handle and
the comment text** in a new `comments` table. This is a real change from the
tool's default "aggregate only" stance, so it's opt-in on purpose rather
than silently part of every run.

- **Facebook**: works anonymously (no session needed) — Facebook renders a
  comment or two per post even logged out. Only what's already visible is
  collected; it doesn't click through to expand reply threads.
- **Threads**: reply *content* needs `--threads-session` — a post's
  permalink page shows only the root post anonymously ("Log in or sign up
  for Threads..." gates the replies themselves, unlike the aggregate counts
  which are visible anonymously). Passing `--collect-comments` without a
  Threads session doesn't fail the crawl — it just skips reply extraction
  and still collects the aggregate counts as usual (throwing away working
  anonymous data over a flag combination would be a worse outcome than a
  console note saying comments were skipped). **The reply-scraping
  selectors are UNTESTED** — there was no logged-in Threads session
  available while building this; validate against a real session before
  trusting this data.
- **TikTok**: best-effort, same as the rest of the TikTok crawler — its bot
  detection already blocks most attempts even for aggregate counts, so
  comment collection is unlikely to work reliably right now. **These
  selectors are also UNTESTED** for the same reason (couldn't get past
  TikTok's block to see a real comment section while building this).

### `--check-seeding`

Runs four heuristic checks against whatever's in the database (needs
`--collect-comments` from this run or a prior one for the first two; needs
multiple runs over time for the third) and adds a "Seeding Signals" section
to `report.html`:

1. **Duplicate comment ratio** — % of collected comments that are near-
   identical to others (normalized: lowercased, punctuation stripped). High
   ratio → possible copy-paste seeding.
2. **Commenter concentration** — % of comment volume from just the top 5
   most frequent commenter handles. High concentration → a small group (or
   bot network) may be driving most of the visible activity.
3. **Velocity anomalies** — flags posts whose engagement grew far faster in
   one interval between crawl runs than their own typical growth rate. Needs
   at least 3 crawl runs for a given post to have enough history to judge -
   run the crawler repeatedly over time (e.g. hourly) to build this up.
4. **Google Trends cross-check** — compares social buzz against search
   interest for the same name. **Known to be unreliable**: `pytrends`
   returned HTTP 429 (rate-limited) on the first attempts while building
   this (both on the artist's name and an unrelated test query), then
   succeeded on a later run with no code change — Google Trends' rate-
   limiting of non-browser access is inconsistent, not an outright block.
   Treat this signal as intermittently unavailable rather than something to
   depend on every run.

**None of these are proof of seeding** — they're heuristics to prioritize
what a human should look at. A real, organically enthusiastic fanclub can
produce a similar-looking pattern (everyone posting the same congratulatory
phrase, a few super-fans commenting on everything). Use judgment on the
actual comments/handles involved (returned alongside each signal), not just
the headline percentage.

## Adding another artist

Add a new entry to `config.yaml` (`threads_handle` is optional — omit it to
skip Threads for that artist):

```yaml
artists:
  - name: Soobin
    facebook_url: https://www.facebook.com/soobin.109
    tiktok_handle: soobin.hoangson_official
    threads_handle: soobin.hoangson
  - name: AnotherArtist
    facebook_url: https://www.facebook.com/...
    tiktok_handle: ...
    threads_handle: ...
```

Then run `python main.py --artist AnotherArtist ...`. The `summary` table in
`data/media.db` already stores one row per artist per run, so a future
ranked "Top N" dashboard just needs a query across artists — no schema
change required.

## Troubleshooting

### `SSL: CERTIFICATE_VERIFY_FAILED: self-signed certificate in certificate chain`

This means you're behind a corporate proxy/security software that does TLS
inspection — it re-signs HTTPS traffic with its own root CA. Windows/macOS
already trust that CA (which is why Chromium-based crawling generally still
works), but some Python libraries don't consult the OS trust store by
default.

Fix: `pip install pip-system-certs` — it patches Python to trust the same
certificates as Windows/macOS. Re-run the command after installing it; no
code changes needed. If a specific library still fails because it ships its
own independent TLS stack, export your OS's trusted root CAs to one file and
point that library's CA-bundle setting at it, e.g. on Windows:

```powershell
$certs = Get-ChildItem Cert:\LocalMachine\Root, Cert:\CurrentUser\Root
$lines = foreach ($cert in $certs) {
    "-----BEGIN CERTIFICATE-----"
    [Convert]::ToBase64String($cert.RawData, [System.Base64FormattingOptions]::InsertLineBreaks)
    "-----END CERTIFICATE-----"
}
$lines | Out-File -Encoding ascii "$env:USERPROFILE\windows_root_certs.pem"
```

### TikTok crawl fails with "TikTok blocked automated access..."

This is TikTok's bot detection serving a block page, not a bug — it happens
even with a logged-in session sometimes. There's no reliable workaround
built into this tool; retrying later, using a real (non-headless) browser
profile, or reducing crawl frequency may help but aren't guaranteed.

## Known limitations

- All three platforms' DOM structure changes frequently; the CSS/aria-label/
  `data-e2e` selectors in `facebook_crawler.py` / `tiktok_crawler.py` /
  `threads_crawler.py` may need updating to match current markup if a crawl
  starts returning zero results.
- Threads only surfaces a handful of recent posts to anonymous crawling
  ("Log in to see more..."); a logged-in `--threads-session` may unlock more,
  but that hasn't needed testing since anonymous access already works.
- No sentiment analysis is included by design — only aggregate engagement
  counts (and, with `--collect-comments`, raw comment text/handles for the
  seeding heuristics above - still no sentiment scoring).
- The Threads and TikTok `--collect-comments` selectors are UNTESTED (see
  the section above) - validate before trusting that data.
- `--check-seeding`'s velocity signal only produces results once a post has
  been seen across 3+ crawl runs; on a first-ever run it'll report zero
  anomalies for every post simply because there's no history yet, not
  because nothing's wrong.
