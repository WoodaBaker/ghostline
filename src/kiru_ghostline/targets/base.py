"""Target interface: anything Ghostline can probe.

A Target is where the agent lives -- an enterprise API, an open-weights
endpoint, or a scripted stand-in for tests. Batteries only ever speak to
a Target, never to a provider SDK directly, so keys and spend stay local.
"""

import abc


class BudgetExhausted(RuntimeError):
    """Raised when a run exceeds its model-call budget."""


class Budget:
    """Model-call budget for a single run. Batteries must spend per call."""

    def __init__(self, max_calls: int = 200):
        if max_calls < 1:
            raise ValueError("max_calls must be >= 1")
        self.max_calls = max_calls
        self.calls_made = 0

    def spend(self, n: int = 1) -> None:
        if self.calls_made + n > self.max_calls:
            raise BudgetExhausted(
                f"budget exhausted: {self.calls_made + n} > {self.max_calls} calls"
            )
        self.calls_made += n


class Target(abc.ABC):
    """Something that produces agent output given a prompt."""

    name: str = "target"

    @abc.abstractmethod
    def complete(self, prompt: str, budget: Budget, **kwargs) -> str:
        """Return the agent's response to a single prompt.

        Must call budget.spend() once per underlying model call.
        """
