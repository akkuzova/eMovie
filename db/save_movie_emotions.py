"""
Score all data/scored/<imdb_id>.txt files (one comment per line) with the
trained emotion classifier and write the full 28-label average vector into
movies.emotions as JSONB.

Usage:
    python save_movie_emotions.py
"""
import collections
import json
import os
import sys

import psycopg2
from dotenv import load_dotenv

ROOT = os.path.join(os.path.dirname(__file__), "..")
SCORED_DIR = os.path.join(ROOT, "data", "scored")
sys.path.insert(0, os.path.join(ROOT, "src"))

from classify_text import classify  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))


def score_file(path):
    totals = collections.Counter()
    n = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            n += 1
            for label, score in classify(line, top_k=28):
                totals[label] += score
    return {label: round(total / n, 4) for label, total in totals.items()}, n


def main():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    for filename in sorted(os.listdir(SCORED_DIR)):
        if not filename.endswith(".txt"):
            continue
        imdb_id = filename[:-4]
        path = os.path.join(SCORED_DIR, filename)
        emotions, n_comments = score_file(path)
        emotions["_comment_count"] = n_comments

        cur.execute(
            "UPDATE movies SET emotions = %s WHERE imdb_id = %s RETURNING title;",
            (json.dumps(emotions), imdb_id),
        )
        row = cur.fetchone()
        title = row[0] if row else "(no matching movie!)"
        print(f"{imdb_id} {title}: {n_comments} comments scored")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
