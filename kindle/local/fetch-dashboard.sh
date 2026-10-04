#!/usr/bin/env sh
# Downloads the dashboard image from the Meal Planner on the Beelink into "$1".
# Before 5 pm the image shows today, after 5 pm it shows tomorrow.
"$(dirname "$0")/../xh" -d -q -o "$1" get http://192.168.4.51:8090/kindle.png
