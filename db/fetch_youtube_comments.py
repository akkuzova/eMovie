"""
Walk a YouTube reviewer's whole channel (default: Chris Stuckmann), match
video titles against movies in the DB, and save top comments locally
(data/scored/<imdb_id>.txt), one comment per line, ready for
save_movie_emotions.py to score.

No OAuth needed -- just a YouTube Data API v3 key (free, self-serve, no
review queue): https://console.cloud.google.com/apis/credentials
Enable "YouTube Data API v3" on the project, create an API key, and set:
    YOUTUBE_API_KEY=...
in .env.

Usage:
    python fetch_youtube_comments.py                          # batch, whole channel
    python fetch_youtube_comments.py --handle @chrisstuckmann  # different channel
    python fetch_youtube_comments.py --dry-run                 # list matches, fetch nothing
"""
import argparse
import os
import re
import sys
import time

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT_DIR = os.path.join(ROOT, "data", "scored")
API_ROOT = "https://www.googleapis.com/youtube/v3"
DEFAULT_HANDLE = "@chrisstuckmann"
COMMENTS_PER_MOVIE = 200
SLEEP_BETWEEN_CALLS = 0.2

load_dotenv(os.path.join(ROOT, ".env"))

# Strip reviewer boilerplate off video titles before matching, e.g.
# "Dune: Part Two - Movie Review" -> "Dune: Part Two"
SUFFIX_RE = re.compile(
    r"\s*[-|:]?\s*(movie review|spoiler review|review|ending explained|"
    r"spoiler talk|breakdown|reaction).*$",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"\((\d{4})\)")
NON_ALNUM_RE = re.compile(r"[^a-z0-9 ]")

# Some review series put the boilerplate *before* the movie title, e.g.
# "Overlooked Movie Review - Broken Arrow (1996)". Detect that (keyword
# followed by a dash/colon early in the string) and use whatever comes
# after it instead of stripping from the end.
PREFIX_RE = re.compile(r"(movie review|spoiler review|review)\s*[-:]\s*", re.IGNORECASE)


def normalize_text(text):
    text = NON_ALNUM_RE.sub("", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def video_title_key(title):
    prefix_match = PREFIX_RE.search(title)
    if prefix_match and prefix_match.start() < 30:
        raw = title[prefix_match.end():]
    else:
        raw = SUFFIX_RE.sub("", title)
    raw = YEAR_RE.sub("", raw)
    return normalize_text(raw)


def normalize(title):
    # kept for catalog titles, which have no reviewer boilerplate to strip
    return video_title_key(title)


def api_get(path, params):
    params = dict(params, key=os.environ["YOUTUBE_API_KEY"])
    resp = requests.get(f"{API_ROOT}/{path}", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_uploads_playlist_id(handle):
    data = api_get(
        "channels", {"part": "contentDetails", "forHandle": handle.lstrip("@")}
    )
    items = data.get("items")
    if not items:
        raise RuntimeError(f"No channel found for handle {handle}")
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def iter_channel_videos(playlist_id):
    page_token = None
    while True:
        data = api_get(
            "playlistItems",
            {
                "part": "snippet",
                "playlistId": playlist_id,
                "maxResults": 50,
                "pageToken": page_token or "",
            },
        )
        for item in data.get("items", []):
            snippet = item["snippet"]
            yield snippet["resourceId"]["videoId"], snippet["title"]
        page_token = data.get("nextPageToken")
        if not page_token:
            return
        time.sleep(SLEEP_BETWEEN_CALLS)


def load_catalog(conn):
    """normalized title -> list of (imdb_id, title, year, imdb_votes)"""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT imdb_id, title, year, imdb_votes FROM movies WHERE year >= 2005;")
    catalog = {}
    for row in cur.fetchall():
        key = normalize(row["title"])
        catalog.setdefault(key, []).append(row)
    return catalog


def match_video(video_title, catalog):
    key = video_title_key(video_title)
    if not key or key not in catalog:
        return None
    candidates = catalog[key]
    year_match = YEAR_RE.search(video_title)
    if year_match:
        year = int(year_match.group(1))
        for c in candidates:
            if c["year"] in (year, year - 1):
                return c
    return max(candidates, key=lambda c: c["imdb_votes"] or 0)


def fetch_top_comments(video_id, limit=COMMENTS_PER_MOVIE):
    comments = []
    page_token = None
    while len(comments) < limit:
        try:
            data = api_get(
                "commentThreads",
                {
                    "part": "snippet",
                    "videoId": video_id,
                    "maxResults": 100,
                    "order": "relevance",
                    "textFormat": "plainText",
                    "pageToken": page_token or "",
                },
            )
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 403:
                return []  # comments disabled
            raise
        for item in data.get("items", []):
            text = item["snippet"]["topLevelComment"]["snippet"]["textDisplay"]
            text = text.strip().replace("\n", " ")
            if text:
                comments.append(text)
            if len(comments) >= limit:
                break
        page_token = data.get("nextPageToken")
        if not page_token:
            break
        time.sleep(SLEEP_BETWEEN_CALLS)
    return comments


def run(handle, dry_run):
    os.makedirs(OUT_DIR, exist_ok=True)
    already_fetched = {f[:-4] for f in os.listdir(OUT_DIR) if f.endswith(".txt")}

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    catalog = load_catalog(conn)
    conn.close()
    print(f"{sum(len(v) for v in catalog.values())} candidate movies (2005+) loaded")

    playlist_id = get_uploads_playlist_id(handle)
    matched = 0
    checked = 0

    for video_id, video_title in iter_channel_videos(playlist_id):
        checked += 1
        movie = match_video(video_title, catalog)
        if not movie:
            continue
        matched += 1
        imdb_id = movie["imdb_id"]
        if imdb_id in already_fetched:
            continue

        print(f"{video_title!r} -> {movie['title']} ({movie['year']}) [{imdb_id}]")
        if dry_run:
            continue

        comments = fetch_top_comments(video_id)
        print(f"  {len(comments)} comments")
        if comments:
            with open(os.path.join(OUT_DIR, f"{imdb_id}.txt"), "w") as f:
                for c in comments:
                    f.write(c + "\n")
        time.sleep(SLEEP_BETWEEN_CALLS)

    print(f"Checked {checked} videos, matched {matched} movies.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--handle", default=DEFAULT_HANDLE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if "YOUTUBE_API_KEY" not in os.environ:
        print("Set YOUTUBE_API_KEY in .env first.")
        sys.exit(1)

    run(args.handle, args.dry_run)
