"""Pushes the grocery list onto the Skylight (unofficial API via pyskylight)."""

import asyncio

from . import config, db


class SkylightError(Exception):
    pass


def _run(coro):
    """Run async Skylight calls from anywhere, including inside the web server's event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def _with_client(fn):
    try:
        from pyskylight import PasswordAuth, Skylight
    except ImportError as e:  # pragma: no cover
        raise SkylightError("pyskylight is not installed") from e
    if not (config.SKYLIGHT_LOGIN_EMAIL and config.SKYLIGHT_PASSWORD):
        raise SkylightError("Skylight login email or password is missing in the settings.")
    try:
        async with Skylight(PasswordAuth(config.SKYLIGHT_LOGIN_EMAIL, config.SKYLIGHT_PASSWORD)) as sky:
            return await fn(sky)
    except SkylightError:
        raise
    except Exception as e:
        name = type(e).__name__
        if "Auth" in name:
            raise SkylightError("Skylight login failed. Check the email and password in the settings "
                                "(a 'Sign in with Google' account needs a Skylight password first).") from e
        raise SkylightError(f"Skylight problem: {name}: {e}") from e


async def _frame(sky):
    frame_id = config.SKYLIGHT_FRAME_ID or db.get_setting("skylight_frame_id")
    frame_name = db.get_setting("skylight_frame_name", "")
    if not frame_id:
        frames = await sky.get_frames()
        if not frames:
            raise SkylightError("No Skylight calendar found on this account.")
        best = next((f for f in frames if getattr(f, "mine", False)), frames[0])
        frame_id, frame_name = str(best.id), best.name or best.household_name or ""
        db.set_setting("skylight_frame_id", frame_id)
        db.set_setting("skylight_frame_name", frame_name)
    return frame_id, frame_name


async def _find_target(sky):
    frame_id, frame_name = await _frame(sky)
    lists = await sky.get_lists(frame_id)
    want = config.SKYLIGHT_LIST_NAME.lower()
    target = (next((l for l in lists if (l.label or "").strip().lower() == want), None)
              or next((l for l in lists if l.default_grocery_list), None)
              or next((l for l in lists if l.kind == "shopping"), None))
    if not target:
        raise SkylightError(f"Could not find a list named '{config.SKYLIGHT_LIST_NAME}' on the Skylight.")
    return frame_id, frame_name, target


def test() -> dict:
    async def run(sky):
        frame_id, frame_name, target = await _find_target(sky)
        return {"frame_id": frame_id, "frame_name": frame_name, "list": target.label}
    return _run(_with_client(run))


def push_items(labels: list[str]) -> dict:
    async def run(sky):
        frame_id, _, target = await _find_target(sky)
        existing = await sky.get_list_items(frame_id, target.id)
        have = {(i.label or "").strip().lower() for i in existing if not i.completed}
        added, skipped = 0, 0
        for label in labels:
            if label.strip().lower() in have:
                skipped += 1
                continue
            await sky.create_list_item(frame_id, target.id, label)
            added += 1
        return {"added": added, "already_there": skipped, "list": target.label}
    return _run(_with_client(run))


def events_for(day, tz_name: str) -> list[dict]:
    """Calendar events (including ones typed on the Skylight) that touch the given local date."""
    from datetime import datetime, time, timedelta
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    start = datetime.combine(day, time.min, tz)
    end = start + timedelta(days=1)

    async def run(sky):
        frame_id, _ = await _frame(sky)
        return await sky.get_calendar_events(frame_id, (day - timedelta(days=1)).isoformat(),
                                             (day + timedelta(days=1)).isoformat(), timezone=tz_name)

    out, seen = [], set()
    for e in _run(_with_client(run)):
        if not e.starts_at:
            continue
        s = e.starts_at.astimezone(tz)
        en = (e.ends_at or e.starts_at).astimezone(tz)
        if e.all_day:
            # all-day events end at midnight of the following day
            if not (s.date() <= day < max(en.date(), s.date() + timedelta(days=1))):
                continue
        elif not (s < end and en > start) and not (s >= start and s < end):
            continue
        key = (e.summary, s.isoformat(), bool(e.all_day))
        if key in seen:
            continue
        seen.add(key)
        out.append({"title": (e.summary or "Untitled").strip(), "all_day": bool(e.all_day),
                    "start": s, "end": en, "started_before": (not e.all_day) and s < start})
    out.sort(key=lambda x: (not x["all_day"], x["start"]))
    return out
