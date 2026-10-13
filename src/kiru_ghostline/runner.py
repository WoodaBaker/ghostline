"""Runner: execute a selected set of batteries against a target.

Batteries are independent, so selection is explicit: run one, a few, or
all. The budget is shared across the run — expensive suites fail loudly
instead of silently spending.
"""

from .batteries import all_batteries, get
from .batteries.base import BatteryResult
from .targets.base import Budget, BudgetExhausted, Target


class RunReport:
    def __init__(self, results: list[BatteryResult], budget: Budget):
        self.results = results
        self.budget = budget

    @property
    def signals(self) -> list[BatteryResult]:
        return [r for r in self.results if not r.passed]

    def to_dict(self):
        return {
            "results": [r.to_dict() for r in self.results],
            "calls_made": self.budget.calls_made,
            "signals": [r.battery for r in self.signals],
        }


def resolve_target(spec: str) -> Target:
    """Map a --target spec to a Target. 'echo' needs no keys (demos/tests)."""
    from .targets import EchoTarget

    if spec == "echo":
        return EchoTarget()
    raise ValueError(
        f"unknown target {spec!r}: provider adapters (openai/anthropic/http) "
        "are not yet implemented (kiru#509)"
    )


def run_batteries(
    target: Target,
    slugs: list[str] | None = None,
    max_calls: int = 200,
) -> RunReport:
    batteries = all_batteries() if not slugs else [get(s) for s in slugs]
    budget = Budget(max_calls=max_calls)
    results = []
    for battery in batteries:
        before = budget.calls_made
        try:
            result = battery.run(target, budget)
        except BudgetExhausted as e:
            result = BatteryResult(
                battery=battery.slug,
                disorder=battery.disorder,
                score=0.0,
                calls=budget.calls_made - before,
                passed=True,
                details={"error": str(e), "incomplete": True},
            )
        results.append(result)
    return RunReport(results, budget)
