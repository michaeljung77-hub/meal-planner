"""Thin client for the Mealie REST API (v2/v3)."""

import json

import requests

from . import config

TIMEOUT = 90


class MealieError(Exception):
    pass


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.MEALIE_TOKEN}", "Accept": "application/json"}


def _req(method: str, path: str, **kw):
    if not config.MEALIE_URL or not config.MEALIE_TOKEN:
        raise MealieError("Mealie URL or token is missing in the settings.")
    try:
        r = requests.request(method, f"{config.MEALIE_URL}{path}", headers=_headers(), timeout=TIMEOUT, **kw)
    except requests.RequestException as e:
        raise MealieError(f"Could not reach Mealie at {config.MEALIE_URL}: {e}") from e
    if r.status_code == 401:
        raise MealieError("Mealie rejected the API token (401). Create a new token in Mealie and update the settings.")
    if r.status_code >= 400:
        detail = r.text[:300]
        raise MealieError(f"Mealie returned {r.status_code}: {detail}")
    if not r.content:
        return None
    try:
        return r.json()
    except ValueError:
        return r.text


def me() -> dict:
    return _req("GET", "/api/users/self")


def all_recipes() -> list[dict]:
    """Every recipe summary (name, slug, rating, tags, description)."""
    out, page = [], 1
    while True:
        data = _req("GET", "/api/recipes", params={"page": page, "perPage": 100,
                                                   "orderBy": "name", "orderDirection": "asc"})
        items = data.get("items", []) if isinstance(data, dict) else []
        out.extend(items)
        if page >= (data.get("total_pages") or data.get("totalPages") or 1):
            break
        page += 1
    return out


def my_ratings() -> dict:
    """recipe_id -> star rating set by the token's user."""
    try:
        data = _req("GET", "/api/users/self/ratings")
    except MealieError:
        return {}
    result = {}
    for r in (data or {}).get("ratings", []):
        rid = r.get("recipeId") or r.get("recipe_id")
        if rid and r.get("rating"):
            result[rid] = r["rating"]
    return result


def recipe(slug: str) -> dict:
    return _req("GET", f"/api/recipes/{slug}")


def import_url(url: str) -> str:
    slug = _req("POST", "/api/recipes/create/url", json={"url": url, "includeTags": False})
    if not isinstance(slug, str) or not slug:
        raise MealieError("Mealie could not read a recipe from that page.")
    return slug.strip('"')


def import_jsonld(recipe_ld: dict, source_url: str | None = None) -> str:
    body = {"data": json.dumps(recipe_ld), "includeTags": False}
    if source_url:
        body["url"] = source_url
    slug = _req("POST", "/api/recipes/create/html-or-json", json=body)
    if not isinstance(slug, str) or not slug:
        raise MealieError("Mealie could not save the recipe.")
    return slug.strip('"')


STARS = {"loved": 5, "good": 4, "meh": 2, "miss": 1}


def set_rating(slug: str, verdict: str) -> None:
    stars = STARS.get(verdict)
    if not stars or not slug:
        return
    user = me()
    _req("POST", f"/api/users/{user['id']}/ratings/{slug}", json={"rating": stars})


def ingredient_lines(rec: dict) -> list[str]:
    lines = []
    for ing in rec.get("recipeIngredient") or []:
        if isinstance(ing, str):
            text = ing
        else:
            text = ing.get("display") or ing.get("originalText") or ing.get("note") or ""
        text = " ".join(str(text).split())
        if text:
            lines.append(text)
    return lines


def instruction_lines(rec: dict) -> list[str]:
    out = []
    for step in rec.get("recipeInstructions") or []:
        text = step.get("text") if isinstance(step, dict) else str(step)
        text = " ".join(str(text or "").split())
        if text:
            out.append(text)
    return out


def recipe_link(slug: str) -> str:
    return f"{config.MEALIE_PUBLIC_URL}/g/home/r/{slug}" if slug else ""
