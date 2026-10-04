# Install guide: Family Meal Planner on the Beelink (CasaOS)

Time: about 30 minutes. Do it on a computer, with your iPhone nearby for the last part.

Have these ready in your password manager:
- Claude API key
- Mealie API token
- Gmail app password (meal planner account)
- Your Skylight app password

---

## Part A: Make the app image downloadable (2 min)

GitHub already built the app. Because the repository is private, the app image is private too,
and CasaOS can't download it yet. The image contains only code, no passwords, so it's safe to make public.

1. Go to **github.com/michaeljung77-hub?tab=packages** and click **meal-planner**.
2. On the right, click **Package settings**.
3. Scroll to **Danger Zone**, click **Change visibility**, choose **Public**, type `meal-planner` and confirm.

(Your code repository stays private; only the ready-to-run image becomes public.)

## Part B: Check the Skylight password (2 min)

The grocery list sync logs into Skylight with an email and password.
If you normally sign in to the Skylight app with **"Continue with Google"**, you don't have a Skylight password yet:
open the Skylight app, sign out, choose **Forgot password** with `michael.jung77@googlemail.com`, and set one.
Your Google sign-in keeps working.

## Part C: Install the app in CasaOS (10 min)

1. In CasaOS, open **App Store** and click **Custom Install** (top right), then the **Import** icon.
2. Paste the file below and click **Submit**.

```yaml
services:
  meal-planner:
    image: ghcr.io/michaeljung77-hub/meal-planner:latest
    container_name: meal-planner
    restart: unless-stopped
    ports:
      - "8090:8090"
    volumes:
      - /DATA/AppData/meal-planner:/data
    environment:
      TZ: America/New_York
      ANTHROPIC_API_KEY: CHANGE-ME
      MEALIE_URL: http://192.168.4.51:9925
      MEALIE_TOKEN: CHANGE-ME
      GMAIL_USER: jungfamily.mealplanner@gmail.com
      GMAIL_APP_PASSWORD: CHANGE-ME
      SKYLIGHT_RECIPE_EMAIL: jung_family@ourskylight.com
      SKYLIGHT_LOGIN_EMAIL: michael.jung77@googlemail.com
      SKYLIGHT_PASSWORD: CHANGE-ME
      SKYLIGHT_LIST_NAME: Grocery List
    deploy:
      resources:
        limits:
          memory: 512M
```

3. **Before you click Install, check the form** (CasaOS dropped these for Mealie last time):
   - **Title**: `Meal Planner`
   - **Web UI**: `http://` `192.168.4.51` port `8090`
   - **Port**: Host `8090`, Container `8090`, TCP. Add it with **+ Add** if missing.
   - **Volumes**: Host `/DATA/AppData/meal-planner`, Container `/data`. Add it if missing.
   - **Environment Variables**: replace each `CHANGE-ME` with the real value from your password manager.
     Gmail app passwords work with or without the spaces.
4. Click **Install** and wait for the icon to appear (the first download takes a minute or two).

Port 8090 is free on your setup (health dashboard 8080, Mealie 9925). If CasaOS says it's taken, use 8091 on the **host** side only.

## Part D: First start and connection test (5 min)

1. Open **http://192.168.4.51:8090** in a browser. You should see "Ready when you are".
   If a yellow box lists missing settings, open the app's settings in CasaOS, fill them in, and click **Save**.
2. Tap **House rules**, scroll to **Connections**, tap **Test connections**. You want four green checks:
   - **Mealie**: shows your name and recipe count.
   - **Claude API**: model answered.
   - **Gmail to Skylight**: Gmail login OK.
   - **Skylight grocery list**: found your Skylight and the list "Grocery List".
3. Anything red: the message says what's wrong. The usual fixes:

| Message | Fix |
| --- | --- |
| Mealie rejected the API token | Create a new token in Mealie (Profile > API Tokens) and paste it into the settings |
| Could not reach Mealie | Check `MEALIE_URL` is `http://192.168.4.51:9925` |
| Claude API key was rejected | Re-copy the key from console.anthropic.com; check billing is active |
| Gmail: Username and Password not accepted | Re-create the app password in the meal planner Gmail |
| Skylight login failed | Part B: set a Skylight password, then update `SKYLIGHT_PASSWORD` |
| Could not find a list named 'Grocery List' | Match the exact list name in `SKYLIGHT_LIST_NAME` |

After changing a setting in CasaOS, click **Save**; the app restarts on its own.

## Part E: Put it on your iPhone (2 min)

1. On the iPhone (home Wi-Fi), open Safari and go to **http://192.168.4.51:8090**.
2. Tap **Share**, then **Add to Home Screen**, name it **Meal Planner**, and tap **Add**.

It opens full screen like an app, with its own icon.

## Part F: Your first Saturday

1. Tap **Start planning**. The first week skips rating, because nothing has been planned yet.
2. **Pantry**: the starter staples list is there; tap what's running low. Long-press any staple you don't keep and remove it, and add your own at the bottom.
3. **Get ideas**: the first run takes 1 to 2 minutes, because the planner reads your 21 rated Mealie recipes and builds the first taste profile. Later runs take about a minute.
4. Pick meals, choose **Real recipe** or **Write one** for each, add changes if you like, then **Prepare recipes**.
5. **Build grocery list**, remove what you already have, then **Send to Skylight**.
6. Check the Skylight: recipes appear in the Recipe Box within a few minutes (Sidekick processes the emails), and the grocery items are on the list right away.

Also worth a look once: **Taste profile** on the home screen. Read what the planner thinks your family likes and correct anything that's off. Add family notes like "Sebastian loves rice dishes" there.

## Updating later

When I improve the app, GitHub builds a new version automatically. To install it, open the app's
settings in CasaOS and click **Save** without changing anything; CasaOS pulls the newest image.
Your data in `/DATA/AppData/meal-planner` stays untouched.

## Costs

Claude API: roughly $0.50 to $1.50 per Saturday session, depending on how many new batches and
web-searched recipes you use. Keep the monthly limit in the Claude Console at about $10.
