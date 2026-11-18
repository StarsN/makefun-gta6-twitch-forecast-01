# Validation results

Scorer (the contest's own rule): for each scored hour *h* and level τ, pinball loss
`2 · max(τ·d, (τ−1)·d)` with `d = ln(y) − ln(q)`; the loss is the mean over all items.
Lower is better. "Baseline" is the house persistence baseline (the kit's starter): every hour
stays at hour 1's print, spread `exp(z_τ · 0.15 · sqrt(h−1))`.

## 1. Practice cases (the kit's p00–p03)

Actuals: the launches' real hours 2–24 (SullyGnome hourly averages — provenance and cross-checks
in the header of `validate.py`; scoring the kit's starter against these actuals reproduces the
house's published practice loss 0.387, and this entry's table below uses the same actuals).

| case | launch | this entry | baseline | typical miss | 90% coverage |
|------|--------|-----------:|---------:|-------------:|-------------:|
| p00 | Marvel's Wolverine | 0.262464 | 0.743671 | 53.9% | 0.957 |
| p01 | Red Dead Redemption 2 | 0.151645 | 0.286813 | 15.8% | 1.000 |
| p02 | God of War Ragnarök | 0.199335 | 0.214579 | 32.5% | 1.000 |
| p03 | Marvel's Spider-Man 2 | 0.244227 | 0.303324 | 32.9% | 0.826 |
| **mean** | | **0.214418** | **0.387097** | | |

The entry's mean practice loss is **44.6% below** the house baseline's. Wolverine (p00) is the
hardest case for everyone: its US unlock came at 04:00Z, so hour 1 (23,357 viewers) precedes a
roughly tenfold ramp — the kernel finds its true neighbours (Ghost of Yōtei, Resident Evil
Requiem — rolling console launches with the same still-building wave) but the day out-ramps even
them.

## 2. Leave-one-out over the comparables

Each of the 37 comparable launches with a full release day in p01's pool plays the target in
turn: its history is truncated at its own checkpoint, its hour 1 becomes the known print, and it
is forecast from the other 36 through the identical code path, then scored against its real day.
This pool is deliberately harsher than the practice set — it includes simultaneous-global
unlocks whose hour 1 is a near-zero baseline before a ×100–×2000 ramp (Silksong, Kingdom Come:
Deliverance II, HELLDIVERS 2), which no hour-1 forecaster can fully see coming.

| | this entry | baseline |
|---|---:|---:|
| mean pinball loss (4,255 items) | **0.476177** | 0.929650 |

**48.8% below** the baseline on the same items.

## 3. Mechanics

- Determinism: `validate.py` asserts two runs of `forecast_case` on each practice case produce
  identical JSON; end-to-end runs of `main.py` over the kit input were also compared byte for
  byte (identical, ~1.5 KB per output file, cap 65,536).
- Speed: ~0.03 s per case (cap 8 s), including parsing the ~1 MB case file.
- Edge cases exercised: no comparables; no history; `history`-only (bucketed fallback);
  hour-1 viewers 0, 3, and 9·10⁸ (output cap 1e9 respected); all comparable viewers zeroed;
  a single comparable; missing `levels`. Every case still yields 23 rows × 5 finite,
  non-decreasing quantiles in (0, 1e9].
