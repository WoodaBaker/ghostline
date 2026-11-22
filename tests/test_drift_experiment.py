"""Tests for experiments/drift/run.py.

Kiru Mind's PRED-001 cites that script as evidence and reads only its exit
code, so these tests pin the contract: 0 when the prediction holds, 1 when it
fails, 2 when there is no verdict. Running them in CI keeps the evidence
passing on every change to this repo.
"""

import importlib.util
import random
import subprocess
import sys
from pathlib import Path

import pytest

RUN = Path(__file__).resolve().parent.parent / "experiments" / "drift" / "run.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(RUN), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def load_module():
    spec = importlib.util.spec_from_file_location("drift_run", RUN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_run_passes_and_repeats_exactly():
    first, second = run(), run()
    assert first.returncode == 0, first.stdout + first.stderr
    assert "RESULT: PASS" in first.stdout
    assert first.stdout == second.stdout


@pytest.mark.parametrize("seed", ["1", "2", "3", "4"])
def test_holds_for_other_seeds(seed):
    # A pass at one seed only could be luck; the prediction should not be.
    proc = run("--seed", seed)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_one_day_of_drift_fails_the_codes_changed_check():
    # Shows the script can fail: after one day units still keep their tuning.
    proc = run("--days", "1")
    assert proc.returncode == 1
    assert "FAIL  codes changed" in proc.stdout
    assert "PASS  structure held" in proc.stdout
    assert "RESULT: FAIL" in proc.stdout


@pytest.mark.parametrize(
    "args, message",
    [
        (["--days", "0"], "--days must be 1 to 365, got 0"),
        (["--days", "366"], "--days must be 1 to 365, got 366"),
        (["--seed", "-1"], "--seed must be 0 or more, got -1"),
        (["--seed", "x"], "invalid int value: 'x'"),
    ],
)
def test_bad_arguments_give_no_verdict(args, message):
    proc = run(*args)
    assert proc.returncode == 2
    assert message in proc.stderr


def test_degenerate_day_matrix_is_an_instrument_error():
    drift = load_module()
    n = drift.N_UNITS
    m = [[float(r == c) for c in range(n)] for r in range(n)]
    for r in range(n):
        m[r][1] = m[r][0]  # two equal columns: no orthogonal matrix from these
    with pytest.raises(drift.InstrumentError, match="column 1"):
        drift.orthonormalize(m)


def test_orthonormalize_returns_an_orthogonal_matrix():
    drift = load_module()
    q = drift.orthonormalize(drift.step_matrix(random.Random(0)))
    n = drift.N_UNITS
    for i in range(n):
        for j in range(n):
            col_dot = sum(q[r][i] * q[r][j] for r in range(n))
            assert abs(col_dot - (i == j)) < 1e-12
