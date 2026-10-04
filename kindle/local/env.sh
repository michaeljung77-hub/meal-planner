#!/usr/bin/env sh
# Bedroom dashboard settings (replaces dashboard/local/env.sh on the Kindle)

# Checks Wi-Fi by reaching the Beelink, so it works even if the internet is down
export WIFI_TEST_IP=${WIFI_TEST_IP:-192.168.4.51}

# 5:30 am (today) and 9:30 pm (tomorrow), every day
export REFRESH_SCHEDULE=${REFRESH_SCHEDULE:-"30 5,21 * * *"}
export TIMEZONE=${TIMEZONE:-"America/New_York"}

# Full (flashing) refresh every time: only twice a day, keeps the screen crisp
export FULL_DISPLAY_REFRESH_RATE=${FULL_DISPLAY_REFRESH_RATE:-1}

# Never replace the dashboard with the "Kindle is sleeping" screen
export SLEEP_SCREEN_INTERVAL=999999

export LOW_BATTERY_REPORTING=${LOW_BATTERY_REPORTING:-false}
export LOW_BATTERY_THRESHOLD_PERCENT=10
