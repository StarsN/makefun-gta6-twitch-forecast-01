"""Forecast GTA VI's launch-day Twitch viewers, hour by hour (make.fun gta6-twitch-ccu-forecast-01).

Reads one case file per run from the input directory: everything recorded about a game launch up to
the end of its first UTC hour - that hour's viewer print, the hourly history before it, and a library
of past big launches ("comparables") with their full hourly curves. Writes, for each of hours 2..24,
five quantiles (5/25/50/75/95%) of that hour's concurrent viewers in the category.

Method, in one paragraph: a launch day's shape is forecast as a ratio curve to its own first hour.
Each comparable contributes, per hour h, the log ratio log(viewers_h / viewers_1) of its release day.
Those log ratios are pooled with kernel weights that measure how similar the comparable's launch
situation was to this case's - how far the category had already lifted above its pre-launch baseline
by hour 1, how fast it was still growing into hour 1, and the log size of hour 1 itself - and the
weighted empirical quantiles of the pooled log ratios, lightly smoothed across neighbouring hours,
become the forecast quantiles after multiplying back by this case's hour-1 print. Launches whose
unlock wave had not started, had already peaked, or was drowned by early access sit far away in that
feature space and are down-weighted automatically; rolling-midnight console launches like this one
dominate the pool that remains. Pure standard library, no randomness, no network: two runs on the
same case write the same bytes.

Run by the grader as `python3 -P -s /bot/main.py` with the case alone in /input; locally,
MAKEFUN_INPUT_DIR and MAKEFUN_OUTPUT_DIR stand in for /input and /output.
"""

import json
import math
import os
from datetime import date
from pathlib import Path

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

DEFAULT_LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]

# Kernel bandwidths for (lift, growth into hour 1, log hour-1 viewers) and the weight floor that
# keeps every real launch in the pool with at least a whisper of influence.
BW_LIFT = 0.7
BW_GROWTH = 0.7
BW_LEVEL = 1.5
WEIGHT_FLOOR = 0.02

# Feature windows, in whole hours relative to the day's start (hour 1 begins at offset 0).
BASELINE_LO, BASELINE_HI = -72, -16   # pre-launch baseline window (before any unlock wave)
GROWTH_LO = -3                        # momentum window: the three hours before the day


def epoch(ts):
    """Seconds since the Unix epoch for an ISO 8601 UTC stamp like 2026-11-19T01:00:00Z."""
    days = date(int(ts[0:4]), int(ts[5:7]), int(ts[8:10])).toordinal() - 719163
    secs = int(ts[11:13]) * 3600 + int(ts[14:16]) * 60 + int(ts[17:19])
    return days * 86400 + secs


def hour_offsets(day_start, stamps):
    """Whole-hour offset of each stamp from day_start (offset 0 is the day's first hour)."""
    base = epoch(day_start)
    return [round((epoch(s) - base) / 3600) for s in stamps]


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return None
    return xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2])


def launch_features(hourly, v1):
    """(lift, growth) of a launch from its hourly points and its hour-1 viewers.

    hourly maps whole-hour offsets (0 = the day's first hour) to viewers. lift is how far hour 1
    sits above the pre-launch baseline, in log units; growth is hour 1 against the mean of the
    three hours just before the day, in log units. Missing data degrades to 0.0 (neutral).
    """
    base_vals = [v for off, v in hourly.items() if BASELINE_LO <= off < BASELINE_HI and v > 0]
    if len(base_vals) < 4:
        base_vals = [v for off, v in hourly.items() if -336 <= off < BASELINE_HI and v > 0]
    base = median(base_vals)
    lift = math.log(v1 / base) if base and base > 0 and v1 > 0 else 0.0
    recent = [v for off, v in hourly.items() if GROWTH_LO <= off < 0 and v > 0]
    growth = math.log(v1 / (sum(recent) / len(recent))) if recent and v1 > 0 else 0.0
    return lift, growth


def comparable_day(comp):
    """A comparable's hourly viewers keyed by whole-hour offset from its own day start."""
    offsets = hour_offsets(comp["day_start"], [p["from"] for p in comp["hourly"]])
    day = {}
    for off, p in zip(offsets, comp["hourly"]):
        if p.get("viewers"):
            day[off] = float(p["viewers"])
    return day


def target_hourly(case):
    """The case's own hourly viewers by offset: history_hourly when present, else history bucketed."""
    hourly = {}
    rows = case.get("history_hourly") or []
    if rows:
        offsets = hour_offsets(case["day_start"], [p["from"] for p in rows])
        for off, p in zip(offsets, rows):
            if p.get("viewers"):
                hourly[off] = float(p["viewers"])
        return hourly
    buckets = {}
    hist = case.get("history") or []
    if hist:
        offsets = hour_offsets(case["day_start"], [p["at"] for p in hist])
        for off, p in zip(offsets, hist):
            if p.get("viewers"):
                buckets.setdefault(off, []).append(float(p["viewers"]))
        for off, vals in buckets.items():
            hourly[off] = sum(vals) / len(vals)
    return hourly


def weighted_quantile(pairs, tau):
    """Smallest sample whose cumulative weight reaches tau of the total (pairs are (x, w))."""
    pairs.sort()
    total = sum(w for _, w in pairs)
    cum = 0.0
    for x, w in pairs:
        cum += w
        if cum >= tau * total:
            return x
    return pairs[-1][0]


def forecast_case(case):
    """The forecast object for one parsed case: {"hours": [{"hour": h, "q": [5 quantiles]}]}."""
    levels = case.get("levels") or DEFAULT_LEVELS
    first = next((k for k in case.get("known") or [] if k.get("hour") == 1), None)
    p1 = float(first["viewers"]) if first and first.get("viewers") else 1.0
    if p1 < 1.0:
        p1 = 1.0
    t_lift, t_growth = launch_features(target_hourly(case), p1)
    t_level = math.log(p1)

    # Pool the comparables' release-day log-ratio curves, each with its kernel weight.
    pool = []  # (weight, {hour: log ratio to that launch's hour 1})
    for comp in case.get("comparables") or []:
        if "before release" in (comp.get("name") or ""):
            continue  # the target category's own pre-release history is not a launch
        day = comparable_day(comp)
        v1 = day.get(0)
        if not v1 or v1 <= 0:
            continue
        c_lift, c_growth = launch_features(day, v1)
        d2 = ((t_lift - c_lift) / BW_LIFT) ** 2 \
            + ((t_growth - c_growth) / BW_GROWTH) ** 2 \
            + ((t_level - math.log(v1)) / BW_LEVEL) ** 2
        weight = max(math.exp(-0.5 * d2), WEIGHT_FLOOR)
        # day is keyed by offset; hour h of the day is offset h-1, hour 1 is offset 0.
        ratios = {off + 1: math.log(day[off] / v1) for off in day if 1 <= off <= 23 and day[off] > 0}
        if ratios:
            pool.append((weight, ratios))

    hours_wanted = sorted(row["hour"] for row in case.get("forecast") or []) or list(range(2, 25))
    log_q = {}
    for h in hours_wanted:
        pairs = [(r[h], w) for w, r in pool if h in r]
        if pairs:
            log_q[h] = [weighted_quantile(list(pairs), tau) for tau in levels]
        else:
            log_q[h] = [0.0] * len(levels)

    # Light smoothing across neighbouring hours (weights 1-2-1), per quantile level.
    smoothed = {}
    for h in hours_wanted:
        acc = [0.0] * len(levels)
        total_w = 0.0
        for dh, wgt in ((-1, 0.25), (0, 0.5), (1, 0.25)):
            if h + dh in log_q:
                total_w += wgt
                for i in range(len(levels)):
                    acc[i] += wgt * log_q[h + dh][i]
        smoothed[h] = [v / total_w for v in acc]

    rows = []
    for h in hours_wanted:
        qs = []
        for v in smoothed[h]:
            q = p1 * math.exp(max(-12.0, min(12.0, v)))
            q = round2(q)
            q = min(max(q, 0.01), 1_000_000_000)
            if qs and q < qs[-1]:
                q = qs[-1]
            qs.append(q)
        rows.append({"hour": h, "q": qs})
    return {"hours": rows}


def round2(x):
    """x rounded to 2 decimals, half up; whole numbers come back as ints (JSON writes 1240, not 1240.0)."""
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if float(value).is_integer() else value


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
