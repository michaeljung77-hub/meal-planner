"""Settings read from environment variables (entered in CasaOS, never in code)."""

import os


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY")
CLAUDE_MODEL = _get("CLAUDE_MODEL", "claude-sonnet-5")
# Server-side web search tool version used to find real recipes online.
CLAUDE_WEB_SEARCH_TOOL = _get("CLAUDE_WEB_SEARCH_TOOL", "web_search_20250305")

# Mealie as seen from inside the Beelink (container-to-host) and from the iPhone.
MEALIE_URL = _get("MEALIE_URL").rstrip("/")
MEALIE_PUBLIC_URL = (_get("MEALIE_PUBLIC_URL") or MEALIE_URL).rstrip("/")
MEALIE_TOKEN = _get("MEALIE_TOKEN")

GMAIL_USER = _get("GMAIL_USER")
GMAIL_APP_PASSWORD = _get("GMAIL_APP_PASSWORD").replace(" ", "")
SKYLIGHT_RECIPE_EMAIL = _get("SKYLIGHT_RECIPE_EMAIL")

SKYLIGHT_LOGIN_EMAIL = _get("SKYLIGHT_LOGIN_EMAIL")
SKYLIGHT_PASSWORD = _get("SKYLIGHT_PASSWORD")
SKYLIGHT_LIST_NAME = _get("SKYLIGHT_LIST_NAME", "Grocery List")
SKYLIGHT_FRAME_ID = _get("SKYLIGHT_FRAME_ID")  # optional; found automatically

DATA_DIR = _get("DATA_DIR", "/data")
TZ = _get("TZ", "America/New_York")


def missing() -> list[str]:
    """Settings that must be filled in before the matching feature works."""
    required = {
        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
        "MEALIE_URL": MEALIE_URL,
        "MEALIE_TOKEN": MEALIE_TOKEN,
        "GMAIL_USER": GMAIL_USER,
        "GMAIL_APP_PASSWORD": GMAIL_APP_PASSWORD,
        "SKYLIGHT_RECIPE_EMAIL": SKYLIGHT_RECIPE_EMAIL,
        "SKYLIGHT_LOGIN_EMAIL": SKYLIGHT_LOGIN_EMAIL,
        "SKYLIGHT_PASSWORD": SKYLIGHT_PASSWORD,
    }
    return [k for k, v in required.items() if not v]
