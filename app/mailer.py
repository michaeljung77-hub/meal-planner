"""Sends recipes to the Skylight by email (the official Sidekick import route)."""

import re
import smtplib
import ssl
from email.message import EmailMessage

from . import config, mealie

_REPLACE = {
    "°": " degrees ", "½": "1/2", "¼": "1/4", "¾": "3/4", "⅓": "1/3",
    "⅔": "2/3", "⅛": "1/8", "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "…": "...", "×": "x", " ": " ",
}


def plain(text: str) -> str:
    """Plain ASCII only, which Skylight's Recipe Box parses cleanly."""
    for k, v in _REPLACE.items():
        text = text.replace(k, v)
    text = text.encode("ascii", "ignore").decode()
    return re.sub(r"[ \t]+", " ", text).strip()


def recipe_text(rec: dict) -> str:
    parts = [plain(rec.get("name") or "Recipe")]
    meta = []
    if rec.get("recipeYield") or rec.get("recipeServings"):
        meta.append(f"Serves: {plain(str(rec.get('recipeYield') or rec.get('recipeServings')))}")
    if rec.get("totalTime"):
        meta.append(f"Total time: {plain(str(rec['totalTime']))}")
    if meta:
        parts.append(" | ".join(meta))
    if rec.get("description"):
        parts.append(plain(rec["description"]))
    parts.append("")
    parts.append("Ingredients")
    parts += [f"- {plain(i)}" for i in mealie.ingredient_lines(rec)]
    parts.append("")
    parts.append("Instructions")
    parts += [f"{n}. {plain(s)}" for n, s in enumerate(mealie.instruction_lines(rec), 1)]
    return "\n".join(parts)


def send(subject: str, body: str) -> None:
    if not (config.GMAIL_USER and config.GMAIL_APP_PASSWORD and config.SKYLIGHT_RECIPE_EMAIL):
        raise RuntimeError("Gmail address, app password or Skylight email is missing in the settings.")
    msg = EmailMessage()
    msg["From"] = config.GMAIL_USER
    msg["To"] = config.SKYLIGHT_RECIPE_EMAIL
    msg["Subject"] = plain(subject)
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=60) as s:
        s.login(config.GMAIL_USER, config.GMAIL_APP_PASSWORD)
        s.send_message(msg)


def test_login() -> None:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=30) as s:
        s.login(config.GMAIL_USER, config.GMAIL_APP_PASSWORD)
