"""Ghostline v1 trace schema and JSONL serialization.

This module defines the trace format for capturing agent behavior:
- Event: individual occurrences (model calls, tool uses, observations)
- Trace: a sequence of events with metadata
- Signal: a detected disorder signal from analysis
- Diagnosis: aggregated analysis result linking signals to disorders

JSONL format uses a header line with schema version, followed by event records.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TextIO

SCHEMA_VERSION = "ghostline.v1"

CaptureMode = Literal["full", "sample", "summary"]
EventKind = Literal["model_call", "tool_use", "observation", "error", "custom"]


class TraceValidationError(Exception):
    """Raised when trace data fails validation."""


class TraceParseError(Exception):
    """Raised when JSONL parsing fails."""

    def __init__(self, message: str, line_number: int | None = None):
        self.line_number = line_number
        if line_number is not None:
            message = f"Line {line_number}: {message}"
        super().__init__(message)


@dataclass
class Event:
    """A single event in an agent trace.

    Events capture discrete occurrences: model calls, tool invocations,
    observations, errors, or custom application-specific events.
    """

    kind: EventKind
    ts: str  # ISO 8601 timestamp
    data: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        valid_kinds = {"model_call", "tool_use", "observation", "error", "custom"}
        if self.kind not in valid_kinds:
            raise TraceValidationError(
                f"Invalid event kind '{self.kind}'; must be one of {valid_kinds}"
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        known = {"kind", "ts", "data", "id"}
        filtered = {k: v for k, v in data.items() if k in known}
        if "kind" not in filtered:
            raise TraceValidationError("Event missing required field 'kind'")
        if "ts" not in filtered:
            raise TraceValidationError("Event missing required field 'ts'")
        return cls(**filtered)

    @classmethod
    def now(cls, kind: EventKind, data: dict[str, Any] | None = None) -> Event:
        """Create an event with the current timestamp."""
        return cls(
            kind=kind,
            ts=datetime.now(timezone.utc).isoformat(),
            data=data or {},
        )


@dataclass
class Signal:
    """A detected disorder signal from trace analysis.

    Signals are intermediate results linking observed patterns to
    potential disorders. Multiple signals may contribute to a diagnosis.
    """

    disorder: str  # e.g. "GI-SYCO-01"
    score: float  # 0..1 -- higher means stronger signal
    evidence: list[str] = field(default_factory=list)  # event IDs
    details: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise TraceValidationError(
                f"Signal score must be between 0.0 and 1.0, got {self.score}"
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Signal:
        known = {"disorder", "score", "evidence", "details", "id"}
        filtered = {k: v for k, v in data.items() if k in known}
        if "disorder" not in filtered:
            raise TraceValidationError("Signal missing required field 'disorder'")
        if "score" not in filtered:
            raise TraceValidationError("Signal missing required field 'score'")
        return cls(**filtered)


@dataclass
class Diagnosis:
    """Aggregated analysis result linking signals to disorders.

    A diagnosis summarizes the analysis of a trace, collecting all
    detected signals and providing an overall assessment.
    """

    signals: list[Signal] = field(default_factory=list)
    summary: str = ""
    model: str = ""
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def has_signals(self) -> bool:
        return len(self.signals) > 0

    @property
    def max_score(self) -> float:
        if not self.signals:
            return 0.0
        return max(s.score for s in self.signals)

    def to_dict(self) -> dict[str, Any]:
        return {
            "signals": [s.to_dict() for s in self.signals],
            "summary": self.summary,
            "model": self.model,
            "ts": self.ts,
            "id": self.id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Diagnosis:
        signals = [Signal.from_dict(s) for s in data.get("signals", [])]
        return cls(
            signals=signals,
            summary=data.get("summary", ""),
            model=data.get("model", ""),
            ts=data.get("ts", datetime.now(timezone.utc).isoformat()),
            id=data.get("id", str(uuid.uuid4())),
        )


@dataclass
class Trace:
    """A sequence of events representing an agent run.

    Traces capture the full behavioral record of an agent interaction,
    including model calls, tool uses, and any observations or errors.
    """

    events: list[Event] = field(default_factory=list)
    model: str = ""
    capture_mode: CaptureMode = "full"
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    diagnosis: Diagnosis | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        valid_modes = {"full", "sample", "summary"}
        if self.capture_mode not in valid_modes:
            raise TraceValidationError(
                f"Invalid capture_mode '{self.capture_mode}'; "
                f"must be one of {valid_modes}"
            )

    def add_event(self, event: Event) -> None:
        """Add an event to the trace."""
        self.events.append(event)

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": [e.to_dict() for e in self.events],
            "model": self.model,
            "capture_mode": self.capture_mode,
            "ts": self.ts,
            "diagnosis": self.diagnosis.to_dict() if self.diagnosis else None,
            "metadata": self.metadata,
            "id": self.id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Trace:
        events = [Event.from_dict(e) for e in data.get("events", [])]
        diagnosis = None
        if data.get("diagnosis"):
            diagnosis = Diagnosis.from_dict(data["diagnosis"])
        return cls(
            events=events,
            model=data.get("model", ""),
            capture_mode=data.get("capture_mode", "full"),
            ts=data.get("ts", datetime.now(timezone.utc).isoformat()),
            diagnosis=diagnosis,
            metadata=data.get("metadata", {}),
            id=data.get("id", str(uuid.uuid4())),
        )


@dataclass
class TraceHeader:
    """JSONL header line carrying schema version and metadata."""

    schema_version: str = SCHEMA_VERSION
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    model: str = ""
    capture_mode: CaptureMode = "full"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ts": self.ts,
            "model": self.model,
            "capture_mode": self.capture_mode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TraceHeader:
        version = data.get("schema_version")
        if version is None:
            raise TraceValidationError("Header missing required field 'schema_version'")
        if version != SCHEMA_VERSION:
            raise TraceValidationError(
                f"Unsupported schema version '{version}'; expected '{SCHEMA_VERSION}'"
            )
        return cls(
            schema_version=version,
            ts=data.get("ts", datetime.now(timezone.utc).isoformat()),
            model=data.get("model", ""),
            capture_mode=data.get("capture_mode", "full"),
        )


def write_jsonl(
    path: str | Path,
    trace: Trace,
    *,
    append: bool = False,
) -> None:
    """Write a trace to a JSONL file.

    The file starts with a header line containing schema version and metadata,
    followed by one line per event.

    Args:
        path: File path to write to.
        trace: The trace to serialize.
        append: If True, append events without header (for streaming).
    """
    path = Path(path)
    mode = "a" if append else "w"

    with path.open(mode) as f:
        if not append:
            header = TraceHeader(
                ts=trace.ts,
                model=trace.model,
                capture_mode=trace.capture_mode,
            )
            f.write(json.dumps(header.to_dict()) + "\n")

        for event in trace.events:
            f.write(json.dumps(event.to_dict()) + "\n")


def write_jsonl_stream(
    f: TextIO,
    trace: Trace,
    *,
    include_header: bool = True,
) -> None:
    """Write a trace to an open file handle.

    Args:
        f: Open file handle to write to.
        trace: The trace to serialize.
        include_header: If True, write the header line first.
    """
    if include_header:
        header = TraceHeader(
            ts=trace.ts,
            model=trace.model,
            capture_mode=trace.capture_mode,
        )
        f.write(json.dumps(header.to_dict()) + "\n")

    f.writelines(json.dumps(event.to_dict()) + "\n" for event in trace.events)


def read_jsonl(path: str | Path) -> Trace:
    """Read a trace from a JSONL file.

    Expects a header line with schema version, followed by event lines.

    Args:
        path: File path to read from.

    Returns:
        Reconstructed Trace object.

    Raises:
        TraceParseError: If the file is malformed or missing required fields.
        TraceValidationError: If data fails validation.
    """
    path = Path(path)

    if not path.exists():
        raise TraceParseError(f"File not found: {path}")

    with path.open() as f:
        return read_jsonl_stream(f)


def read_jsonl_stream(f: TextIO) -> Trace:
    """Read a trace from an open file handle.

    Args:
        f: Open file handle to read from.

    Returns:
        Reconstructed Trace object.

    Raises:
        TraceParseError: If the content is malformed.
        TraceValidationError: If data fails validation.
    """
    lines = list(f)
    if not lines:
        raise TraceParseError("Empty file: expected header line")

    # Parse header
    try:
        header_data = json.loads(lines[0])
    except json.JSONDecodeError as e:
        raise TraceParseError(f"Invalid JSON in header: {e}", line_number=1) from e

    header = TraceHeader.from_dict(header_data)

    # Parse events
    events: list[Event] = []
    for i, line in enumerate(lines[1:], start=2):
        line = line.strip()
        if not line:
            continue
        try:
            event_data = json.loads(line)
        except json.JSONDecodeError as e:
            raise TraceParseError(f"Invalid JSON: {e}", line_number=i) from e

        try:
            events.append(Event.from_dict(event_data))
        except TraceValidationError as e:
            raise TraceParseError(str(e), line_number=i) from e

    return Trace(
        events=events,
        model=header.model,
        capture_mode=header.capture_mode,
        ts=header.ts,
    )


def iter_events(path: str | Path) -> Iterator[Event]:
    """Iterate over events in a JSONL file without loading all into memory.

    Yields events one at a time after validating the header.

    Args:
        path: File path to read from.

    Yields:
        Event objects, one per line after the header.

    Raises:
        TraceParseError: If the file is malformed.
        TraceValidationError: If data fails validation.
    """
    path = Path(path)

    if not path.exists():
        raise TraceParseError(f"File not found: {path}")

    with path.open() as f:
        # Validate header first
        header_line = f.readline()
        if not header_line:
            raise TraceParseError("Empty file: expected header line")

        try:
            header_data = json.loads(header_line)
        except json.JSONDecodeError as e:
            raise TraceParseError(f"Invalid JSON in header: {e}", line_number=1) from e

        TraceHeader.from_dict(header_data)  # Validate header

        # Yield events
        line_number = 1
        for line in f:
            line_number += 1
            line = line.strip()
            if not line:
                continue
            try:
                event_data = json.loads(line)
            except json.JSONDecodeError as e:
                raise TraceParseError(f"Invalid JSON: {e}", line_number=line_number)

            try:
                yield Event.from_dict(event_data)
            except TraceValidationError as e:
                raise TraceParseError(str(e), line_number=line_number)


def validate_trace(trace: Trace) -> list[str]:
    """Validate a trace and return a list of issues.

    Returns an empty list if the trace is valid.

    Args:
        trace: The trace to validate.

    Returns:
        List of validation error messages (empty if valid).
    """
    issues: list[str] = []

    if not trace.ts:
        issues.append("Trace missing timestamp (ts)")

    if trace.capture_mode not in {"full", "sample", "summary"}:
        issues.append(f"Invalid capture_mode: {trace.capture_mode}")

    for i, event in enumerate(trace.events):
        if event.kind not in {
            "model_call",
            "tool_use",
            "observation",
            "error",
            "custom",
        }:
            issues.append(f"Event {i}: invalid kind '{event.kind}'")
        if not event.ts:
            issues.append(f"Event {i}: missing timestamp (ts)")

    if trace.diagnosis:
        for i, signal in enumerate(trace.diagnosis.signals):
            if not 0.0 <= signal.score <= 1.0:
                issues.append(
                    f"Diagnosis signal {i}: score {signal.score} out of range [0, 1]"
                )

    return issues


def validate_jsonl(path: str | Path) -> list[str]:
    """Validate a JSONL file and return a list of issues.

    Returns an empty list if the file is valid.

    Args:
        path: File path to validate.

    Returns:
        List of validation error messages (empty if valid).
    """
    issues: list[str] = []
    path = Path(path)

    if not path.exists():
        return [f"File not found: {path}"]

    with path.open() as f:
        lines = list(f)

    if not lines:
        return ["Empty file: expected header line"]

    # Validate header
    try:
        header_data = json.loads(lines[0])
    except json.JSONDecodeError as e:
        return [f"Line 1: Invalid JSON in header: {e}"]

    if "schema_version" not in header_data:
        issues.append("Line 1: Header missing schema_version")
    elif header_data["schema_version"] != SCHEMA_VERSION:
        issues.append(
            f"Line 1: Unsupported schema version '{header_data['schema_version']}'"
        )

    # Validate events
    for i, line in enumerate(lines[1:], start=2):
        line = line.strip()
        if not line:
            continue

        try:
            event_data = json.loads(line)
        except json.JSONDecodeError as e:
            issues.append(f"Line {i}: Invalid JSON: {e}")
            continue

        if "kind" not in event_data:
            issues.append(f"Line {i}: Event missing required field 'kind'")
        elif event_data["kind"] not in {
            "model_call",
            "tool_use",
            "observation",
            "error",
            "custom",
        }:
            issues.append(f"Line {i}: Invalid event kind '{event_data['kind']}'")

        if "ts" not in event_data:
            issues.append(f"Line {i}: Event missing required field 'ts'")

    return issues
