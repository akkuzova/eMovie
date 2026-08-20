"""
Import the IMDb non-commercial movie catalog (title, director, year) into
the `movies` table. Source: https://datasets.imdbws.com/ (free bulk dumps).

Streams straight from the downloaded .gz files (no full decompression to
disk) and filters early so memory stays bounded despite the name.basics
file covering ~14M people.

Usage:
    python import_movies.py
"""
import os

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
CHUNK_SIZE = 200_000

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

print("Reading title.basics.tsv.gz (filtering to titleType == 'movie')...")
movie_chunks = []
for chunk in pd.read_csv(
    os.path.join(DATA_DIR, "title.basics.tsv.gz"),
    sep="\t",
    compression="gzip",
    usecols=["tconst", "titleType", "primaryTitle", "startYear"],
    dtype=str,
    na_values="\\N",
    chunksize=CHUNK_SIZE,
):
    movie_chunks.append(chunk[chunk["titleType"] == "movie"])
movies = pd.concat(movie_chunks, ignore_index=True).drop(columns=["titleType"])
movies["startYear"] = pd.to_numeric(movies["startYear"], errors="coerce")
print(f"{len(movies)} movies found")

movie_ids = set(movies["tconst"])

print("Reading title.crew.tsv.gz (filtering to our movie ids)...")
crew_chunks = []
for chunk in pd.read_csv(
    os.path.join(DATA_DIR, "title.crew.tsv.gz"),
    sep="\t",
    compression="gzip",
    usecols=["tconst", "directors"],
    dtype=str,
    na_values="\\N",
    chunksize=CHUNK_SIZE,
):
    crew_chunks.append(chunk[chunk["tconst"].isin(movie_ids)])
crew = pd.concat(crew_chunks, ignore_index=True)
crew["first_director_nconst"] = crew["directors"].str.split(",").str[0]

movies = movies.merge(crew[["tconst", "first_director_nconst"]], on="tconst", how="left")
director_ids = set(movies["first_director_nconst"].dropna())
print(f"{len(director_ids)} unique directors to resolve")

print("Reading name.basics.tsv.gz (filtering to our director ids)...")
name_chunks = []
for chunk in pd.read_csv(
    os.path.join(DATA_DIR, "name.basics.tsv.gz"),
    sep="\t",
    compression="gzip",
    usecols=["nconst", "primaryName"],
    dtype=str,
    na_values="\\N",
    chunksize=CHUNK_SIZE,
):
    name_chunks.append(chunk[chunk["nconst"].isin(director_ids)])
names = pd.concat(name_chunks, ignore_index=True)

movies = movies.merge(
    names, left_on="first_director_nconst", right_on="nconst", how="left"
)
movies = movies.rename(
    columns={"tconst": "imdb_id", "primaryTitle": "title", "startYear": "year", "primaryName": "director"}
)
movies = movies[["imdb_id", "title", "director", "year"]]
movies["year"] = movies["year"].astype("Int64")

print(f"Loading {len(movies)} rows into CockroachDB...")
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

rows = [
    (r.imdb_id, r.title, r.director if pd.notna(r.director) else None, int(r.year) if pd.notna(r.year) else None)
    for r in movies.itertuples(index=False)
]

BATCH = 5000
for i in range(0, len(rows), BATCH):
    batch = rows[i : i + BATCH]
    execute_values(
        cur,
        """
        INSERT INTO movies (imdb_id, title, director, year)
        VALUES %s
        ON CONFLICT (imdb_id) DO UPDATE
        SET title = EXCLUDED.title, director = EXCLUDED.director, year = EXCLUDED.year
        """,
        batch,
        template="(%s::text, %s::text, %s::text, %s::int)",
    )
    conn.commit()
    print(f"  {min(i + BATCH, len(rows))}/{len(rows)}")

cur.execute("SELECT count(*) FROM movies;")
print(f"Done. movies table now has {cur.fetchone()[0]} rows.")
conn.close()
