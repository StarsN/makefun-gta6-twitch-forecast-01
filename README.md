# GTA VI launch-day Twitch viewers — hour-by-hour quantile forecaster

[make.fun bounty: Forecast GTA VI's launch-day Twitch viewers hour by hour](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/StarsN/makefun-gta6-twitch-forecast-01/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/StarsN/makefun-gta6-twitch-forecast-01/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

An entry for make.fun's **gta6-twitch-ccu-forecast-01**: given everything recorded about a game
launch up to the end of its first UTC hour — that hour's concurrent-viewer print in the game's
Twitch category, the hourly history before it, and a library of past big launches with their full
hourly curves — forecast, for each of hours 2–24 of launch day, five quantiles (5/25/50/75/95%) of
that hour's viewer count. Scoring is the mean pinball loss on the log scale over all hours and
quantiles, so the median has to be right *and* the spread has to be honest.

`main.py` is the whole entry: Python 3.13, standard library only, no network, deterministic
(two runs on the same case write the same bytes), ~0.03 s per case against an 8 s cap.

## The model

A launch day's shape is forecast as a **ratio curve to its own first hour**, learned from the
comparables rather than assumed:

1. **Ratio samples.** For every comparable launch, take its release day (the 24 UTC hours from its
   `day_start`) and form, per hour *h*, the log ratio `log(viewers_h / viewers_1)`. A comparable
   whose day has no usable hour 1 contributes nothing; the target category's own pre-release
   history (present in every case's comparables) is not a launch and is excluded.
2. **Situation features.** Three numbers describe where a launch stands at the end of hour 1,
   computed identically for the target (from its `history_hourly`, or by bucketing `history`)
   and for each comparable (from its own hourly points):
   - **lift** — `log(hour-1 viewers / pre-launch baseline)`, the baseline being the median hourly
     viewers over the window 72–16 h before the day (wide fallback if sparse). It separates
     launches whose unlock wave has already lifted the category (rolling midnight unlocks, like
     GTA VI) from launches still sitting at baseline waiting for a later global unlock, and from
     early-access launches whose "baseline" is already gameplay.
   - **growth** — `log(hour-1 viewers / mean viewers of the 3 hours before the day)`: whether the
     wave was still building into hour 1 or already ebbing.
   - **level** — `log(hour-1 viewers)`: big launches trace different curves from small ones.
3. **Kernel pooling.** Each comparable is weighted by a Gaussian kernel over those features
   (bandwidths 0.7 / 0.7 / 1.5, floor 0.02 so nobody is fully silenced). For GTA VI — a
   rolling-midnight console launch whose category is already far above baseline at hour 1 — the
   pool that survives is dominated by exactly that class of launch (the Sonys, Rockstar's own
   previous launch, the rolling Call of Dutys), while simultaneous-global unlocks (a ×100 ramp
   still to come) and early-access titles (already peaked) fade out.
4. **Quantiles.** Per hour, the five levels are the weighted empirical quantiles of the pooled
   log ratios, lightly smoothed across neighbouring hours (weights 1-2-1), multiplied back by
   the case's hour-1 print, rounded to 2 decimals, and forced non-decreasing, positive and
   ≤ 1e9. If a case ever arrived with no usable comparables, every quantile falls back to the
   hour-1 print — a valid forecast, never a crash.

## Validation

`validate.py` scores the entry two ways (see `VALIDATION.md` for the full tables):

- **Practice cases p00–p03** (Wolverine, Red Dead Redemption 2, God of War Ragnarök,
  Spider-Man 2), against the launches' real hours 2–24: **0.2144** mean pinball loss vs the
  house persistence baseline's **0.3871** on the same actuals.
- **Leave-one-out over 37 comparable launches**, each forecast from the remaining pool through
  the same code path: **0.4762** vs the baseline's **0.9297**.

The practice case files stop at hour 1, so `practice_actuals.json` holds the real hours 2–24 —
the same SullyGnome hourly averages the kit was built from, re-fetched via the URLs in the kit's
`input/NOTICE.txt`. They reproduce every history point and hour-1 print in the kit exactly, and
scoring the kit's starter against them reproduces the house's published baseline loss of 0.387.

## Running it

```bash
# as the grader does (one case in the input dir):
MAKEFUN_INPUT_DIR=/path/to/input MAKEFUN_OUTPUT_DIR=/path/to/output python3 main.py

# validation (needs the kit's input/ directory):
python3 validate.py /path/to/kit/input
```
