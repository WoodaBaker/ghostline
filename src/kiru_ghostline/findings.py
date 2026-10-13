"""Findings: the disorder documentation format.

A Finding is what Ghostline produces when it observes a failure pattern
worth recording -- whether it matches a known disorder or is a novelty
candidate. The format is the contract with kiru: `ghostline report
--upload` posts this JSON to the kiru API, where it enters the DEM-X
lifecycle as an Anomaly candidate (opt-in only).

The mechanistic_evidence field is reserved from day one (see kiru#509):
behavioral evidence now, internals later.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .schema import Event

SCHEMA_VERSION = "ghostline.v1"

_REPEATABILITY_PATTERN = re.compile(r"^(\d+)/(\d+)")


def _parse_repeatability_string(s: str) -> float | None:
    """Convert legacy repeatability strings like '4/5 runs' to fraction."""
    match = _REPEATABILITY_PATTERN.match(s.strip())
    if match:
        numerator = int(match.group(1))
        denominator = int(match.group(2))
        if denominator > 0:
            return numerator / denominator
    return None


@dataclass
class Finding:
    """A documented finding of agent misbehavior.

    Required fields: observed_behavior, catalog_version.
    Optional: model, scaffolding, repeatability, battery_scores,
    telemetry_excerpts, diagnosis_id, suspected_disorder, mechanistic_evidence.
    """

    observed_behavior: str
    catalog_version: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    schema_version: str = SCHEMA_VERSION
    model: str = ""
    scaffolding: str | None = None
    repeatability: float | None = None
    suspected_disorder: str | None = None
    battery_scores: dict[str, Any] = field(default_factory=dict)
    telemetry_excerpts: list[Any] = field(default_factory=list)
    diagnosis_id: str | None = None
    mechanistic_evidence: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "schema_version": self.schema_version,
            "observed_behavior": self.observed_behavior,
            "catalog_version": self.catalog_version,
        }
        if self.model:
            result["model"] = self.model
        if self.scaffolding is not None:
            result["scaffolding"] = self.scaffolding
        if self.repeatability is not None:
            result["repeatability"] = self.repeatability
        if self.suspected_disorder is not None:
            result["suspected_disorder"] = self.suspected_disorder
        if self.battery_scores:
            result["battery_scores"] = self.battery_scores
        if self.telemetry_excerpts:
            result["telemetry_excerpts"] = [
                e.to_dict() if hasattr(e, "to_dict") else e
                for e in self.telemetry_excerpts
            ]
        if self.diagnosis_id is not None:
            result["diagnosis_id"] = self.diagnosis_id
        if self.mechanistic_evidence is not None:
            result["mechanistic_evidence"] = self.mechanistic_evidence
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Finding:
        if "observed_behavior" not in data:
            raise ValueError("Finding missing required field 'observed_behavior'")
        if "catalog_version" not in data:
            raise ValueError("Finding missing required field 'catalog_version'")

        repeatability = data.get("repeatability")
        if isinstance(repeatability, str):
            repeatability = _parse_repeatability_string(repeatability)

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            observed_behavior=data["observed_behavior"],
            catalog_version=data["catalog_version"],
            model=data.get("model", ""),
            scaffolding=data.get("scaffolding"),
            repeatability=repeatability,
            suspected_disorder=data.get("suspected_disorder"),
            battery_scores=data.get("battery_scores", {}),
            telemetry_excerpts=data.get("telemetry_excerpts", []),
            diagnosis_id=data.get("diagnosis_id"),
            mechanistic_evidence=data.get("mechanistic_evidence"),
        )

    def add_telemetry_excerpt(self, event: Event) -> None:
        """Add a telemetry event excerpt (should be redacted)."""
        self.telemetry_excerpts.append(event)
