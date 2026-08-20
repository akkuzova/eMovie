# Reddit API usage constraints

Notes from Reddit's Developer Terms (https://redditinc.com/policies/developer-terms),
read 2026-08-19, relevant to `fetch_reddit_comments.py`.

## Do not train on Reddit data

> "access or use the Reddit Services and Data through any means (including by
> accessing our API or indexing, caching, or crawling our Reddit Services and
> Data) to train large language, artificial intelligence, or other
> algorithmic models or related services without our permission"

The emotion classifier is trained on GoEmotions (independent published
dataset, not Reddit-sourced) and only runs **inference** on scraped Reddit
comments. That's fine. Do **not** fine-tune/retrain the model on the scraped
subreddit comments themselves — that would cross into "training on Reddit
data."

## Non-commercial only

> "you will not... access or use any of the Reddit Services and Data by or on
> behalf of a business or as part of a service or product that is monetized...
> sell, lease, sublicense, monetize, or otherwise obtain or derive revenues...
> from any data derived from [Reddit data]"

eMovie must stay personal/non-monetized under the current API terms (no ads,
no paid tier) unless a separate commercial agreement is made with Reddit.

## Storage / retention

> if content "is deleted, gains protected status, or is suspended, withheld,
> modified, or removed... you will delete or modify that... content as soon
> as possible"

> "use commercially reasonable efforts to protect Reddit Services and Data...
> including encryption of the data at rest"

The scraped `data/reddit_comments/*.txt` files aren't a permanent archive —
if re-running the scraper, prefer refreshing over indefinitely keeping stale
copies. At-rest encryption isn't implemented (low risk for a local personal
project, but technically expected by the terms).

## Rate limits

No fixed number stated in the terms page itself (set at Reddit's discretion /
developer docs, historically ~100 requests/min for OAuth apps).
`fetch_reddit_comments.py` sleeps 2s between movies, well under any plausible
limit.
