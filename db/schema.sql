-- eMovie schema
-- users, movies (catalog), per-user movie status, explicit watchlist,
-- recommendations between users, and movie-party sessions.

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS movies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    imdb_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    director TEXT,
    year INT,
    emotions JSONB,              -- 28-label GoEmotions probability vector; NULL until scored
    imdb_rating NUMERIC,         -- IMDb average rating (title.ratings.tsv.gz)
    imdb_votes BIGINT,           -- IMDb number of votes
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_movies_title ON movies (title);
CREATE INDEX IF NOT EXISTS idx_movies_year ON movies (year);
CREATE INDEX IF NOT EXISTS idx_movies_votes ON movies (imdb_votes);

-- One row per (user, movie): watch/like/rewatch state, and private notes.
CREATE TABLE IF NOT EXISTS user_movie_status (
    user_id UUID NOT NULL REFERENCES users (id),
    movie_id UUID NOT NULL REFERENCES movies (id),
    watched BOOLEAN NOT NULL DEFAULT false,
    watched_at TIMESTAMPTZ,
    liked BOOLEAN,                     -- NULL = no opinion yet
    want_to_rewatch BOOLEAN,           -- app layer defaults this to false when liked=false
    agrees_with_emotion BOOLEAN,       -- optional agreement with the model's emotion tag
    personal_emotion TEXT,             -- private override/tag
    personal_comment TEXT,             -- private note
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, movie_id)
);

-- Explicit, user-curated watchlist (distinct from watched/liked history).
CREATE TABLE IF NOT EXISTS watchlist (
    user_id UUID NOT NULL REFERENCES users (id),
    movie_id UUID NOT NULL REFERENCES movies (id),
    added_by UUID REFERENCES users (id),   -- self, or whoever recommended it
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, movie_id)
);

-- One user recommending a movie to another; shows up in the recipient's own list.
CREATE TABLE IF NOT EXISTS recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_user_id UUID NOT NULL REFERENCES users (id),
    to_user_id UUID NOT NULL REFERENCES users (id),
    movie_id UUID NOT NULL REFERENCES movies (id),
    note TEXT,
    seen BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A "movie party": multiple people set today's mood, system picks a movie.
CREATE TABLE IF NOT EXISTS movie_party (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_by UUID NOT NULL REFERENCES users (id),
    chosen_movie_id UUID REFERENCES movies (id),  -- filled in once matched
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS movie_party_participants (
    party_id UUID NOT NULL REFERENCES movie_party (id),
    user_id UUID NOT NULL REFERENCES users (id),
    mood TEXT,                     -- today's target emotion
    wants_rewatch BOOLEAN,
    PRIMARY KEY (party_id, user_id)
);
