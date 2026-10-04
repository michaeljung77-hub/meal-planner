# Bedroom Kindle dashboard

The Meal Planner serves an e-ink image at `http://192.168.4.51:8090/kindle.png`
(758 x 1024, grayscale): weather for Greenville plus the day's Skylight events.
Before 5 pm it shows today, after 5 pm tomorrow. Add `?day=today` or `?day=tomorrow` to force one.

The Kindle runs [kindle-dash](https://github.com/pascalw/kindle-dash). Copy the two files in
`local/` over the ones in `dashboard/local/` on the Kindle. They set the schedule
(5:30 am and 9:30 pm) and point the download at the Beelink.

Optional settings for the Meal Planner app (CasaOS environment variables):
`WEATHER_LAT`, `WEATHER_LON` (default Greenville, SC), `KINDLE_TOMORROW_AFTER` (default 17).
