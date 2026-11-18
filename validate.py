"""Local validation for the GTA VI Twitch CCU forecaster (not used by the grader).

Two evaluations, both scored with the contest's own rule - the mean pinball loss on the log scale,
2 * max(tau * d, (tau - 1) * d) with d = ln(y) - ln(q), over every scored hour and level:

1. Practice cases p00..p03 from the competition kit. The kit's case files stop at the end of hour 1,
   so the actual hours 2..24 come from practice_actuals.json beside this script: the same SullyGnome
   hourly averages the kit was built from, re-fetched from SullyGnome's public chart API (the URLs
   in the kit's input/NOTICE.txt) on 2026-11-18. Cross-checks: the re-fetched series reproduce every
   history point and every hour-1 print in the kit's cases exactly, and scoring the kit's starter
   (the house persistence baseline) against them reproduces the house's published practice loss of
   0.387 - see VALIDATION.md.

2. Leave-one-out over the comparables: each comparable launch in turn plays the target, forecast
   from the remaining pool with the same code path the entry uses (its own history truncated at its
   checkpoint, its own hour 1 as the known print), and is scored against its real release day.

Usage: python3 validate.py [kit_input_dir]   (default: $MAKEFUN_KIT_INPUT or ./input)
"""

import importlib.util
import json
import math
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]

spec = importlib.util.spec_from_file_location("entry", HERE / "main.py")
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


def pinball(y, q, tau):
    d = math.log(max(y, 1.0)) - math.log(q)
    return 2.0 * max(tau * d, (tau - 1.0) * d)


def score(forecast_rows, actual_day):
    total, n = 0.0, 0
    miss, nh, cov = 0.0, 0, 0
    by_hour = {row["hour"]: row["q"] for row in forecast_rows}
    for h, y in actual_day.items():
        if h == 1 or h not in by_hour:
            continue
        qs = by_hour[h]
        for tau, q in zip(LEVELS, qs):
            total += pinball(y, q, tau)
            n += 1
        miss += abs(math.log(max(y, 1.0)) - math.log(qs[2]))
        nh += 1
        cov += 1 if qs[0] <= y <= qs[-1] else 0
    return total / n, 100.0 * (math.exp(miss / nh) - 1.0), cov / nh


def baseline_rows(p1):
    """The house persistence baseline (the kit's starter), as forecast rows."""
    p1 = max(1.0, p1)
    rows = []
    for h in range(2, 25):
        rows.append({"hour": h, "q": [entry.round2(p1 * math.exp(z * 0.15 * math.sqrt(h - 1))) for z in Z]})
    return rows


def check_shape(rows):
    assert len(rows) == 23, f"expected 23 rows, got {len(rows)}"
    assert sorted(r["hour"] for r in rows) == list(range(2, 25)), "hours must be 2..24 each once"
    for r in rows:
        assert set(r.keys()) == {"hour", "q"}, f"bad row keys {r.keys()}"
        assert len(r["q"]) == 5 and all(0 < q <= 1e9 for q in r["q"]), f"bad q {r['q']}"
        assert all(b >= a for a, b in zip(r["q"], r["q"][1:])), f"q not non-decreasing {r['q']}"


def main():
    input_dir = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("MAKEFUN_KIT_INPUT", "input"))
    actuals = {pid: {int(h): v for h, v in d.items()}
               for pid, d in json.loads((HERE / "practice_actuals.json").read_text()).items()}
    cases = {}
    for pid in ["p00", "p01", "p02", "p03"]:
        cases[pid] = json.loads((input_dir / f"{pid}.in").read_text())

    print("== practice cases (actuals: SullyGnome hourly averages, see header) ==")
    print(f"{'case':6s} {'this entry':>12s} {'baseline':>10s} {'miss%':>7s} {'cover90':>8s} {'run s':>6s}")
    tot_e, tot_b, tn = 0.0, 0.0, 0
    for pid, case in cases.items():
        t0 = time.perf_counter()
        rows = entry.forecast_case(case)["hours"]
        dt = time.perf_counter() - t0
        check_shape(rows)
        again = entry.forecast_case(case)["hours"]
        assert json.dumps(again) == json.dumps(rows), "forecast is not deterministic"
        loss_e, miss, cov = score(rows, actuals[pid])
        loss_b, _, _ = score(baseline_rows(case["known"][0]["viewers"]), actuals[pid])
        n = 23 * 5
        tot_e += loss_e * n
        tot_b += loss_b * n
        tn += n
        print(f"{pid:6s} {loss_e:12.6f} {loss_b:10.6f} {miss:7.1f} {cov:8.3f} {dt:6.2f}")
    print(f"{'MEAN':6s} {tot_e / tn:12.6f} {tot_b / tn:10.6f}")

    print("\n== leave-one-out over the comparables of p01 (37 launches with full days) ==")
    case = cases["p01"]
    pool = [c for c in case["comparables"] if "before release" not in c["name"]]
    tot_e, tot_b, tn = 0.0, 0.0, 0
    for i, comp in enumerate(pool):
        day = entry.comparable_day(comp)
        if not day.get(0) or len([o for o in day if 0 <= o <= 23]) < 20:
            continue
        synth = {
            "levels": LEVELS,
            "day_start": comp["day_start"],
            "known": [{"hour": 1, "viewers": day[0]}],
            "forecast": [{"hour": h} for h in range(2, 25)],
            "history_hourly": [  # truncated at the checkpoint, as a real case is
                {"from": p["from"], "viewers": p["viewers"], "channels": p.get("channels")}
                for p, off in zip(comp["hourly"],
                                  entry.hour_offsets(comp["day_start"], [q["from"] for q in comp["hourly"]]))
                if off <= 0
            ],
            "comparables": pool[:i] + pool[i + 1:],
        }
        actual = {off + 1: day[off] for off in day if 0 <= off <= 23}
        loss_e, _, _ = score(entry.forecast_case(synth)["hours"], actual)
        loss_b, _, _ = score(baseline_rows(day[0]), actual)
        n = (len(actual) - 1) * 5
        tot_e += loss_e * n
        tot_b += loss_b * n
        tn += n
    print(f"this entry {tot_e / tn:.6f}   baseline {tot_b / tn:.6f}   over {tn} items")


if __name__ == "__main__":
    main()
