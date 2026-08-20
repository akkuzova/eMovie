"""
Shared DB helpers for the Streamlit app: auth (simple username/password) and
movie search + watchlist queries.
"""
import hashlib
import hmac
import os
import secrets

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

ROOT = os.path.join(os.path.dirname(__file__), "..")
load_dotenv(os.path.join(ROOT, ".env"))

CA_CERT = os.path.join(os.path.dirname(__file__), "root.crt")


def get_conn():
    kwargs = {"sslrootcert": CA_CERT} if os.path.exists(CA_CERT) else {}
    return psycopg2.connect(os.environ["DATABASE_URL"], **kwargs)


def _hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000)
    return f"{salt}${digest.hex()}"


def _verify_password(password, stored):
    salt, _ = stored.split("$", 1)
    return hmac.compare_digest(_hash_password(password, salt), stored)


def create_user(username, password):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id;",
            (username, _hash_password(password)),
        )
        user_id = cur.fetchone()[0]
        conn.commit()
        return user_id
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return None
    finally:
        conn.close()


def authenticate(username, password):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, password_hash FROM users WHERE username = %s;", (username,))
    row = cur.fetchone()
    conn.close()
    if not row or not row[1]:
        return None
    user_id, stored_hash = row
    return user_id if _verify_password(password, stored_hash) else None


SORT_OPTIONS = {
    "Rating": "imdb_rating DESC NULLS LAST, imdb_votes DESC NULLS LAST",
    "Votes": "imdb_votes DESC NULLS LAST",
    "Year (newest)": "year DESC NULLS LAST, title",
    "Title": "title",
}


def search_movies(query, year=None, limit=50, offset=0, sort_by="Rating"):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    sql = (
        "SELECT id, imdb_id, title, director, year, emotions, imdb_rating, imdb_votes "
        "FROM movies WHERE 1=1"
    )
    params = []
    if query:
        sql += " AND title ILIKE %s"
        params.append(f"%{query}%")
    if year:
        sql += " AND year = %s"
        params.append(year)
    order_by = SORT_OPTIONS.get(sort_by, SORT_OPTIONS["Rating"])
    sql += f" ORDER BY {order_by} LIMIT %s OFFSET %s;"
    params += [limit, offset]
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return rows


def get_watchlist(user_id):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT m.id, m.imdb_id, m.title, m.director, m.year, m.emotions,
               m.imdb_rating, m.imdb_votes, w.added_at
        FROM watchlist w
        JOIN movies m ON m.id = w.movie_id
        WHERE w.user_id = %s
        ORDER BY w.added_at DESC;
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def watchlist_movie_ids(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT movie_id FROM watchlist WHERE user_id = %s;", (user_id,))
    ids = {row[0] for row in cur.fetchall()}
    conn.close()
    return ids


def add_to_watchlist(user_id, movie_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO watchlist (user_id, movie_id, added_by)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, movie_id) DO NOTHING;
        """,
        (user_id, movie_id, user_id),
    )
    conn.commit()
    conn.close()


def remove_from_watchlist(user_id, movie_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM watchlist WHERE user_id = %s AND movie_id = %s;",
        (user_id, movie_id),
    )
    conn.commit()
    conn.close()
