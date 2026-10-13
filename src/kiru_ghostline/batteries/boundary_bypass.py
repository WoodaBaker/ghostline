"""Boundary-bypass probe (SEC-BYP-01) -- STUB.

Intended method: standard safety red-team battery (HarmBench-style
refusal tests). Measures refusal rate on disallowed requests, including
common jailbreak framings. See kiru#509.
"""

from ..targets.base import Budget, Target
from .base import Battery, BatteryResult


class BoundaryBypassBattery(Battery):
    slug = "refusal-rate"
    disorder = "SEC-BYP-01"
    description = "Refusal rate under red-team framings."

    def run(self, target: Target, budget: Budget) -> BatteryResult:
        raise NotImplementedError(
            "boundary-bypass battery not yet implemented (kiru#509)"
        )
