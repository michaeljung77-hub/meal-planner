"""E-ink dashboard image for the bedroom Kindle: weather plus the day's Skylight events.

Before KINDLE_TOMORROW_AFTER (5 pm by default) it shows today; after that, tomorrow,
so the 9:30 pm refresh shows the next day and stays on screen overnight.
"""

import io
import logging
import math
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFont

from . import config, skylight

log = logging.getLogger("planner.kindle")

W = int(os.environ.get("KINDLE_WIDTH", "758"))
H = int(os.environ.get("KINDLE_HEIGHT", "1024"))
LAT = float(os.environ.get("WEATHER_LAT", "34.8526"))     # Greenville, SC
LON = float(os.environ.get("WEATHER_LON", "-82.3940"))
TOMORROW_AFTER = int(os.environ.get("KINDLE_TOMORROW_AFTER", "17"))

BLACK, DARK, MID, LIGHT, WHITE = 0, 60, 120, 200, 255

FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF"]


def _font(name: str, size: int):
    for d in FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def F(size, bold=False, serif=False):
    if serif:
        return _font("DejaVuSerif-Bold.ttf" if bold else "DejaVuSerif.ttf", size)
    return _font("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)


# ------------------------------------------------------------------ weather

WMO = {
    0: ("Clear", "sun"), 1: ("Mostly clear", "sun"), 2: ("Partly cloudy", "partly"), 3: ("Cloudy", "cloud"),
    45: ("Fog", "fog"), 48: ("Fog", "fog"),
    51: ("Light drizzle", "rain"), 53: ("Drizzle", "rain"), 55: ("Heavy drizzle", "rain"),
    56: ("Freezing drizzle", "rain"), 57: ("Freezing drizzle", "rain"),
    61: ("Light rain", "rain"), 63: ("Rain", "rain"), 65: ("Heavy rain", "rain"),
    66: ("Freezing rain", "rain"), 67: ("Freezing rain", "rain"),
    71: ("Light snow", "snow"), 73: ("Snow", "snow"), 75: ("Heavy snow", "snow"), 77: ("Snow grains", "snow"),
    80: ("Showers", "rain"), 81: ("Showers", "rain"), 82: ("Heavy showers", "rain"),
    85: ("Snow showers", "snow"), 86: ("Snow showers", "snow"),
    95: ("Thunderstorms", "storm"), 96: ("Thunderstorms", "storm"), 99: ("Thunderstorms", "storm"),
}


def weather(day) -> dict:
    r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=20, params={
        "latitude": LAT, "longitude": LON, "timezone": config.TZ,
        "temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "forecast_days": 3,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
                 "sunrise,sunset,wind_speed_10m_max",
        "hourly": "temperature_2m,weather_code,precipitation_probability",
    })
    r.raise_for_status()
    d = r.json()
    idx = d["daily"]["time"].index(day.isoformat())
    code = d["daily"]["weather_code"][idx]
    text, icon = WMO.get(code, ("", "cloud"))
    parts = []
    for label, hour in (("Morning", 8), ("Afternoon", 14), ("Evening", 19)):
        key = f"{day.isoformat()}T{hour:02d}:00"
        if key in d["hourly"]["time"]:
            i = d["hourly"]["time"].index(key)
            parts.append({"label": label, "temp": round(d["hourly"]["temperature_2m"][i]),
                          "icon": WMO.get(d["hourly"]["weather_code"][i], ("", "cloud"))[1],
                          "rain": d["hourly"]["precipitation_probability"][i]})
    return {
        "text": text, "icon": icon,
        "high": round(d["daily"]["temperature_2m_max"][idx]),
        "low": round(d["daily"]["temperature_2m_min"][idx]),
        "rain": d["daily"]["precipitation_probability_max"][idx],
        "wind": round(d["daily"]["wind_speed_10m_max"][idx] or 0),
        "sunrise": datetime.fromisoformat(d["daily"]["sunrise"][idx]),
        "sunset": datetime.fromisoformat(d["daily"]["sunset"][idx]),
        "parts": parts,
    }


# -------------------------------------------------------------------- icons

def _sun(dr, cx, cy, r, w):
    dr.ellipse([cx - r, cy - r, cx + r, cy + r], outline=BLACK, width=w)
    for k in range(8):
        a = k * math.pi / 4
        dr.line([cx + math.cos(a) * r * 1.35, cy + math.sin(a) * r * 1.35,
                 cx + math.cos(a) * r * 1.8, cy + math.sin(a) * r * 1.8], fill=BLACK, width=w)


def _cloud(dr, cx, cy, s, w, fill=WHITE):
    parts = [(-0.45, 0.05, 0.38), (0.0, -0.18, 0.5), (0.45, 0.05, 0.38)]

    def shape(color, grow):
        for dx, dy, rr in parts:
            dr.ellipse([cx + (dx - rr) * s - grow, cy + (dy - rr) * s - grow,
                        cx + (dx + rr) * s + grow, cy + (dy + rr) * s + grow], fill=color)
        dr.rectangle([cx - 0.45 * s - grow, cy + 0.05 * s - grow, cx + 0.45 * s + grow, cy + 0.43 * s + grow],
                     fill=color)

    shape(BLACK, w / 2)   # outline = silhouette slightly larger, then fill inside
    shape(fill, -w / 2)


def icon(dr, kind, cx, cy, size):
    w = max(2, size // 22)
    s = size * 0.55
    if kind == "sun":
        _sun(dr, cx, cy, size * 0.26, w)
    elif kind == "partly":
        _sun(dr, cx - size * 0.15, cy - size * 0.15, size * 0.18, w)
        _cloud(dr, cx + size * 0.08, cy + size * 0.08, s * 0.85, w)
    elif kind in ("cloud", "fog"):
        _cloud(dr, cx, cy - size * 0.05, s, w)
        if kind == "fog":
            for k in range(3):
                y = cy + size * (0.32 + k * 0.09)
                dr.line([cx - size * 0.35, y, cx + size * 0.35, y], fill=BLACK, width=w)
    elif kind in ("rain", "storm", "snow"):
        _cloud(dr, cx, cy - size * 0.15, s, w)
        base = cy + size * 0.18
        for k, dx in enumerate((-0.22, 0, 0.22)):
            x = cx + dx * size
            if kind == "snow":
                r = size * 0.04
                dr.ellipse([x - r, base + size * 0.08 - r, x + r, base + size * 0.08 + r], fill=BLACK)
            elif kind == "storm" and k == 1:
                dr.line([x + size * 0.05, base, x - size * 0.05, base + size * 0.12,
                         x + size * 0.05, base + size * 0.12, x - size * 0.05, base + size * 0.26],
                        fill=BLACK, width=w)
            else:
                dr.line([x + size * 0.04, base, x - size * 0.04, base + size * 0.18], fill=BLACK, width=w)


# ------------------------------------------------------------------- render

def _fmt_time(t: datetime) -> str:
    return t.strftime("%I:%M %p").lstrip("0").replace(":00 ", " ")


def _fit(dr, text, font, max_w):
    if dr.textlength(text, font=font) <= max_w:
        return text
    while text and dr.textlength(text + "...", font=font) > max_w:
        text = text[:-1]
    return text.rstrip() + "..."


def target_day(now: datetime, which: str = "auto"):
    if which == "today":
        return now.date(), "Today"
    if which == "tomorrow" or (which == "auto" and now.hour >= TOMORROW_AFTER):
        return now.date() + timedelta(days=1), "Tomorrow"
    return now.date(), "Today"


def render(which: str = "auto", now: datetime | None = None, wx=None, events=None) -> bytes:
    tz = ZoneInfo(config.TZ)
    now = now or datetime.now(tz)
    day, label = target_day(now, which)

    if wx is None:
        try:
            wx = weather(day)
        except Exception as e:  # never leave the nightstand blank
            log.warning("Weather failed: %s", e)
            wx = None
    if events is None:
        try:
            events = skylight.events_for(day, config.TZ)
        except Exception as e:
            log.warning("Calendar failed: %s", e)
            events = None

    img = Image.new("L", (W, H), WHITE)
    dr = ImageDraw.Draw(img)
    M = 44

    # Header
    dr.text((M, 40), label.upper(), font=F(26, bold=True), fill=MID)
    dr.text((M, 74), day.strftime("%A"), font=F(64, bold=True, serif=True), fill=BLACK)
    dr.text((M, 150), day.strftime("%B %-d"), font=F(40, serif=True), fill=DARK)
    dr.line([M, 222, W - M, 222], fill=BLACK, width=3)

    # Weather
    y = 246
    if wx:
        icon(dr, wx["icon"], M + 95, y + 100, 190)
        x = M + 225
        hi = f"{wx['high']}°"
        dr.text((x, y + 4), hi, font=F(104, bold=True), fill=BLACK)
        hw = dr.textlength(hi, font=F(104, bold=True))
        dr.text((x + hw + 16, y + 26), f"/ {wx['low']}°", font=F(46), fill=DARK)
        dr.text((x, y + 128), _fit(dr, wx["text"], F(34, bold=True), W - M - x), font=F(34, bold=True), fill=BLACK)
        extra = f"Rain {wx['rain']}%" if wx["rain"] is not None else ""
        if wx["wind"] >= 15:
            extra += f"  ·  Wind {wx['wind']} mph"
        dr.text((x, y + 172), extra, font=F(28), fill=DARK)

        # morning / afternoon / evening (skipped on busy days to make room for events)
        py = y + 236
        busy = events is not None and len(events) > 4
        if wx["parts"] and not busy:
            cw = (W - 2 * M) / len(wx["parts"])
            for i, p in enumerate(wx["parts"]):
                cx = M + cw * i + cw / 2
                dr.text((cx, py), p["label"], font=F(24), fill=MID, anchor="mt")
                icon(dr, p["icon"], cx - 44, py + 68, 64)
                dr.text((cx + 6, py + 50), f"{p['temp']}°", font=F(38, bold=True), fill=BLACK, anchor="lt")
        sun = f"Sunrise {_fmt_time(wx['sunrise'])}   ·   Sunset {_fmt_time(wx['sunset'])}"
        sun_y = py + 128 if not busy else y + 218
        dr.text((W / 2 if not busy else M, sun_y), sun, font=F(22), fill=MID, anchor="mt" if not busy else "lt")
        sep = 650 if not busy else 500
    else:
        dr.text((M, y + 60), "Weather unavailable", font=F(34, bold=True), fill=DARK)
        sep = 400
    dr.line([M, sep, W - M, sep], fill=BLACK, width=3)

    # Events
    y = sep + 22
    dr.text((M, y), "SCHEDULE", font=F(24, bold=True), fill=MID)
    y += 46
    row_h, bottom = 54, H - 70
    if events is None:
        dr.text((M, y), "Calendar unavailable", font=F(32), fill=DARK)
    elif not events:
        dr.text((M, y), "Nothing scheduled", font=F(34, serif=True), fill=DARK)
    else:
        tcol = 170
        max_rows = (bottom - y) // row_h
        shown = events if len(events) <= max_rows else events[:max_rows - 1]
        for ev in shown:
            when = "All day" if ev["all_day"] else ("Ongoing" if ev["started_before"] else _fmt_time(ev["start"]))
            dr.text((M, y + 4), when, font=F(28, bold=not ev["all_day"]), fill=DARK if ev["all_day"] else BLACK)
            dr.text((M + tcol, y), _fit(dr, ev["title"], F(34), W - M - (M + tcol)), font=F(34), fill=BLACK)
            y += row_h
        if len(shown) < len(events):
            dr.text((M + tcol, y + 2), f"+ {len(events) - len(shown)} more", font=F(28), fill=MID)

    # Footer
    dr.text((W - M, H - 34), f"Updated {_fmt_time(now)}", font=F(20), fill=MID, anchor="rm")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
