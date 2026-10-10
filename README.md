# Family Meal Planner

A small web app for the Saturday planning session, built for an iPhone home screen.
It runs on the Beelink next to Mealie and connects:

- **Claude API**: dinner ideas, finding real recipes online, writing or adapting recipes, flavor fingerprints, the grocery list and the family taste profile.
- **Mealie**: the recipe library. Every chosen recipe is saved there.
- **Skylight**: recipes go to the Recipe Box by email (official Sidekick route); the grocery list goes straight onto the Skylight list (unofficial API via [pyskylight](https://github.com/dknowles2/pyskylight)).

## The Saturday flow

1. **Rate last week**: Loved / Good / Meh / Miss, plus an optional note.
2. **Pantry check**: tap staples that are running low.
3. **Ideas**: about 12 cards with adventure level, time, kid note and why it was suggested. Pick, "More like this", new batch with a direction, or add your own idea.
4. **Recipes**: per meal choose *Real recipe* (web search + Mealie import) or *Write one*, optionally with changes.
5. **Review & shop**: grocery list by Aldi aisle, Publix/Ingles flags, remove what you have.
6. **Send to Skylight**: recipes emailed, groceries pushed, week logged.

## How it learns

Every meal carries a flavor fingerprint (cuisine, protein, method, flavors, spice, effort).
Ratings, picks and skipped ideas add up to trait scores with recent weeks counting more.
Claude rewrites a readable taste profile after new ratings; you can edit it, and family notes
are always respected. Favorites rest for a few weeks; "Miss" retires a dish.

## Settings (environment variables, entered in CasaOS)

| Variable | Meaning |
| --- | --- |
| `ANTHROPIC_API_KEY` | Claude API key |
| `ANTHROPIC_WORKSPACE_ID` | only if the key works across several Console workspaces (starts with `wrkspc_`) |
| `CLAUDE_MODEL` | optional, default `claude-sonnet-5` |
| `MEALIE_URL` | e.g. `http://192.168.4.51:9925` |
| `MEALIE_TOKEN` | Mealie API token |
| `GMAIL_USER`, `GMAIL_APP_PASSWORD` | sender account for Skylight emails |
| `SKYLIGHT_RECIPE_EMAIL` | the Skylight device email address |
| `SKYLIGHT_LOGIN_EMAIL`, `SKYLIGHT_PASSWORD` | Skylight app login (for the grocery list) |
| `SKYLIGHT_LIST_NAME` | default `Grocery List` |

Data lives in `/data/planner.db` (map it to `/DATA/AppData/meal-planner`).

## Build

Every push to `main` builds `ghcr.io/michaeljung77-hub/meal-planner:latest` with GitHub Actions.
