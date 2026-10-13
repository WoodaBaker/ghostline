"""Goal-drift probe (GI-DRFT-01) — STUB.

Intended method: run the target on a long multi-step task, periodically
ask it to state its current objective, and measure divergence (embedding
similarity) between stated objectives and the original brief. A decaying
similarity curve is the signal. See kiru#509.
"""

from .base import Battery, BatteryResult
from ..targets.base import Budget, Target


class GoalDriftBattery(Battery):
    slug = "goal-drift-trajectory"
    disorder = "GI-DRFT-01"
    description = "Stated-objective divergence over long trajectories."

    def run(self, target: Target, budget: Budget) -> BatteryResult:
        raise NotImplementedError("goal-drift battery not yet implemented (kiru#509)")
