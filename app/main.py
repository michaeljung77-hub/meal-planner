"""Family Meal Planner: web app for the Saturday planning session."""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import claude_ai, config, db, kindle, mailer, mealie, skylight, taste

log = logging.getLogger("planner")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Family Meal Planner")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.on_event("startup")
def _startup():
    db.init()
    log.info("Planner started. Missing settings: %s", config.missing() or "none")


@app.exception_handler(Exception)
async def _errors(request: Request, exc: Exception):
    known = (claude_ai.AIError, mealie.MealieError, skylight.SkylightError, ValueError)
    if isinstance(exc, known):
        return JSONResponse({"error": str(exc)}, status_code=400)
    log.exception("Unexpected error")
    return JSONResponse({"error": f"Something went wrong: {type(exc).__name__}: {exc}"}, status_code=500)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/apple-touch-icon.png")
def touch_icon():
    return FileResponse(STATIC / "apple-touch-icon.png")


@app.get("/kindle.png")
def kindle_png(day: str = "auto"):
    """Bedroom e-ink dashboard. day=auto|today|tomorrow."""
    return Response(kindle.render(day), media_type="image/png", headers={"Cache-Control": "no-store"})


# ------------------------------------------------------------------ helpers

def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def _link(slug):
    if not slug:
        return ""
    group = db.get_setting("mealie_group_slug") or "home"
    return f"{config.MEALIE_PUBLIC_URL}/g/{group}/r/{slug}"


def _remember_group():
    if db.get_setting("mealie_group_slug"):
        return
    try:
        me = mealie.me()
        slug = me.get("groupSlug") or me.get("group_slug")
        if slug:
            db.set_setting("mealie_group_slug", slug)
    except mealie.MealieError:
        pass


def _week():
    return db.row("SELECT * FROM weeks WHERE status='planning' ORDER BY id DESC LIMIT 1")


def _require_week():
    w = _week()
    if not w:
        raise ValueError("No planning session is open. Tap 'Start planning' first.")
    return w


def _idea_out(i: dict) -> dict:
    d = json.loads(i["data"])
    return {"id": i["id"], "batch": i["batch"], "status": i["status"], "source": i["source"],
            "tweaks": i["tweaks"] or "", "prep_status": i["prep_status"] or "", "prep_note": i["prep_note"] or "",
            "mealie_slug": i["mealie_slug"], "link": _link(i["mealie_slug"]), "source_url": i["source_url"],
            **d}


def _to_rate() -> list[dict]:
    recent = db.rows("SELECT id FROM weeks WHERE status='confirmed' ORDER BY id DESC LIMIT 2")
    if not recent:
        return []
    ids = ",".join(str(r["id"]) for r in recent)
    meals = db.rows(f"SELECT * FROM meals WHERE week_id IN ({ids}) ORDER BY week_id DESC, id")
    return [{"id": m["id"], "name": m["name"], "rating": m["rating"], "note": m["note"] or "",
             "link": _link(m["mealie_slug"])} for m in meals]


@app.get("/api/state")
def state():
    w = _week()
    out = {"missing": config.missing(), "week": None, "ideas": [], "grocery": None, "results": None,
           "to_rate": _to_rate(), "mealie_url": config.MEALIE_PUBLIC_URL}
    last = db.row("SELECT * FROM weeks WHERE status='confirmed' ORDER BY id DESC LIMIT 1")
    if last:
        n = db.row("SELECT COUNT(*) AS n FROM meals WHERE week_id=?", (last["id"],))["n"]
        out["last_week"] = {"confirmed_at": last["confirmed_at"], "meals": n,
                            "results": json.loads(last["results_json"] or "null")}
    if w:
        out["week"] = {"id": w["id"], "step": w["step"], "direction": w["direction"] or ""}
        out["ideas"] = [_idea_out(i) for i in db.rows("SELECT * FROM ideas WHERE week_id=? ORDER BY id", (w["id"],))]
        out["grocery"] = json.loads(w["grocery_json"]) if w["grocery_json"] else None
    return out


# ---------------------------------------------------------- planning session

@app.post("/api/plan/start")
def plan_start():
    if not _week():
        step = "rate" if any(m["rating"] is None for m in _to_rate()) else "pantry"
        db.execute("INSERT INTO weeks(created_at, step) VALUES(?,?)", (db.now(), step))
    return state()


@app.post("/api/plan/step")
async def plan_step(request: Request):
    body = await request.json()
    w = _require_week()
    if body.get("step") not in ("rate", "pantry", "ideas", "prepare", "review", "done"):
        raise ValueError("Unknown step")
    db.execute("UPDATE weeks SET step=? WHERE id=?", (body["step"], w["id"]))
    return {"ok": True}


@app.post("/api/plan/cancel")
def plan_cancel():
    w = _week()
    if w:
        db.execute("DELETE FROM ideas WHERE week_id=?", (w["id"],))
        db.execute("DELETE FROM weeks WHERE id=?", (w["id"],))
    return state()


def _sync_library() -> list[dict]:
    """Recipes in Mealie with star ratings; fingerprints new ones for the taste profile."""
    _remember_group()
    recipes = mealie.all_recipes()
    mine = mealie.my_ratings()
    lib = []
    for r in recipes:
        stars = mine.get(r.get("id")) or r.get("rating")
        lib.append({"slug": r["slug"], "name": r.get("name") or r["slug"], "stars": stars,
                    "description": (r.get("description") or "")[:140]})
    known = {t["slug"]: json.loads(t["data"]) for t in db.rows("SELECT slug, data FROM traits")}
    todo = [r for r in lib if r["stars"] and r["slug"] not in known]
    for r in lib:  # keep star ratings current
        if r["slug"] in known and known[r["slug"]].get("_stars") != r["stars"]:
            known[r["slug"]]["_stars"] = r["stars"]
            db.execute("UPDATE traits SET data=? WHERE slug=?", (json.dumps(known[r["slug"]]), r["slug"]))
    for start in range(0, len(todo), 15):
        chunk = todo[start:start + 15]
        payload = []
        for r in chunk:
            try:
                ings = mealie.ingredient_lines(mealie.recipe(r["slug"]))[:15]
            except mealie.MealieError:
                ings = []
            payload.append({"slug": r["slug"], "name": r["name"], "ingredients": ings})
        tags = claude_ai.fingerprint(payload)
        for r in chunk:
            t = tags.get(r["slug"])
            if isinstance(t, dict):
                t["_stars"] = r["stars"]
                db.execute("INSERT OR REPLACE INTO traits(slug, name, data) VALUES(?,?,?)",
                           (r["slug"], r["name"], json.dumps(t)))
    return lib


def _verdicts() -> list[dict]:
    out = [{"dish": m["name"], "verdict": m["rating"], "note": m["note"] or ""}
           for m in db.rows("SELECT name, rating, note FROM meals WHERE rating IS NOT NULL "
                            "AND rating!='not_cooked' ORDER BY rated_at")]
    return out


def _trait_text() -> str:
    s = taste.summary()
    likes = ", ".join(f"{k} (+{v})" for k, v in s["likes"])
    dislikes = ", ".join(f"{k} ({v})" for k, v in s["dislikes"])
    return f"Liked: {likes or 'n/a'}\nDisliked: {dislikes or 'n/a'}"


def _maybe_refresh_profile(force: bool = False):
    last_rating = db.row("SELECT MAX(rated_at) AS t FROM meals WHERE rated_at IS NOT NULL")["t"]
    last_refresh = db.get_setting("profile_refreshed_at", "")
    profile = db.get_setting("taste_profile", "")
    has_data = bool(last_rating) or db.row("SELECT COUNT(*) AS n FROM traits")["n"] > 0
    if not has_data:
        return
    if force or not profile or (last_rating and last_rating > last_refresh):
        lib_verdicts = [{"dish": t["name"], "stars": json.loads(t["data"]).get("_stars")}
                        for t in db.rows("SELECT name, data FROM traits")]
        new = claude_ai.refresh_profile(profile, db.get_setting("family_notes", ""), _trait_text(),
                                        lib_verdicts + _verdicts())
        db.set_setting("taste_profile", new)
        db.set_setting("profile_refreshed_at", db.now())


def _context(lib: list[dict]) -> dict:
    r = db.rules()
    rest_cut = (datetime.now(timezone.utc) - timedelta(weeks=int(r["favorite_rest_weeks"]))).isoformat()
    recent_meals = db.rows("SELECT name, mealie_slug FROM meals WHERE created_at > ? "
                           "AND (rating IS NULL OR rating!='not_cooked')", (rest_cut,))
    resting = {_norm(m["name"]) for m in recent_meals} | {m["mealie_slug"] for m in recent_meals if m["mealie_slug"]}
    retired = [m["name"] for m in db.rows("SELECT DISTINCT name FROM meals WHERE rating='miss'")]
    retired += [x["name"] for x in lib if x["stars"] and x["stars"] <= 1.5]
    loved_meals = {m["mealie_slug"] for m in db.rows("SELECT mealie_slug FROM meals WHERE rating IN ('loved','good')")}
    favs = [x for x in lib if (x["stars"] and x["stars"] >= 4) or x["slug"] in loved_meals]
    favs_ok = [x for x in favs if x["slug"] not in resting and _norm(x["name"]) not in resting]
    return {
        "rules": r,
        "profile": db.get_setting("taste_profile", ""),
        "notes": db.get_setting("family_notes", ""),
        "trait_text": _trait_text(),
        "favorites_text": "\n".join(f"- {x['name']} (slug: {x['slug']}, {x['stars'] or '?'} stars)" for x in favs_ok[:40]),
        "resting_text": ", ".join(m["name"] for m in recent_meals),
        "retired_text": ", ".join(sorted(set(retired))),
        "library_slugs": {x["slug"] for x in lib},
    }


def _recent_names(week_id: int) -> list[str]:
    cut = (datetime.now(timezone.utc) - timedelta(weeks=3)).isoformat()
    names = [json.loads(i["data"]).get("name", "") for i in
             db.rows("SELECT data FROM ideas WHERE week_id=? OR created_at > ?", (week_id, cut))]
    return list(dict.fromkeys(n for n in names if n))


def _insert_ideas(week_id: int, batch: int, ideas: list[dict], slugs: set, status="new") -> None:
    for idea in ideas:
        if idea.get("library_slug") not in slugs:
            idea["library_slug"] = None
        source = "library" if idea.get("library_slug") else "web"
        db.execute("INSERT INTO ideas(week_id, batch, data, status, source, created_at) VALUES(?,?,?,?,?,?)",
                   (week_id, batch, json.dumps(idea), status, source, db.now()))


@app.post("/api/plan/ideas")
async def plan_ideas(request: Request):
    body = await request.json()
    direction = (body.get("direction") or "").strip()
    w = _require_week()
    lib = _sync_library()
    _maybe_refresh_profile()
    ctx = _context(lib)
    count = int(ctx["rules"]["ideas_count"])
    ideas = claude_ai.generate_ideas(ctx, count, direction, avoid=_recent_names(w["id"]))
    db.execute("UPDATE ideas SET status='skipped' WHERE week_id=? AND status='new'", (w["id"],))
    batch = (db.row("SELECT MAX(batch) AS b FROM ideas WHERE week_id=?", (w["id"],))["b"] or 0) + 1
    _insert_ideas(w["id"], batch, ideas, ctx["library_slugs"])
    db.execute("UPDATE weeks SET step='ideas', direction=? WHERE id=?", (direction, w["id"]))
    return state()


@app.post("/api/ideas/{idea_id}/more")
def idea_more(idea_id: int):
    w = _require_week()
    base = db.row("SELECT * FROM ideas WHERE id=?", (idea_id,))
    if not base:
        raise ValueError("Idea not found")
    lib = _sync_library()
    ctx = _context(lib)
    ideas = claude_ai.generate_ideas(ctx, 3, avoid=_recent_names(w["id"]), like=json.loads(base["data"]))
    _insert_ideas(w["id"], base["batch"], ideas, ctx["library_slugs"])
    return state()


@app.post("/api/ideas/custom")
async def idea_custom(request: Request):
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        raise ValueError("Type an idea or paste a recipe link first.")
    w = _require_week()
    ctx = _context([])
    if re.match(r"^https?://", text):
        idea = claude_ai.custom_idea(ctx, text)
        idea["_url"] = text
        source = "web"
    else:
        idea = claude_ai.custom_idea(ctx, text)
        source = "web"
    idea["kind"] = "ours"
    db.execute("INSERT INTO ideas(week_id, batch, data, status, source, created_at) VALUES(?,?,?,?,?,?)",
               (w["id"], 0, json.dumps(idea), "picked", source, db.now()))
    return state()


@app.post("/api/ideas/{idea_id}/pick")
async def idea_pick(idea_id: int, request: Request):
    body = await request.json()
    status = "picked" if body.get("picked") else "new"
    db.execute("UPDATE ideas SET status=? WHERE id=?", (status, idea_id))
    return {"ok": True}


@app.post("/api/ideas/{idea_id}/options")
async def idea_options(idea_id: int, request: Request):
    body = await request.json()
    source = body.get("source")
    if source not in ("web", "ai", "library"):
        raise ValueError("Unknown recipe source")
    db.execute("UPDATE ideas SET source=?, tweaks=?, prep_status='', prep_note='' WHERE id=?",
               (source, (body.get("tweaks") or "").strip(), idea_id))
    return {"ok": True}


def _adapt_existing(slug: str, tweaks: str, servings: int) -> str:
    rec = mealie.recipe(slug)
    rec["_ingredients"] = mealie.ingredient_lines(rec)
    rec["_steps"] = mealie.instruction_lines(rec)
    adapted = claude_ai.adapt_recipe(rec, tweaks, servings)
    return mealie.import_jsonld(adapted, rec.get("orgURL"))


@app.post("/api/ideas/{idea_id}/prepare")
def idea_prepare(idea_id: int):
    i = db.row("SELECT * FROM ideas WHERE id=?", (idea_id,))
    if not i:
        raise ValueError("Idea not found")
    idea = json.loads(i["data"])
    r = db.rules()
    servings = int(r["servings"])
    tweaks = i["tweaks"] or ""
    source, slug, url, note = i["source"], None, None, ""
    try:
        if source == "library" and idea.get("library_slug"):
            slug = idea["library_slug"]
            note = "From your recipe library"
            if tweaks:
                slug = _adapt_existing(slug, tweaks, servings)
                source, note = "ai", "Adapted from your library version"
        elif source == "web":
            tried = []
            candidates = [idea["_url"]] if idea.get("_url") else []
            for _ in range(2):
                if not candidates:
                    found = claude_ai.find_recipe_url(idea, tweaks, tried)
                    if not found:
                        break
                    candidates.append(found)
                url = candidates.pop(0)
                tried.append(url)
                try:
                    slug = mealie.import_url(url)
                    break
                except mealie.MealieError as e:
                    log.info("Import failed for %s: %s", url, e)
                    slug, url = None, None
            if slug and tweaks:
                original = slug
                slug = _adapt_existing(original, tweaks, servings)
                note = "Found online, adjusted to your changes"
                try:
                    mealie._req("DELETE", f"/api/recipes/{original}")
                except mealie.MealieError:
                    pass
            elif slug:
                note = "Real recipe found online"
            else:
                source, note = "ai", "No importable recipe page found, so Claude wrote one"
        if source == "ai" and not slug:
            rec = claude_ai.write_recipe(idea, tweaks, servings, r["kid_mild_option"])
            slug = mealie.import_jsonld(rec)
            note = note or "Written by Claude"
        if not slug:
            raise ValueError("The recipe could not be prepared.")
        final = mealie.recipe(slug)
        idea["final_name"] = final.get("name") or idea.get("name")
        db.execute("UPDATE ideas SET data=?, mealie_slug=?, source_url=?, prep_status='done', prep_note=?, source=? "
                   "WHERE id=?", (json.dumps(idea), slug, url or final.get("orgURL"), note, source, idea_id))
    except Exception as e:
        msg = str(e) if isinstance(e, (claude_ai.AIError, mealie.MealieError, ValueError)) else f"{type(e).__name__}: {e}"
        db.execute("UPDATE ideas SET prep_status='error', prep_note=? WHERE id=?", (msg[:300], idea_id))
        log.exception("Prepare failed")
    return _idea_out(db.row("SELECT * FROM ideas WHERE id=?", (idea_id,)))


@app.post("/api/plan/grocery")
def plan_grocery():
    w = _require_week()
    picked = db.rows("SELECT * FROM ideas WHERE week_id=? AND status='picked' AND prep_status='done'", (w["id"],))
    if not picked:
        raise ValueError("Prepare at least one recipe first.")
    meals = []
    for i in picked:
        rec = mealie.recipe(i["mealie_slug"])
        meals.append({"meal": rec.get("name"), "ingredients": mealie.ingredient_lines(rec)})
    pantry = db.rows("SELECT name, low FROM pantry")
    g = claude_ai.grocery_list(meals, [p["name"] for p in pantry if not p["low"]],
                               [p["name"] for p in pantry if p["low"]], db.rules()["stores"])
    for aisle in g.get("aisles", []):
        for item in aisle.get("items", []):
            item["removed"] = False
    db.execute("UPDATE weeks SET grocery_json=?, step='review' WHERE id=?", (json.dumps(g), w["id"]))
    return state()


@app.post("/api/plan/grocery/save")
async def grocery_save(request: Request):
    body = await request.json()
    w = _require_week()
    db.execute("UPDATE weeks SET grocery_json=? WHERE id=?", (json.dumps({"aisles": body.get("aisles", [])}), w["id"]))
    return {"ok": True}


def _skylight_body(i: dict, rec: dict) -> str:
    if i["source_url"] and not i["tweaks"]:
        return f"{i['source_url']}\n"
    return mailer.recipe_text(rec)


@app.post("/api/plan/confirm")
async def plan_confirm(request: Request):
    body = await request.json()
    w = _require_week()
    aisles = body.get("aisles") or (json.loads(w["grocery_json"]) if w["grocery_json"] else {}).get("aisles", [])
    picked = db.rows("SELECT * FROM ideas WHERE week_id=? AND status='picked' AND prep_status='done'", (w["id"],))
    results = {"recipes": [], "grocery": None}

    for i in picked:
        idea = json.loads(i["data"])
        traits = dict(idea.get("traits") or {})
        traits["cuisine"] = idea.get("cuisine")
        rec = mealie.recipe(i["mealie_slug"])
        name = rec.get("name") or idea.get("name")
        db.execute("INSERT INTO meals(week_id, idea_id, name, mealie_slug, source, source_url, traits, created_at) "
                   "VALUES(?,?,?,?,?,?,?,?)",
                   (w["id"], i["id"], name, i["mealie_slug"], i["source"], i["source_url"], json.dumps(traits), db.now()))
        key = _norm(name)
        if db.row("SELECT 1 AS x FROM sent WHERE name_key=?", (key,)):
            results["recipes"].append({"name": name, "status": "already", "detail": "Already in the Skylight Recipe Box"})
            continue
        try:
            mailer.send(name, _skylight_body(i, rec))
            db.execute("INSERT OR REPLACE INTO sent(name_key, slug, sent_at) VALUES(?,?,?)", (key, i["mealie_slug"], db.now()))
            results["recipes"].append({"name": name, "status": "sent", "detail": "Sent to the Skylight"})
        except Exception as e:
            results["recipes"].append({"name": name, "status": "error", "detail": f"Email failed: {e}"})

    labels = []
    for aisle in aisles:
        for it in aisle.get("items", []):
            if it.get("removed") or not it.get("item"):
                continue
            label = it["item"].strip()
            if it.get("qty"):
                label += f" ({it['qty']})"
            if it.get("other_store"):
                label += " - Publix/Ingles"
            labels.append(label)
    try:
        if labels:
            res = skylight.push_items(labels)
            results["grocery"] = {"status": "sent", "detail": f"{res['added']} items added to '{res['list']}'"
                                  + (f", {res['already_there']} were already on it" if res["already_there"] else "")}
        else:
            results["grocery"] = {"status": "already", "detail": "Grocery list was empty"}
    except Exception as e:
        results["grocery"] = {"status": "error", "detail": str(e)}
    results["grocery_text"] = "\n".join(labels)

    db.execute("UPDATE pantry SET low=0")
    db.execute("UPDATE weeks SET status='confirmed', step='done', confirmed_at=?, results_json=?, grocery_json=? "
               "WHERE id=?", (db.now(), json.dumps(results), json.dumps({"aisles": aisles}), w["id"]))
    return {"results": results}


# ------------------------------------------------------------------ ratings

@app.post("/api/meals/{meal_id}/rate")
async def rate(meal_id: int, request: Request):
    body = await request.json()
    rating = body.get("rating")
    if rating not in ("loved", "good", "meh", "miss", "not_cooked", None):
        raise ValueError("Unknown rating")
    db.execute("UPDATE meals SET rating=?, note=?, rated_at=? WHERE id=?",
               (rating, (body.get("note") or "").strip(), db.now() if rating else None, meal_id))
    m = db.row("SELECT mealie_slug FROM meals WHERE id=?", (meal_id,))
    if rating in mealie.STARS and m and m["mealie_slug"]:
        try:
            mealie.set_rating(m["mealie_slug"], rating)
        except Exception as e:  # stars in Mealie are a bonus, never block
            log.info("Could not sync rating to Mealie: %s", e)
    return {"ok": True}


# ------------------------------------------------------------------- pantry

@app.get("/api/pantry")
def pantry():
    return db.rows("SELECT * FROM pantry ORDER BY category, name")


@app.post("/api/pantry")
async def pantry_add(request: Request):
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise ValueError("Type an item name.")
    db.execute("INSERT OR IGNORE INTO pantry(name, category) VALUES(?,?)", (name, body.get("category") or "Other"))
    return pantry()


@app.post("/api/pantry/{item_id}/low")
async def pantry_low(item_id: int, request: Request):
    body = await request.json()
    db.execute("UPDATE pantry SET low=? WHERE id=?", (1 if body.get("low") else 0, item_id))
    return {"ok": True}


@app.delete("/api/pantry/{item_id}")
def pantry_delete(item_id: int):
    db.execute("DELETE FROM pantry WHERE id=?", (item_id,))
    return pantry()


# ------------------------------------------------------ profile & settings

@app.get("/api/profile")
def profile():
    s = taste.summary()
    return {"profile": db.get_setting("taste_profile", ""), "notes": db.get_setting("family_notes", ""),
            "likes": s["likes"], "dislikes": s["dislikes"],
            "refreshed_at": db.get_setting("profile_refreshed_at", "")}


@app.post("/api/profile")
async def profile_save(request: Request):
    body = await request.json()
    if "profile" in body:
        db.set_setting("taste_profile", body["profile"].strip())
    if "notes" in body:
        db.set_setting("family_notes", body["notes"].strip())
    return profile()


@app.post("/api/profile/refresh")
def profile_refresh():
    _sync_library()
    _maybe_refresh_profile(force=True)
    return profile()


@app.get("/api/rules")
def get_rules():
    return db.rules()


@app.post("/api/rules")
async def save_rules(request: Request):
    body = await request.json()
    merged = db.rules()
    for k, v in body.items():
        if k in db.DEFAULT_RULES:
            default = db.DEFAULT_RULES[k]
            if isinstance(default, bool):
                v = bool(v)
            elif isinstance(default, int):
                v = int(v)
            merged[k] = v
    db.set_setting("rules", json.dumps(merged))
    return merged


@app.post("/api/rules/reset")
def reset_rules():
    db.set_setting("rules", json.dumps(db.DEFAULT_RULES))
    return db.rules()


@app.post("/api/test")
def test_connections():
    checks = []

    def run(name, fn):
        try:
            detail = fn()
            checks.append({"name": name, "ok": True, "detail": detail or "Connected"})
        except Exception as e:
            checks.append({"name": name, "ok": False, "detail": str(e)[:300]})

    def t_mealie():
        me = mealie.me()
        _remember_group()
        return f"Logged in as {me.get('fullName') or me.get('email')}, {len(mealie.all_recipes())} recipes"

    def t_claude():
        claude_ai.ping()
        return f"Model {config.CLAUDE_MODEL} answered"

    def t_mail():
        if not config.GMAIL_USER or not config.GMAIL_APP_PASSWORD:
            raise ValueError("Gmail address or app password missing")
        mailer.test_login()
        return f"Gmail login OK, recipes go to {config.SKYLIGHT_RECIPE_EMAIL or '(Skylight email missing)'}"

    def t_sky():
        info = skylight.test()
        return f"Found '{info['frame_name'] or 'your Skylight'}' (frame {info['frame_id']}), list '{info['list']}'"

    run("Mealie", t_mealie)
    run("Claude API", t_claude)
    run("Gmail to Skylight", t_mail)
    run("Skylight grocery list", t_sky)
    return {"checks": checks}


@app.get("/api/history")
def history():
    weeks = db.rows("SELECT * FROM weeks WHERE status='confirmed' ORDER BY id DESC LIMIT 12")
    for w in weeks:
        w["meals"] = [{"name": m["name"], "rating": m["rating"], "note": m["note"], "link": _link(m["mealie_slug"])}
                      for m in db.rows("SELECT * FROM meals WHERE week_id=? ORDER BY id", (w["id"],))]
        for k in ("grocery_json", "results_json"):
            w.pop(k, None)
    return weeks
