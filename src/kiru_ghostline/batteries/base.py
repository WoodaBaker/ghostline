"""Battery interface: one probe battery per disorder.

A Battery encodes the diagnostic method for a single DEM-X disorder:
what to ask the target, how to score the responses, and what counts as
a signal. Batteries are independent -- a run selects any subset.
"""

import abc
from dataclasses import dataclass, field


@dataclass
class BatteryResult:
    battery: str
    disorder: str
    score: float  # 0..1 -- higher means a stronger disorder signal
    calls: int
    passed: bool  # True when score is below the signal threshold
    details: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "battery": self.battery,
            "disorder": self.disorder,
            "score": self.score,
            "calls": self.calls,
            "passed": self.passed,
            "details": self.details,
        }


class Battery(abc.ABC):
    """One diagnostic battery. Subclass and implement run()."""

    slug: str  # e.g. "sycophancy-flip"
    disorder: str  # e.g. "GI-SYCO-01"
    description: str = ""
    signal_threshold: float = 0.5  # score >= threshold means signal detected

    @abc.abstractmethod
    def run(self, target, budget) -> BatteryResult:
        """Probe the target and return a scored result."""
