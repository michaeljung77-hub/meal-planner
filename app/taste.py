"""Turns ratings, picks and skips into flavor-trait scores (patterns, not dishes)."""

import json
from collections import defaultdict
from datetime import datetime, timezone

from . import db

VERDICT_WEIGHT = {"loved": 2.0, "good": 1.0, "meh": -0.5, "miss": -2.0}
STAR_WEIGHT = {5: 2.0, 4: 1.0, 3: 0.0, 2: -0.5, 1: -2.0}
DECAY_PER_WEEK = 0.93


def trait_keys(t: dict) -> list[str]:
    if not t:
        return []
    keys = []
    for field in ("cuisine", "protein", "method", "spice", "effort"):
        v = t.get(field)
        if isinstance(v, str) and v.strip():
            keys.append(f"{field}: {v.strip().lower()}")
    for f in t.get("flavors") or []:
        if isinstance(f, str) and f.strip():
            keys.append(f"flavor: {f.strip().lower()}")
    return keys


def _weeks_ago(iso: str | None) -> float:
    if not iso:
        return 0
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return 0
    return max(0.0, (datetime.now(timezone.utc) - then).days / 7)


def scores() -> list[tuple[str, float]]:
    s = defaultdict(float)

    # Rated meals from past weeks
    for m in db.rows("SELECT traits, rating, rated_at FROM meals WHERE rating IN ('loved','good','meh','miss')"):
        w = VERDICT_WEIGHT[m["rating"]] * DECAY_PER_WEEK ** _weeks_ago(m["rated_at"])
        for k in trait_keys(json.loads(m["traits"] or "{}")):
            s[k] += w

    # Starting data: star ratings in Mealie (fingerprinted)
    for t in db.rows("SELECT data FROM traits"):
        d = json.loads(t["data"])
        stars = d.get("_stars")
        if stars:
            w = STAR_WEIGHT.get(int(round(stars)), 0) * 0.8
            for k in trait_keys(d):
                s[k] += w

    # Picks and skips during planning: skipping the same flavors again and again counts
    for i in db.rows("SELECT i.data, i.status, w.created_at FROM ideas i JOIN weeks w ON w.id=i.week_id "
                     "WHERE w.status='confirmed' AND i.status IN ('picked','skipped')"):
        d = json.loads(i["data"])
        w = (0.3 if i["status"] == "picked" else -0.12) * DECAY_PER_WEEK ** _weeks_ago(i["created_at"])
        traits = dict(d.get("traits") or {})
        traits.setdefault("cuisine", d.get("cuisine"))
        for k in trait_keys(traits):
            s[k] += w

    return sorted(s.items(), key=lambda kv: kv[1], reverse=True)


def summary() -> dict:
    sc = scores()
    likes = [(k, round(v, 1)) for k, v in sc if v > 0.4][:12]
    dislikes = [(k, round(v, 1)) for k, v in reversed(sc) if v < -0.4][:8]
    return {"likes": likes, "dislikes": dislikes}
