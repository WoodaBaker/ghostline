"""Scripted and echo targets for tests and demos (no API keys needed)."""

from .base import Budget, Target


class EchoTarget(Target):
    """Repeats the prompt back. Useful for smoke-testing the runner."""

    name = "echo"

    def complete(self, prompt: str, budget: Budget, **kwargs) -> str:
        budget.spend()
        return prompt


class ScriptedTarget(Target):
    """Returns canned responses in order, then repeats the last one."""

    def __init__(self, responses, name="scripted"):
        self.responses = list(responses)
        self.name = name
        self.seen_prompts = []

    def complete(self, prompt: str, budget: Budget, **kwargs) -> str:
        budget.spend()
        self.seen_prompts.append(prompt)
        if len(self.seen_prompts) <= len(self.responses):
            return self.responses[len(self.seen_prompts) - 1]
        return self.responses[-1]
