# Drift toy

A population of 50 units codes 9 stimuli. Every simulated day the code is
re-coded. The script checks one prediction: when each day's re-coding preserves
distances, single units change their tuning while the 9×9 matrix of distances
between stimulus codes stays the same. A control arm, re-coded by a matching
change that does not preserve distances, must change the matrix.

    python experiments/drift/run.py                    # seed 0, 30 days
    python experiments/drift/run.py --seed 7 --days 60

Standard library only, Python 3.10+, about 0.3 s. Seeded: the same arguments
print the same numbers.

## Why it's here

Kiru Mind's PRED-001 cites this file as its evidence
(`ghostline:experiments/drift/run.py`) and reads only the exit code. Moving the
file or changing its pass criteria changes what that entry rests on.
`tests/test_drift_experiment.py` runs it in CI so it stays passing.

The measurement itself (did the code change, did the relational structure
change) is a drift signal Ghostline can later apply to model representations.

## Model

- **Stimuli:** 9 points evenly spaced on a circle, like hues or orientations.
- **Day-0 codes:** each unit has a bell-shaped tuning curve around a random
  preferred angle, so neighbouring stimuli get similar codes and the distance
  matrix has real structure.
- **Each day:** draw `M = I + 0.04 G`, with `G` a 50×50 standard normal matrix.
  - Drift arm: `Q` = Gram-Schmidt of `M`, an orthogonal matrix close to `I`.
    Every code `x` becomes `Q x`.
  - Control arm: every code `x` becomes `M x`. Same random draw, without the
    constraint.

The two arms take the same step. On day 1 at seed 0 they move the codes by
26% and 25%, so a difference in the matrix comes from the constraint, not from
step size. After day 1 the control's codes also grow in size, which is why its
matrix keeps moving further.

## Pass criteria

Fixed in `run.py` before running.

| Check            | Measure                                                                                              | Pass if |
| ---------------- | ---------------------------------------------------------------------------------------------------- | ------- |
| codes changed    | mean over units of the correlation between a unit's tuning curve on day 0 and on the last day        | < 0.5   |
| structure held   | drift arm: the largest change in any distance, relative to the largest day-0 distance, on any day    | < 1e-9  |
| control broke it | control arm: the same measure, smallest over all days                                                | > 0.01  |

A correlation under 0.5 means day-0 tuning explains under a quarter of the
variance of a unit's tuning now. Round-off in the drift arm is about 1e-16, so
1e-9 leaves wide room for other platforms while sitting far below the
control's smallest change.

## Exit codes

| Code | Meaning                                                                          |
| ---- | -------------------------------------------------------------------------------- |
| 0    | the prediction held                                                              |
| 1    | the prediction failed; the `FAIL` line says which check                          |
| 2    | no verdict: bad arguments, or the simulation misbehaved (for example, a re-coding that should be orthogonal isn't) |

`--days 1` exits 1: after one day units still keep most of their tuning
(r = 0.96). That is the quickest way to see the script fail.

## Result

Seed 0, 30 days:

```
  day  tuning r  code moved  matrix    tuning r  code moved  matrix
    0     1.000       0.000  0.0e+00      1.000       0.000    0.000
    1     0.961       0.264  1.3e-16      0.962       0.254    0.056
    5     0.785       0.602  1.3e-16      0.843       0.749    0.261
   10     0.586       0.924  1.3e-16      0.707       1.099    0.556
   15     0.461       1.073  1.3e-16      0.518       1.362    0.945
   20     0.291       1.162  2.5e-16      0.452       1.714    1.097
   25     0.342       1.158  2.5e-16      0.430       2.010    1.453
   30     0.210       1.178  2.5e-16      0.380       2.547    1.670

PASS  codes changed: mean tuning r, day 0 vs day 30, is 0.210 (needs < 0.5); 39 of 50 units now prefer a different stimulus
PASS  structure held: the drift arm's matrix moved at most 3.8e-16 on any day (needs < 1e-09)
PASS  control broke it: the control arm's matrix moved at least 0.056 on every day (needs > 0.01)
RESULT: PASS, PRED-001 held
```

Seeds 0 to 19 all pass. Day-30 tuning r ranged from 0.15 to 0.40, the drift
arm's matrix moved at most 4.5e-16, and the control arm's moved at least 0.032.
The smallest values (the `e-16` column) may differ in the last digits on other
platforms. The verdict does not.

## What a pass does and doesn't show

- The re-codings are orthogonal by construction, so the drift arm is a numerical
  check of a theorem: orthogonal maps preserve distances. What the run adds is
  an instrument that separates relation-preserving from relation-breaking
  change at matched step sizes, plus numbers for how far the code moved.
- Rotations happen about the origin, so "firing rates" go negative. Real
  neurons can't.
- Real drift isn't exactly orthogonal. How close it comes is an empirical
  question this toy doesn't touch.
