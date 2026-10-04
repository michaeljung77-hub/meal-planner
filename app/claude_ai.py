"""All Claude API calls: ideas, recipes, tweaks, fingerprints, grocery list, taste profile."""

import json
import re

from . import config

_client = None


class AIError(Exception):
    pass


def client():
    global _client
    if _client is None:
        if not config.ANTHROPIC_API_KEY:
            raise AIError("The Claude API key is missing in the settings.")
        import anthropic
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=240, max_retries=2)
    return _client


SYSTEM = (
    "You are the family's personal chef and meal planner. You know home cooking across cuisines, "
    "write clear, reliable recipes in US units, and you answer ONLY with the JSON requested, "
    "no commentary and no markdown fences."
)


def _text(resp) -> str:
    return "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")


def _json(text: str):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start, end = text.find(open_c), text.rfind(close_c)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except ValueError:
                continue
    raise AIError("Claude's answer could not be read. Please try again.")


def ask(prompt: str, max_tokens: int = 4000, tools=None):
    try:
        import anthropic
        messages = [{"role": "user", "content": prompt}]
        kwargs = {"model": config.CLAUDE_MODEL, "max_tokens": max_tokens, "system": SYSTEM,
                  "messages": messages}
        if tools:
            kwargs["tools"] = tools
        resp = client().messages.create(**kwargs)
        # Long server-side tool runs (web search) can pause; continue them.
        for _ in range(3):
            if getattr(resp, "stop_reason", "") != "pause_turn":
                break
            messages = messages + [{"role": "assistant", "content": resp.content}]
            kwargs["messages"] = messages
            resp = client().messages.create(**kwargs)
        return _json(_text(resp))
    except AIError:
        raise
    except anthropic.AuthenticationError as e:
        raise AIError("The Claude API key was rejected. Check it in the settings.") from e
    except anthropic.APIStatusError as e:
        raise AIError(f"Claude API error {e.status_code}: {str(e.message)[:200]}") from e
    except anthropic.APIConnectionError as e:
        raise AIError("Could not reach the Claude API. Is the Beelink online?") from e


IDEA_FORMAT = """{"ideas": [{
  "name": "dish name",
  "pitch": "one appetizing sentence",
  "cuisine": "e.g. Mexican",
  "cook_minutes": 35,
  "day_type": "weeknight" or "weekend",
  "adventure": "safe" or "stretch" or "elevated",
  "kind": "favorite" or "remix" or "new" or "wildcard",
  "library_slug": "slug of the matching recipe from OUR LIBRARY when kind is favorite, else null",
  "is_pasta": false,
  "kid_note": "how Sebastian gets a mild/familiar version (short)",
  "why": "short reason tied to the family's taste, e.g. 'because you loved the creamy tang of ...'",
  "traits": {"protein": "chicken", "method": "skillet", "flavors": ["creamy", "tangy"],
             "spice": "mild" or "medium" or "hot", "effort": "easy" or "medium" or "project"}
}]}"""


def generate_ideas(ctx: dict, count: int, direction: str = "", avoid: list[str] | None = None,
                   like: dict | None = None) -> list[dict]:
    r = ctx["rules"]
    task = f"Suggest {count} dinner ideas for the coming week."
    if like:
        task = (f"Suggest {count} variations or close relatives of this dish the family is interested in: "
                f"{json.dumps(like)}. Keep what makes it appealing, vary cuisine, protein or technique.")
    prompt = f"""{task}

HOUSEHOLD: {r['household']}
SERVINGS: {r['servings']}

HOUSE RULES (follow them):
- Weeknight dishes: mostly at most {r['weeknight_max_minutes']} minutes; {r['weeknight_stretch']}.
- Weekend dishes: elevated cooking projects welcome, no time limit. Include a few weekend ideas.
- Mix: {r['favorites_share']}. Include {r['wildcards']} wildcard(s) to discover new favorites.
- At most {r['max_pasta']} pasta dish(es) in the set.
- {"Every stretch/elevated dish needs a mild or sauce-on-the-side option for Sebastian (kid_note)." if r['kid_mild_option'] else ""}
- Keep it international, rotating through: {r['cuisines']}.
- Favor ingredient overlap between ideas so one shop covers several meals.
- Shopping happens at {r['stores']}; prefer ingredients they carry.

FAMILY TASTE PROFILE:
{ctx['profile'] or '(still learning; lean on the library ratings below)'}

FAMILY NOTES (written by the family, always respect):
{ctx['notes'] or '(none)'}

FLAVOR PATTERNS LEARNED FROM RATINGS (positive = liked, negative = disliked):
{ctx['trait_text'] or '(not enough data yet)'}

OUR LIBRARY (favorites available to suggest again, with slug):
{ctx['favorites_text'] or '(none yet)'}

RESTING (cooked recently, do NOT suggest): {ctx['resting_text'] or 'none'}
RETIRED (never suggest these or near-copies): {ctx['retired_text'] or 'none'}
RECENTLY SUGGESTED OR COOKED (avoid repeating): {', '.join((avoid or [])[:60]) or 'none'}
{('DIRECTION FROM THE FAMILY FOR THIS BATCH: ' + direction) if direction else ''}

Most ideas should be NEW dishes built on flavor profiles the family loves, not repeats.
Return JSON exactly in this format:
{IDEA_FORMAT}"""
    data = ask(prompt, max_tokens=6000)
    ideas = data.get("ideas") if isinstance(data, dict) else data
    if not isinstance(ideas, list) or not ideas:
        raise AIError("Claude returned no ideas. Please try again.")
    return [i for i in ideas if isinstance(i, dict) and i.get("name")]


def custom_idea(ctx: dict, text: str) -> dict:
    prompt = f"""The family wants to add their own idea to this week's plan: "{text}"
Turn it into one concrete dish idea for this household: {ctx['rules']['household']}
Taste profile: {ctx['profile'] or 'still learning'}
If it is a URL, describe the dish at that URL as best you can from the URL itself.
Return JSON exactly in this format with a single idea, kind "new":
{IDEA_FORMAT}"""
    data = ask(prompt, max_tokens=1500)
    ideas = data.get("ideas") if isinstance(data, dict) else data
    if not ideas:
        raise AIError("Could not turn that into an idea.")
    return ideas[0]


def find_recipe_url(idea: dict, tweaks: str, exclude: list[str]) -> str | None:
    tools = [{"type": config.CLAUDE_WEB_SEARCH_TOOL, "name": "web_search", "max_uses": 4}]
    prompt = f"""Find ONE real, well-reviewed recipe page online for this dish:
{json.dumps({k: idea.get(k) for k in ('name', 'pitch', 'cuisine', 'cook_minutes')})}
{('Preferences: ' + tweaks) if tweaks else ''}
Prefer reputable recipe sites whose pages contain a full ingredient list and steps
(e.g. Serious Eats, NYT Cooking free pages, Bon Appetit, Food Network, RecipeTin Eats,
Budget Bytes, Simply Recipes, Chefkoch for German dishes, Just One Cookbook for Japanese, Maangchi for Korean).
Avoid video-only pages, paywalls, PDFs and these URLs: {exclude or 'none'}.
Return JSON: {{"url": "https://...", "title": "page title"}}"""
    try:
        data = ask(prompt, max_tokens=3000, tools=tools)
    except AIError:
        return None
    url = (data or {}).get("url") if isinstance(data, dict) else None
    return url if isinstance(url, str) and url.startswith("http") else None


RECIPE_FORMAT = """{
 "@context": "https://schema.org", "@type": "Recipe",
 "name": "...", "description": "one or two sentences",
 "recipeYield": "4 servings", "prepTime": "PT15M", "cookTime": "PT25M", "totalTime": "PT40M",
 "recipeCuisine": "...",
 "recipeIngredient": ["1 1/2 lb boneless chicken thighs", "..."],
 "recipeInstructions": [{"@type": "HowToStep", "text": "..."}]
}"""


def write_recipe(idea: dict, tweaks: str, servings: int, kid_option: bool) -> dict:
    prompt = f"""Write a complete, reliable home recipe for:
{json.dumps({k: idea.get(k) for k in ('name', 'pitch', 'cuisine', 'cook_minutes', 'kid_note', 'traits')})}
Servings: {servings}. US units. Ingredients that Aldi/Lidl carry where possible.
{('Family adjustments to apply: ' + tweaks) if tweaks else ''}
Write instructions as full sentences with temperatures as "425 F" and doneness cues.
{"If the dish is spicy or adventurous, end with a step starting 'For Sebastian:' describing the mild version." if kid_option else ""}
Return ONLY schema.org Recipe JSON in this format:
{RECIPE_FORMAT}"""
    rec = ask(prompt, max_tokens=4000)
    if not isinstance(rec, dict) or not rec.get("recipeIngredient"):
        raise AIError("Claude did not return a complete recipe.")
    rec.setdefault("@context", "https://schema.org")
    rec["@type"] = "Recipe"
    return rec


def adapt_recipe(existing: dict, tweaks: str, servings: int) -> dict:
    slim = {"name": existing.get("name"), "description": existing.get("description"),
            "recipeIngredient": existing.get("_ingredients"), "recipeInstructions": existing.get("_steps")}
    prompt = f"""Adapt this recipe for the family. Requested changes: {tweaks}
Keep everything else faithful. Servings: {servings}. US units.
Name it like the original plus a short hint of the change, e.g. "Chicken Tikka Masala (Mild)".
Original:
{json.dumps(slim)}
Return ONLY schema.org Recipe JSON in this format:
{RECIPE_FORMAT}"""
    rec = ask(prompt, max_tokens=4000)
    if not isinstance(rec, dict) or not rec.get("recipeIngredient"):
        raise AIError("Claude did not return a complete adapted recipe.")
    rec["@type"] = "Recipe"
    rec.setdefault("@context", "https://schema.org")
    return rec


def fingerprint(recipes: list[dict]) -> dict:
    """recipes: [{slug, name, ingredients}] -> {slug: traits}"""
    prompt = f"""Tag each recipe with its flavor fingerprint.
Recipes: {json.dumps(recipes)}
Return JSON: {{"<slug>": {{"cuisine": "...", "protein": "...", "method": "...",
 "flavors": ["creamy", "tangy"], "spice": "mild|medium|hot", "effort": "easy|medium|project",
 "kid_friendly": "yes|maybe|no"}}, ...}}
Use short lowercase words. Flavors from: creamy, tangy, smoky, herby, umami, sweet-savory, spicy,
garlicky, cheesy, citrusy, rich, fresh, crispy, saucy, earthy."""
    data = ask(prompt, max_tokens=4000)
    return data if isinstance(data, dict) else {}


def grocery_list(meals: list[dict], pantry_skip: list[str], pantry_low: list[str], stores: str) -> dict:
    prompt = f"""Build one consolidated grocery list for this week's meals.
Meals with ingredients: {json.dumps(meals)}
Pantry staples the family already has (leave them OUT unless clearly needed in a larger amount than a
household keeps): {', '.join(pantry_skip) or 'none'}
Pantry items running low (ADD these): {', '.join(pantry_low) or 'none'}
Stores: {stores}

Rules:
- Combine duplicates and total the quantities in shopping units (e.g. "2 lb", "1 bunch", "1 can (28 oz)").
- Group by aisle in the order of a typical Aldi store walk: Produce, Bakery, Meat & Seafood, Dairy & Eggs,
  Deli & Cheese, Pantry & Canned, International, Spices & Baking, Frozen, Other.
- used_in lists the meal names using the item. Set other_store true when Aldi/Lidl usually don't carry it.
Return JSON: {{"aisles": [{{"aisle": "Produce", "items": [{{"item": "Yellow onions", "qty": "3",
"used_in": ["Meal A"], "other_store": false}}]}}]}}"""
    data = ask(prompt, max_tokens=5000)
    if not isinstance(data, dict) or "aisles" not in data:
        raise AIError("Could not build the grocery list. Please try again.")
    return data


def refresh_profile(old_profile: str, notes: str, trait_text: str, verdicts: list[dict]) -> str:
    prompt = f"""Rewrite the family's taste profile (plain language, 120-180 words, second person plural
"you", no bullet points). Describe flavor patterns they love, what tends to miss, Sebastian's comfort zone,
and where there is room to explore. Base it on the evidence; keep valid points from the old profile.
Old profile: {old_profile or '(none)'}
Family notes: {notes or '(none)'}
Flavor scores (positive liked, negative disliked): {trait_text or '(none)'}
Recent verdicts: {json.dumps(verdicts[-40:])}
Return JSON: {{"profile": "..."}}"""
    data = ask(prompt, max_tokens=1200)
    text = data.get("profile") if isinstance(data, dict) else None
    if not text:
        raise AIError("Could not refresh the taste profile.")
    return text.strip()


def ping() -> str:
    data = ask('Reply with JSON {"ok": true}', max_tokens=20)
    return "ok" if data else "?"
