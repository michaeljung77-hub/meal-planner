"""SQLite storage for the planner: weeks, ideas, meals, ratings, pantry, settings."""

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS weeks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planning',      -- planning | confirmed
    step TEXT NOT NULL DEFAULT 'rate',
    direction TEXT DEFAULT '',
    grocery_json TEXT,
    results_json TEXT,
    confirmed_at TEXT
);
CREATE TABLE IF NOT EXISTS ideas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_id INTEGER NOT NULL,
    batch INTEGER NOT NULL DEFAULT 1,
    data TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',            -- new | picked | skipped
    source TEXT,                                   -- web | ai | library
    tweaks TEXT DEFAULT '',
    mealie_slug TEXT,
    source_url TEXT,
    prep_status TEXT DEFAULT '',                   -- '' | done | error
    prep_note TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_id INTEGER NOT NULL,
    idea_id INTEGER,
    name TEXT NOT NULL,
    mealie_slug TEXT,
    source TEXT,
    source_url TEXT,
    traits TEXT,
    rating TEXT,                                   -- loved | good | meh | miss | not_cooked
    note TEXT DEFAULT '',
    rated_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS traits (
    slug TEXT PRIMARY KEY,
    name TEXT,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pantry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT DEFAULT 'Other',
    low INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sent (
    name_key TEXT PRIMARY KEY,
    slug TEXT,
    sent_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

DEFAULT_RULES = {
    "ideas_count": 12,
    "weeknight_max_minutes": 45,
    "weeknight_stretch": "1-2 stretch dishes per week on weeknights",
    "favorites_share": "about one third favorites or close remixes, two thirds new",
    "wildcards": 1,
    "max_pasta": 1,
    "favorite_rest_weeks": 3,
    "kid_mild_option": True,
    "servings": 4,
    "cuisines": "American comfort food, Italian, Mexican, German, Asian (Chinese, Japanese, "
    "Korean, Thai, Vietnamese), Mediterranean, Indian, French",
    "stores": "Aldi or Lidl first; Publix or Ingles only for items Aldi/Lidl usually don't carry",
    "household": "Two adults and a 7-year-old son, Sebastian. Michael loves to cook and enjoys "
    "elevated dishes. Sebastian is picky, but the family wants to be adventurous; his pickiness "
    "shapes the plan but never vetoes it. No allergies, no excluded foods. The family plans the "
    "whole week, weekends included, and sometimes skips nights.",
}

DEFAULT_PANTRY = {
    "Oils & Vinegars": ["Olive oil", "Vegetable oil", "Sesame oil", "White wine vinegar",
                        "Red wine vinegar", "Rice vinegar", "Balsamic vinegar", "Cooking spray"],
    "Spices": ["Salt", "Black pepper", "Garlic powder", "Onion powder", "Paprika",
               "Smoked paprika", "Ground cumin", "Chili powder", "Dried oregano",
               "Italian seasoning", "Red pepper flakes", "Cinnamon", "Bay leaves",
               "Dried thyme", "Curry powder", "Caraway seeds"],
    "Baking": ["All-purpose flour", "Sugar", "Brown sugar", "Honey", "Cornstarch",
               "Baking powder", "Baking soda", "Vanilla extract", "Panko breadcrumbs"],
    "Sauces & Condiments": ["Soy sauce", "Worcestershire sauce", "Dijon mustard",
                            "Ketchup", "Mayonnaise", "Hot sauce", "Sriracha", "Maple syrup"],
    "Pantry": ["Chicken broth", "Canned diced tomatoes", "Tomato paste", "White rice",
               "Spaghetti", "Short pasta", "Canned black beans"],
    "Fridge": ["Butter", "Eggs", "Milk", "Parmesan", "Garlic", "Yellow onions"],
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _path() -> str:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    return os.path.join(config.DATA_DIR, "planner.db")


@contextmanager
def conn():
    with _lock:
        c = sqlite3.connect(_path())
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()


def init() -> None:
    with conn() as c:
        c.executescript(SCHEMA)
        if c.execute("SELECT COUNT(*) FROM pantry").fetchone()[0] == 0 and not _get(c, "pantry_seeded"):
            for cat, items in DEFAULT_PANTRY.items():
                for name in items:
                    c.execute("INSERT OR IGNORE INTO pantry(name, category) VALUES(?,?)", (name, cat))
            _set(c, "pantry_seeded", "1")
        if _get(c, "rules") is None:
            _set(c, "rules", json.dumps(DEFAULT_RULES))


def _get(c, key):
    row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def _set(c, key, value):
    c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
              (key, value))


def get_setting(key: str, default=None):
    with conn() as c:
        v = _get(c, key)
    return default if v is None else v


def set_setting(key: str, value: str) -> None:
    with conn() as c:
        _set(c, key, value)


def rules() -> dict:
    merged = dict(DEFAULT_RULES)
    try:
        merged.update(json.loads(get_setting("rules", "{}")))
    except ValueError:
        pass
    return merged


def rows(sql: str, params=()) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def row(sql: str, params=()):
    with conn() as c:
        r = c.execute(sql, params).fetchone()
        return dict(r) if r else None


def execute(sql: str, params=()) -> int:
    with conn() as c:
        cur = c.execute(sql, params)
        return cur.lastrowid
