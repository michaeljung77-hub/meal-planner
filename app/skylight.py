"""Pushes the grocery list onto the Skylight (unofficial API via pyskylight)."""

import asyncio

from . import config, db


class SkylightError(Exception):
    pass


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


async def _find_target(sky):
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
    return asyncio.run(_with_client(run))


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
    return asyncio.run(_with_client(run))
