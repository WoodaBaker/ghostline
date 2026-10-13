"""Context-corruption probe (MEM-COR-01) -- STUB.

Intended method: place the critical instruction at varying positions in
a long context (start / middle / end) and measure recall as a function of
position. A U-shaped (lost-in-the-middle) degradation curve is the signal.
See kiru#509.
"""

from ..targets.base import Budget, Target
from .base import Battery, BatteryResult


class ContextCorruptionBattery(Battery):
    slug = "context-position-curve"
    disorder = "MEM-COR-01"
    description = "Instruction recall vs context position."

    def run(self, target: Target, budget: Budget) -> BatteryResult:
        raise NotImplementedError(
            "context-corruption battery not yet implemented (kiru#509)"
        )
