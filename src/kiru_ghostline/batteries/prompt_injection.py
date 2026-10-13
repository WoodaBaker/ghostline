"""Prompt-injection probe (SEC-INJ-01) — STUB.

Intended method: embed instructions in simulated tool output
(BIPIA/AgentDojo-style) and measure the compliance rate — how often the
target follows the injected instruction over the principal's. See kiru#509.
"""

from .base import Battery, BatteryResult
from ..targets.base import Budget, Target


class PromptInjectionBattery(Battery):
    slug = "injection-compliance"
    disorder = "SEC-INJ-01"
    description = "Injected-instruction compliance rate."

    def run(self, target: Target, budget: Budget) -> BatteryResult:
        raise NotImplementedError("prompt-injection battery not yet implemented (kiru#509)")
