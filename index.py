import datetime
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "db"))
import db  # noqa: E402

st.set_page_config(page_title="eMovie", page_icon="🎬", layout="wide")

PAGE_SIZE = 20

if "user_id" not in st.session_state:
    # Restore login from the URL query param so a page reload doesn't log
    # the user out (a fresh reload gets a brand new session_state).
    uid = st.query_params.get("uid")
    username = db.get_username(uid) if uid else None
    st.session_state.user_id = uid if username else None
    st.session_state.username = username
    if not username:
        st.query_params.pop("uid", None)
def get_page():
    try:
        return max(1, int(st.query_params.get("page", "1")))
    except (TypeError, ValueError):
        return 1


def set_page(page):
    st.query_params["page"] = str(page)


def log_in(user_id, username):
    st.session_state.user_id = user_id
    st.session_state.username = username
    st.query_params["uid"] = user_id


def log_out():
    st.session_state.user_id = None
    st.session_state.username = None
    st.query_params.pop("uid", None)


def top_emotions(emotions, n=3):
    if not emotions:
        return None
    pairs = [(k, v) for k, v in emotions.items() if not k.startswith("_")]
    pairs.sort(key=lambda p: p[1], reverse=True)
    return ", ".join(f"{k} ({v:.2f})" for k, v in pairs[:n])


def render_header():
    cols = st.columns([5, 2, 2, 2, 3, 2])
    cols[0].markdown("**Title**")
    cols[1].markdown("**Director**")
    cols[2].markdown("**Rating**")
    cols[3].markdown("**IMDb**")
    cols[4].markdown("**Emotions**")
    cols[5].markdown("**Watchlist**")
    st.divider()


def render_movie_row(movie, in_watchlist_ids):
    cols = st.columns([5, 2, 2, 2, 3, 2])
    year = movie["year"] or "—"
    cols[0].markdown(f"**{movie['title']}** ({year})")
    cols[1].write(movie["director"] or "—")
    if movie["imdb_rating"] is not None:
        votes = movie["imdb_votes"] or 0
        cols[2].write(f"{movie['imdb_rating']} ({votes:,})")
    else:
        cols[2].write("—")
    cols[3].markdown(f"[IMDb](https://www.imdb.com/title/{movie['imdb_id']}/)")
    emotions_str = top_emotions(movie["emotions"])
    cols[4].write(emotions_str or "_not scored yet_")

    if st.session_state.user_id:
        in_watchlist = movie["id"] in in_watchlist_ids
        key = f"wl_{movie['id']}"
        if in_watchlist:
            if cols[5].button("Remove", key=key):
                db.remove_from_watchlist(st.session_state.user_id, movie["id"])
                st.rerun()
        else:
            if cols[5].button("+ Watchlist", key=key):
                db.add_to_watchlist(st.session_state.user_id, movie["id"])
                st.rerun()


# --- Sidebar: auth ---
with st.sidebar:
    st.title("eMovie 🎬")
    if st.session_state.user_id:
        st.write(f"Signed in as **{st.session_state.username}**")
        if st.button("Log out"):
            log_out()
            st.rerun()
    else:
        tab_login, tab_signup = st.tabs(["Log in", "Sign up"])
        with tab_login:
            with st.form("login_form"):
                username = st.text_input("Username", key="login_username")
                password = st.text_input("Password", type="password", key="login_password")
                if st.form_submit_button("Log in"):
                    user_id = db.authenticate(username, password)
                    if user_id:
                        log_in(user_id, username)
                        st.rerun()
                    else:
                        st.error("Wrong username or password.")
        with tab_signup:
            with st.form("signup_form"):
                new_username = st.text_input("Username", key="signup_username")
                new_password = st.text_input("Password", type="password", key="signup_password")
                if st.form_submit_button("Create account"):
                    if not new_username or not new_password:
                        st.error("Username and password are required.")
                    else:
                        user_id = db.create_user(new_username, new_password)
                        if user_id:
                            log_in(user_id, new_username)
                            st.rerun()
                        else:
                            st.error("That username is already taken.")

# --- Main ---
watchlist_count = len(db.watchlist_movie_ids(st.session_state.user_id)) if st.session_state.user_id else 0
tab_browse, tab_watchlist = st.tabs(["Browse movies", f"⭐ My watchlist ({watchlist_count})"])

with tab_browse:
    st.subheader("Search movies")
    col_q, col_yc, col_y, col_s = st.columns([3, 1, 1, 2])
    query = col_q.text_input("Title contains", key="search_query")
    filter_by_year = col_yc.checkbox("Filter by year", key="search_filter_by_year")
    year = col_y.number_input(
        "Year",
        min_value=0,
        max_value=2100,
        value=datetime.date.today().year,
        step=1,
        key="search_year",
        disabled=not filter_by_year,
    )
    sort_by = col_s.selectbox(
        "Sort by", list(db.SORT_OPTIONS.keys()), index=1, key="search_sort_by"
    )

    if st.session_state.get("_prev_search") != (query, filter_by_year, year, sort_by):
        set_page(1)
    st.session_state["_prev_search"] = (query, filter_by_year, year, sort_by)

    page = get_page()
    movies = db.search_movies(
        query,
        year if filter_by_year else None,
        limit=PAGE_SIZE,
        offset=(page - 1) * PAGE_SIZE,
        sort_by=sort_by,
    )
    in_watchlist_ids = db.watchlist_movie_ids(st.session_state.user_id) if st.session_state.user_id else set()

    if not movies:
        st.info("No movies found.")
    else:
        render_header()
    for movie in movies:
        render_movie_row(movie, in_watchlist_ids)
        st.divider()

    st.caption(f"Page {page}")
    col_prev, col_next = st.columns(2)
    if col_prev.button("← Previous", disabled=page <= 1):
        set_page(page - 1)
        st.rerun()
    if col_next.button("Next →", disabled=len(movies) < PAGE_SIZE):
        set_page(page + 1)
        st.rerun()

with tab_watchlist:
    if not st.session_state.user_id:
        st.info("Log in to see your watchlist.")
    else:
        watchlist = db.get_watchlist(st.session_state.user_id)
        if not watchlist:
            st.info("Your watchlist is empty. Add movies from the Browse tab.")
        else:
            render_header()
        in_watchlist_ids = {m["id"] for m in watchlist}
        for movie in watchlist:
            render_movie_row(movie, in_watchlist_ids)
            st.divider()
