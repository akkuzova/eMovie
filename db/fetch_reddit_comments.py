"""
Find r/movies "Official Discussion" threads for movies in the DB and save
their comments locally (data/reddit_comments/<imdb_id>.txt), one comment
per line, for later emotion scoring.

Requires a Reddit API app (script type) at https://www.reddit.com/prefs/apps
and these vars in .env:
    REDDIT_CLIENT_ID=...
    REDDIT_CLIENT_SECRET=...
    REDDIT_USER_AGENT=emovie/0.1 by <your reddit username>

Usage:
    python fetch_reddit_comments.py                       # batch over DB
    python fetch_reddit_comments.py --title "Dune" --year 2021   # single lookup, prints instead of saving
"""
import argparse
import os
import re
import time

import praw
import psycopg2
from dotenv import load_dotenv
from prawcore.exceptions import PrawcoreException

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT_DIR = os.path.join(ROOT, "data", "reddit_comments")
ERROR_LOG = os.path.join(ROOT, "data", "reddit_errors.log")
COMMENTS_PER_MOVIE = 300
SLEEP_BETWEEN_MOVIES = 2  # seconds, stay well under the ~100 req/min limit

load_dotenv(os.path.join(ROOT, ".env"))


def get_reddit():
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ.get("REDDIT_USER_AGENT", "emovie/0.1"),
    )


def find_discussion_thread(reddit, title, year):
    """Search r/movies for an Official Discussion thread matching this movie."""
    subreddit = reddit.subreddit("movies")
    query = f'title:"Official Discussion" title:"{title}"'
    candidates = list(subreddit.search(query, sort="relevance", limit=10))

    if not candidates:
        candidates = list(
            subreddit.search(f'"Official Discussion" {title}', sort="relevance", limit=10)
        )

    title_lower = re.sub(r"[^a-z0-9 ]", "", title.lower())
    best = None
    for submission in candidates:
        sub_title_lower = re.sub(r"[^a-z0-9 ]", "", submission.title.lower())
        if "official discussion" not in sub_title_lower:
            continue
        if title_lower not in sub_title_lower:
            continue
        if year and str(year) not in submission.title and str(year - 1) not in submission.title:
            # still allow it; year isn't always in the thread title
            pass
        best = submission
        break

    return best


def fetch_comments(submission, limit=COMMENTS_PER_MOVIE):
    submission.comment_sort = "top"
    submission.comments.replace_more(limit=0)
    comments = []
    for comment in submission.comments.list():
        text = comment.body.strip().replace("\n", " ")
        if text and text not in ("[deleted]", "[removed]"):
            comments.append(text)
        if len(comments) >= limit:
            break
    return comments


def log_error(text):
    os.makedirs(os.path.dirname(ERROR_LOG), exist_ok=True)
    with open(ERROR_LOG, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}\n")


def run_batch():
    os.makedirs(OUT_DIR, exist_ok=True)
    already_fetched = {f[:-4] for f in os.listdir(OUT_DIR) if f.endswith(".txt")}

    reddit = get_reddit()
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute(
        "SELECT imdb_id, title, year FROM movies WHERE year >= 2010 ORDER BY year DESC;"
    )
    movies = cur.fetchall()
    conn.close()

    print(f"{len(movies)} movies from 2010+ to check, {len(already_fetched)} already fetched")

    for imdb_id, title, year in movies:
        if imdb_id in already_fetched:
            continue

        print(f"{imdb_id} | {title} ({year})")
        try:
            submission = find_discussion_thread(reddit, title, year)
            if not submission:
                print("  no discussion thread found")
                continue

            comments = fetch_comments(submission)
            print(f"  found thread, {len(comments)} comments")

            with open(os.path.join(OUT_DIR, f"{imdb_id}.txt"), "w") as f:
                for c in comments:
                    f.write(c + "\n")

        except PrawcoreException as e:
            log_error(f"{imdb_id} {title} ({year}): {e}")
            print(f"  error: {e}")

        time.sleep(SLEEP_BETWEEN_MOVIES)


def run_single(title, year):
    reddit = get_reddit()
    submission = find_discussion_thread(reddit, title, year)
    if not submission:
        print("No discussion thread found.")
        return
    print(f"Found: {submission.title} ({submission.url})")
    comments = fetch_comments(submission, limit=20)
    for c in comments:
        print("-", c[:200])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--title")
    parser.add_argument("--year", type=int)
    args = parser.parse_args()

    if args.title:
        run_single(args.title, args.year)
    else:
        run_batch()
