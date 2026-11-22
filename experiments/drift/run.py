#!/usr/bin/env python3
"""Drift toy: single-unit codes change while the similarity matrix holds.

Evidence for PRED-001 in the Kiru Mind registry, which cites this file as
ghostline:experiments/drift/run.py. The model and the pass criteria are
explained in README.md beside it.

    python experiments/drift/run.py                    # seed 0, 30 days
    python experiments/drift/run.py --seed 7 --days 60

Exit codes:
    0  the prediction held
    1  the prediction failed (the FAIL line says which check)
    2  no verdict: bad arguments, or the simulation itself misbehaved

Standard library only, Python 3.10+. Seeded, so the same arguments print the
same numbers.
"""

from __future__ import annotations

import argparse
import math
import random
import statistics
import sys

N_STIMULI = 9
N_UNITS = 50
# Size of each day's re-coding. At 0.04 a unit's tuning is still recognisable
# after one day (r ~0.96) and mostly gone after 30 (r ~0.2-0.4 across seeds).
DAILY_STEP = 0.04
# The control arm's codes grow ~4% a day; far past a year they overflow floats.
MAX_DAYS = 365

# Pass criteria, fixed before running. Change them only on purpose: PRED-001
# rests on these exact thresholds.
#
# r < 0.5 means a unit's day-0 tuning explains under a quarter (r^2) of the
# variance of its tuning now.
MAX_TUNING_R = 0.5
# Round-off in the drift arm is ~1e-16. 1e-9 leaves room for other platforms
# while staying far below anything a real change would produce.
HOLD_TOL = 1e-9
# 1% of the largest distance: well above round-off, small enough that a mild
# relation-breaking change still counts.
BREAK_MIN = 0.01


class InstrumentError(Exception):
    """The simulation misbehaved, so its verdict would mean nothing (exit 2)."""


def dot(u: list[float], v: list[float]) -> float:
    return sum(a * b for a, b in zip(u, v))


def make_codes(rng: random.Random) -> list[list[float]]:
    """Day-0 population code: one row per stimulus, one column per unit.

    Stimuli sit evenly on a circle (like hues or orientations). Each unit has a
    bell-shaped tuning curve around a random preferred angle (baseline 1, peak
    gain 5-15, von Mises width 2), so neighbouring stimuli get similar codes and
    the similarity matrix has real structure to preserve or break.
    """
    angles = [2 * math.pi * k / N_STIMULI for k in range(N_STIMULI)]
    prefs = [rng.uniform(0, 2 * math.pi) for _ in range(N_UNITS)]
    gains = [rng.uniform(5, 15) for _ in range(N_UNITS)]
    return [
        [1 + g * math.exp(2 * (math.cos(a - p) - 1)) for p, g in zip(prefs, gains)]
        for a in angles
    ]


def step_matrix(rng: random.Random) -> list[list[float]]:
    """One day's raw re-coding: I + DAILY_STEP * G, with G standard normal."""
    return [
        [(r == c) + DAILY_STEP * rng.gauss(0, 1) for c in range(N_UNITS)]
        for r in range(N_UNITS)
    ]


def orthonormalize(m: list[list[float]]) -> list[list[float]]:
    """The orthogonal matrix Gram-Schmidt makes from m's columns.

    m is close to the identity, so the result is too: each day is a small
    rotation of the code, not a full scramble.
    """
    qs: list[list[float]] = []
    for c in range(N_UNITS):
        v = [m[r][c] for r in range(N_UNITS)]
        for q in qs:  # modified Gram-Schmidt: project out of the updated v
            p = dot(q, v)
            v = [vi - p * qi for vi, qi in zip(v, q)]
        norm = math.sqrt(dot(v, v))
        if norm < 1e-12:
            raise InstrumentError(
                f"column {c} of the day's matrix is degenerate "
                f"(norm {norm:.1e} after projection)"
            )
        qs.append([x / norm for x in v])

    # Check rather than trust: a Q that isn't orthogonal would make the drift
    # arm fail and pass off a bug as a refuted prediction.
    worst = max(
        abs(dot(qs[i], qs[j]) - (i == j))
        for i in range(N_UNITS)
        for j in range(i, N_UNITS)
    )
    if worst > 1e-12:
        raise InstrumentError(
            f"Gram-Schmidt result is not orthogonal: max |Q^T Q - I| = {worst:.1e}"
        )
    return [[qs[c][r] for c in range(N_UNITS)] for r in range(N_UNITS)]


def recode(codes: list[list[float]], a: list[list[float]]) -> list[list[float]]:
    """Apply y = a x to every stimulus's code x."""
    return [[dot(row, x) for row in a] for x in codes]


def distances(codes: list[list[float]]) -> list[list[float]]:
    """The similarity matrix: Euclidean distance between every pair of codes."""
    return [[math.dist(x, y) for y in codes] for x in codes]


def matrix_change(d: list[list[float]], d0: list[list[float]]) -> float:
    """Largest change in any distance, relative to the largest day-0 distance."""
    scale = max(max(row) for row in d0)
    worst = max(abs(a - b) for row, row0 in zip(d, d0) for a, b in zip(row, row0))
    return worst / scale


def tuning_r(codes0: list[list[float]], codes: list[list[float]]) -> float:
    """Mean over units of corr(tuning curve on day 0, tuning curve now).

    A unit's tuning curve is its response to each stimulus: one column of the
    codes. 1 means every unit kept its tuning; ~0 means none did.
    """
    rs = []
    for u in range(N_UNITS):
        before = [x[u] for x in codes0]
        after = [x[u] for x in codes]
        try:
            rs.append(statistics.correlation(before, after))
        except statistics.StatisticsError as e:
            raise InstrumentError(
                f"unit {u} has a flat tuning curve, so its "
                f"correlation is undefined: {e}"
            ) from e
    return statistics.fmean(rs)


def code_moved(codes0: list[list[float]], codes: list[list[float]]) -> float:
    """How far the codes moved, relative to their size on day 0."""
    moved = sum((a - b) ** 2 for x, x0 in zip(codes, codes0) for a, b in zip(x, x0))
    size = sum(a * a for x0 in codes0 for a in x0)
    return math.sqrt(moved / size)


def preferred(codes: list[list[float]], u: int) -> int:
    """The stimulus unit u responds to most."""
    return max(range(N_STIMULI), key=lambda s: codes[s][u])


def run(seed: int, days: int) -> bool:
    """Simulate both arms, print the numbers, and return whether PRED-001 held."""
    rng = random.Random(seed)
    codes0 = make_codes(rng)
    d0 = distances(codes0)
    drift = control = codes0
    worst_hold = 0.0  # drift arm: the largest matrix change on any day
    least_break = math.inf  # control arm: the smallest matrix change on any day

    print(
        f"PRED-001 drift toy: seed {seed}, {days} day{'s' * (days != 1)}, "
        f"{N_STIMULI} stimuli, "
        f"{N_UNITS} units, daily step {DAILY_STEP}"
    )
    print()
    print("       drift arm: orthogonal           control arm: same draw, not")
    print("  day  tuning r  code moved  matrix    tuning r  code moved  matrix")
    row = "{:>5}  {:>8.3f}  {:>10.3f}  {:>7.1e}   {:>8.3f}  {:>10.3f}  {:>7.3f}"
    print(row.format(0, 1, 0, 0, 1, 0, 0))

    for day in range(1, days + 1):
        m = step_matrix(rng)
        drift = recode(drift, orthonormalize(m))
        control = recode(control, m)
        hold = matrix_change(distances(drift), d0)
        broke = matrix_change(distances(control), d0)
        if not (math.isfinite(hold) and math.isfinite(broke)):
            raise InstrumentError(
                f"day {day}: a matrix change is not finite "
                f"(drift {hold}, control {broke})"
            )
        worst_hold = max(worst_hold, hold)
        least_break = min(least_break, broke)
        if day == 1 or day % 5 == 0 or day == days:
            print(
                row.format(
                    day,
                    tuning_r(codes0, drift),
                    code_moved(codes0, drift),
                    hold,
                    tuning_r(codes0, control),
                    code_moved(codes0, control),
                    broke,
                )
            )

    final_r = tuning_r(codes0, drift)
    switched = sum(preferred(codes0, u) != preferred(drift, u) for u in range(N_UNITS))
    checks = [
        (
            final_r < MAX_TUNING_R,
            (
                f"codes changed: mean tuning r, day 0 vs day {days}, is {final_r:.3f} "
                f"(needs < {MAX_TUNING_R}); {switched} of {N_UNITS} units now prefer "
                f"a different stimulus"
            ),
        ),
        (
            worst_hold < HOLD_TOL,
            (
                f"structure held: the drift arm's matrix moved at most "
                f"{worst_hold:.1e} on any day (needs < {HOLD_TOL:.0e})"
            ),
        ),
        (
            least_break > BREAK_MIN,
            (
                f"control broke it: the control arm's matrix moved at least "
                f"{least_break:.3f} on every day (needs > {BREAK_MIN})"
            ),
        ),
    ]
    print()
    for ok, text in checks:
        print(("PASS  " if ok else "FAIL  ") + text)
    held = all(ok for ok, _ in checks)
    print(
        "RESULT: PASS, PRED-001 held" if held else "RESULT: FAIL, PRED-001 did not hold"
    )
    return held


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Drift toy: codes change, similarity matrix holds (PRED-001)."
    )
    parser.add_argument(
        "--seed", type=int, default=0, help="random seed, 0 or more (default 0)"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help=f"days of drift, 1 to {MAX_DAYS} (default 30)",
    )
    args = parser.parse_args(argv)
    # parser.error exits 2, matching "no verdict".
    if args.seed < 0:
        # random.Random(-n) is the same stream as Random(n); refuse the alias.
        parser.error(f"--seed must be 0 or more, got {args.seed}")
    if not 1 <= args.days <= MAX_DAYS:
        parser.error(f"--days must be 1 to {MAX_DAYS}, got {args.days}")

    try:
        held = run(args.seed, args.days)
    except InstrumentError as e:
        print(f"run.py: no verdict, the simulation misbehaved: {e}", file=sys.stderr)
        return 2
    return 0 if held else 1


if __name__ == "__main__":
    sys.exit(main())
