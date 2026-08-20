"""
Backfill imdb_rating / imdb_votes on the `movies` table from IMDb's
title.ratings.tsv.gz (free non-commercial bulk dump).

Usage:
    python import_ratings.py
"""
import os

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
CHUNK_SIZE = 200_000

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
cur.execute("SELECT imdb_id FROM movies;")
movie_ids = {row[0] for row in cur.fetchall()}
print(f"{len(movie_ids)} movies in catalog")

print("Reading title.ratings.tsv.gz (filtering to our movie ids)...")
rating_chunks = []
for chunk in pd.read_csv(
    os.path.join(DATA_DIR, "title.ratings.tsv.gz"),
    sep="\t",
    compression="gzip",
    usecols=["tconst", "averageRating", "numVotes"],
    dtype=str,
    na_values="\\N",
    chunksize=CHUNK_SIZE,
):
    rating_chunks.append(chunk[chunk["tconst"].isin(movie_ids)])
ratings = pd.concat(rating_chunks, ignore_index=True)
print(f"{len(ratings)} ratings matched to our catalog")

rows = [
    (r.tconst, float(r.averageRating), int(r.numVotes))
    for r in ratings.itertuples(index=False)
]

BATCH = 5000
for i in range(0, len(rows), BATCH):
    batch = rows[i : i + BATCH]
    execute_values(
        cur,
        """
        UPDATE movies AS m
        SET imdb_rating = v.rating, imdb_votes = v.votes
        FROM (VALUES %s) AS v (imdb_id, rating, votes)
        WHERE m.imdb_id = v.imdb_id
        """,
        batch,
        template="(%s::text, %s::numeric, %s::bigint)",
    )
    conn.commit()
    print(f"  {min(i + BATCH, len(rows))}/{len(rows)}")

cur.execute("SELECT count(*) FROM movies WHERE imdb_rating IS NOT NULL;")
print(f"Done. {cur.fetchone()[0]} movies now have a rating.")
conn.close()
