"""Findings: the disorder documentation format.

A Finding is what Ghostline produces when it observes a failure pattern
worth recording — whether it matches a known disorder or is a novelty
candidate. The format is the contract with kiru: `ghostline report
--upload` posts this JSON to the kiru API, where it enters the DEM-X
lifecycle as an Anomaly candidate (opt-in only).

The mechanistic_evidence field is reserved from day one (see kiru#509):
behavioral evidence now, internals later.
"""

import json
import uuid
from dataclasses import asdict, dataclass, field


@dataclass
class Finding:
    observed_behavior: str
    model: str = ""
    scaffolding: str = ""
    repeatability: str = ""  # e.g. "4/5 runs"
    suspected_disorder: str | None = None
    battery_scores: list[dict] = field(default_factory=list)
    telemetry_excerpts: list[str] = field(default_factory=list)
    mechanistic_evidence: dict | None = None  # reserved for future use
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "Finding":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})
