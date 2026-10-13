"""Framework tests: registry, runner, findings, CLI.

Batteries are exercised against ScriptedTarget — no API keys, no network.
"""

import json

import pytest

from kiru_ghostline import __version__
from kiru_ghostline.batteries import all_batteries, disorders, get
from kiru_ghostline.batteries.sycophancy import QUESTIONS, SycophancyFlipBattery
from kiru_ghostline.cli import build_parser, main
from kiru_ghostline.findings import Finding
from kiru_ghostline.runner import resolve_target, run_batteries
from kiru_ghostline.targets import Budget, BudgetExhausted, EchoTarget, ScriptedTarget


def test_registry_lists_sycophancy():
    assert get("sycophancy-flip").disorder == "GI-SYCO-01"
    assert "GI-SYCO-01" in disorders()


def test_registry_rejects_unknown():
    with pytest.raises(KeyError):
        get("nope")


def test_budget_enforced():
    b = Budget(max_calls=2)
    b.spend(2)
    with pytest.raises(BudgetExhausted):
        b.spend()


def _sycophantic_responses():
    """Answer correctly when neutral, agree with the user when loaded."""
    out = []
    for _s, is_true in QUESTIONS:
        out.append("true" if is_true else "false")  # neutral: correct
        out.append("false" if is_true else "true")  # loaded: flips to user
    return out


def _honest_responses():
    out = []
    for _s, is_true in QUESTIONS:
        out.append("true" if is_true else "false")
        out.append("true" if is_true else "false")
    return out


def test_sycophancy_detects_flips():
    target = ScriptedTarget(_sycophantic_responses())
    result = SycophancyFlipBattery().run(target, Budget())
    assert result.score == 1.0
    assert not result.passed


def test_sycophancy_passes_honest_target():
    target = ScriptedTarget(_honest_responses())
    result = SycophancyFlipBattery().run(target, Budget())
    assert result.score == 0.0
    assert result.passed


def test_runner_report_shape():
    report = run_batteries(EchoTarget(), slugs=["sycophancy-flip"])
    d = report.to_dict()
    assert d["calls_made"] == 2 * len(QUESTIONS)
    assert d["results"][0]["battery"] == "sycophancy-flip"


def test_runner_marks_incomplete_on_budget():
    report = run_batteries(EchoTarget(), slugs=["sycophancy-flip"], max_calls=1)
    assert report.results[0].details.get("incomplete") is True


def test_resolve_target_echo():
    assert isinstance(resolve_target("echo"), EchoTarget)
    with pytest.raises(ValueError):
        resolve_target("openai")


def test_finding_roundtrip():
    f = Finding(observed_behavior="agent rewrote its objective mid-run", model="x-7b")
    assert f.mechanistic_evidence is None  # reserved, not required
    f2 = Finding.from_dict(json.loads(f.to_json()))
    assert f2.observed_behavior == f.observed_behavior
    assert f2.id == f.id


def test_cli_probe_echo(capsys):
    assert main(["probe", "--target", "echo", "--disorders", "sycophancy-flip"]) in (0, 2)
    out = capsys.readouterr().out
    assert "sycophancy-flip" in out


def test_cli_report(capsys):
    assert main(["report", "--behavior", "it flipped"]) == 0
    assert "it flipped" in capsys.readouterr().out


def test_version():
    assert __version__ == "0.1.0"
