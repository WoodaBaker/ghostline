"""ghostline.v1 trace schema and JSONL serialization.

Implements the Blueprint contract for capturing and analyzing agent behavior.
See docs/schema-v1.md for the full specification.
"""

from __future__ import annotations

import json
import re
import uuid
import warnings
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, TextIO

from . import __version__

SCHEMA_VERSION = "ghostline.v1"
CURRENT_MAJOR = 1
SUPPORTED_MAJORS = {0, 1}

_VERSION_PATTERN = re.compile(r"^ghostline\.v(\d+)$")
_RFC3339_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
_DEMX_CODE_PATTERN = re.compile(r"^[A-Z]{2,4}-[A-Z]{2,4}-\d{2,4}$")


class TraceValidationError(Exception):
    """Raised when trace data fails validation."""


class TraceParseError(Exception):
    """Raised when JSONL parsing fails."""

    def __init__(self, message: str, line_number: int | None = None):
        self.line_number = line_number
        if line_number is not None:
            message = f"Line {line_number}: {message}"
        super().__init__(message)


class EventType(str, Enum):
    """Types of events in an agent trace."""

    PROMPT_STARTED = "prompt_started"
    RESPONSE_RECEIVED = "response_received"
    TOOL_CALLED = "tool_called"
    TOOL_RESULT = "tool_result"
    SESSION_CLOSED = "session_closed"
    OBJECTIVE_SET = "objective_set"
    CUSTOM = "custom"


class CaptureMode(str, Enum):
    """Level of payload capture."""

    METADATA_ONLY = "metadata_only"
    PARTIAL_PAYLOAD = "partial_payload"
    FULL_PAYLOAD = "full_payload"


class Verdict(str, Enum):
    """Diagnosis verdict."""

    CLEAN = "clean"
    SIGNAL = "signal"
    INCONCLUSIVE = "inconclusive"


class SignalSource(str, Enum):
    """Source of a signal detection."""

    DETECTOR = "detector"
    BATTERY = "battery"
    CHECKER = "checker"
    JUDGE = "judge"


_EVENT_TYPE_VALUES = {e.value for e in EventType}
_CAPTURE_MODE_VALUES = {e.value for e in CaptureMode}
_VERDICT_VALUES = {e.value for e in Verdict}
_SIGNAL_SOURCE_VALUES = {e.value for e in SignalSource}

_CAPTURE_MODE_ORDER = {
    CaptureMode.METADATA_ONLY: 0,
    CaptureMode.PARTIAL_PAYLOAD: 1,
    CaptureMode.FULL_PAYLOAD: 2,
}


def _now_rfc3339() -> str:
    """Return current UTC time in RFC3339 format with Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_rfc3339(ts: str, field_name: str) -> None:
    """Validate RFC3339 UTC timestamp format."""
    if not _RFC3339_PATTERN.match(ts):
        raise TraceValidationError(
            f"Invalid RFC3339 timestamp for {field_name}: {ts!r}"
        )


def _validate_demx_code(code: str) -> None:
    """Validate DEM-X disorder code format."""
    if not _DEMX_CODE_PATTERN.match(code):
        raise TraceValidationError(
            f"Invalid DEM-X code format: {code!r}; expected format like GI-SYCO-01"
        )


def _parse_version(version: str) -> int:
    """Parse schema version string, return major version number."""
    match = _VERSION_PATTERN.match(version)
    if not match:
        raise TraceValidationError(
            f"Invalid schema version format: {version!r}; expected 'ghostline.v<MAJOR>'"
        )
    return int(match.group(1))


@dataclass
class ModelRef:
    """Reference to a model."""

    provider: str
    name: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "name": self.name, "params": self.params}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelRef:
        if "provider" not in data:
            raise TraceValidationError("ModelRef missing required field 'provider'")
        if "name" not in data:
            raise TraceValidationError("ModelRef missing required field 'name'")
        return cls(
            provider=data["provider"],
            name=data["name"],
            params=data.get("params", {}),
        )


@dataclass
class Event:
    """A single event in an agent trace."""

    event_id: str
    event_type: EventType | str
    ts: str
    session_key: str
    payload: dict[str, Any]
    idempotency_key: str = ""
    agent_label: str = ""
    seq: int | None = None
    model: ModelRef | None = None
    capture_mode: CaptureMode = CaptureMode.PARTIAL_PAYLOAD
    metadata: dict[str, Any] = field(default_factory=dict)
    _raw_event_type: str | None = field(default=None, repr=False)
    _extra_fields: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if len(self.session_key) > 120:
            raise TraceValidationError(
                f"session_key exceeds 120 chars: {len(self.session_key)}"
            )
        if len(self.idempotency_key) > 128:
            raise TraceValidationError(
                f"idempotency_key exceeds 128 chars: {len(self.idempotency_key)}"
            )
        if len(self.agent_label) > 120:
            raise TraceValidationError(
                f"agent_label exceeds 120 chars: {len(self.agent_label)}"
            )
        _validate_rfc3339(self.ts, "ts")

    def to_dict(self) -> dict[str, Any]:
        if self._raw_event_type is not None:
            event_type_str = self._raw_event_type
        elif isinstance(self.event_type, EventType):
            event_type_str = self.event_type.value
        else:
            event_type_str = self.event_type

        result: dict[str, Any] = {
            "event_id": self.event_id,
            "event_type": event_type_str,
            "ts": self.ts,
            "session_key": self.session_key,
            "payload": self.payload,
        }
        if self.idempotency_key:
            result["idempotency_key"] = self.idempotency_key
        if self.agent_label:
            result["agent_label"] = self.agent_label
        if self.seq is not None:
            result["seq"] = self.seq
        if self.model is not None:
            result["model"] = self.model.to_dict()
        if self.capture_mode != CaptureMode.PARTIAL_PAYLOAD:
            result["capture_mode"] = self.capture_mode.value
        if self.metadata:
            result["metadata"] = self.metadata
        result.update(self._extra_fields)
        return result

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], *, seq_default: int | None = None
    ) -> Event:
        if not isinstance(data, dict):
            raise TraceValidationError("Event data must be a dict")

        required = {"event_id", "event_type", "ts", "session_key", "payload"}
        missing = required - data.keys()
        if missing:
            raise TraceValidationError(
                f"Event missing required fields: {', '.join(sorted(missing))}"
            )

        event_type_raw = data["event_type"]
        if event_type_raw in _EVENT_TYPE_VALUES:
            event_type = EventType(event_type_raw)
            raw_event_type = None
        else:
            event_type = EventType.CUSTOM
            raw_event_type = event_type_raw

        capture_mode_raw = data.get("capture_mode", "partial_payload")
        if capture_mode_raw not in _CAPTURE_MODE_VALUES:
            raise TraceValidationError(
                f"Invalid capture_mode: {capture_mode_raw!r}; "
                f"must be one of {_CAPTURE_MODE_VALUES}"
            )
        capture_mode = CaptureMode(capture_mode_raw)

        model = None
        if data.get("model") is not None:
            model = ModelRef.from_dict(data["model"])

        known_fields = {
            "event_id",
            "event_type",
            "ts",
            "session_key",
            "payload",
            "idempotency_key",
            "agent_label",
            "seq",
            "model",
            "capture_mode",
            "metadata",
            "kind",
        }
        extra_fields = {k: v for k, v in data.items() if k not in known_fields}

        return cls(
            event_id=data["event_id"],
            event_type=event_type,
            ts=data["ts"],
            session_key=data["session_key"],
            payload=data["payload"],
            idempotency_key=data.get("idempotency_key", ""),
            agent_label=data.get("agent_label", ""),
            seq=data.get("seq", seq_default),
            model=model,
            capture_mode=capture_mode,
            metadata=data.get("metadata", {}),
            _raw_event_type=raw_event_type,
            _extra_fields=extra_fields,
        )

    @classmethod
    def create(
        cls,
        event_type: EventType | str,
        session_key: str,
        payload: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Event:
        """Create an event with auto-generated id and timestamp."""
        return cls(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            ts=_now_rfc3339(),
            session_key=session_key,
            payload=payload or {},
            **kwargs,
        )


@dataclass
class _TraceHeader:
    """JSONL header (internal use only)."""

    schema_version: str
    trace_id: str
    created_at: str
    producer: str
    capture_mode: CaptureMode
    session_key: str | None = None
    agent_label: str | None = None
    objective: str | None = None
    redactions: list[str] | None = None
    _extra_fields: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "kind": "header",
            "schema_version": self.schema_version,
            "trace_id": self.trace_id,
            "created_at": self.created_at,
            "producer": self.producer,
            "capture_mode": self.capture_mode.value,
        }
        if self.session_key is not None:
            result["session_key"] = self.session_key
        if self.agent_label is not None:
            result["agent_label"] = self.agent_label
        if self.objective is not None:
            result["objective"] = self.objective
        if self.redactions is not None:
            result["redactions"] = self.redactions
        result.update(self._extra_fields)
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> _TraceHeader:
        if not isinstance(data, dict):
            raise TraceValidationError("Header data must be a dict")

        if data.get("kind") != "header":
            raise TraceValidationError("First line must have kind='header'")

        version = data.get("schema_version")
        if version is None:
            raise TraceValidationError("Header missing required field 'schema_version'")

        major = _parse_version(version)
        if major not in SUPPORTED_MAJORS:
            raise TraceValidationError(
                f"Unsupported schema major version {major}; "
                f"supported: {sorted(SUPPORTED_MAJORS)}"
            )

        required = {"trace_id", "created_at", "producer", "capture_mode"}
        missing = required - data.keys()
        if missing:
            raise TraceValidationError(
                f"Header missing required fields: {', '.join(sorted(missing))}"
            )

        _validate_rfc3339(data["created_at"], "created_at")

        capture_mode_raw = data["capture_mode"]
        if capture_mode_raw not in _CAPTURE_MODE_VALUES:
            raise TraceValidationError(f"Invalid capture_mode: {capture_mode_raw!r}")

        known_fields = {
            "kind",
            "schema_version",
            "trace_id",
            "created_at",
            "producer",
            "capture_mode",
            "session_key",
            "agent_label",
            "objective",
            "redactions",
        }
        extra_fields = {k: v for k, v in data.items() if k not in known_fields}

        return cls(
            schema_version=version,
            trace_id=data["trace_id"],
            created_at=data["created_at"],
            producer=data["producer"],
            capture_mode=CaptureMode(capture_mode_raw),
            session_key=data.get("session_key"),
            agent_label=data.get("agent_label"),
            objective=data.get("objective"),
            redactions=data.get("redactions"),
            _extra_fields=extra_fields,
        )


@dataclass
class Trace:
    """A sequence of events representing an agent run."""

    trace_id: str
    created_at: str
    producer: str
    capture_mode: CaptureMode
    schema_version: str = SCHEMA_VERSION
    session_key: str | None = None
    agent_label: str | None = None
    objective: str | None = None
    redactions: list[str] | None = None
    events: list[Event] = field(default_factory=list)
    _extra_fields: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        _validate_rfc3339(self.created_at, "created_at")

    def add_event(self, event: Event) -> None:
        """Add an event to the trace."""
        self.events.append(event)
        mode_order = _CAPTURE_MODE_ORDER.get(event.capture_mode, 1)
        current_order = _CAPTURE_MODE_ORDER.get(self.capture_mode, 1)
        if mode_order > current_order:
            self.capture_mode = event.capture_mode
        if (
            self.objective is None
            and event.event_type == EventType.OBJECTIVE_SET
            and "objective" in event.payload
        ):
            self.objective = event.payload["objective"]

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "trace_id": self.trace_id,
            "created_at": self.created_at,
            "producer": self.producer,
            "capture_mode": self.capture_mode.value,
            "events": [e.to_dict() for e in self.events],
        }
        if self.session_key is not None:
            result["session_key"] = self.session_key
        if self.agent_label is not None:
            result["agent_label"] = self.agent_label
        if self.objective is not None:
            result["objective"] = self.objective
        if self.redactions is not None:
            result["redactions"] = self.redactions
        result.update(self._extra_fields)
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Trace:
        if not isinstance(data, dict):
            raise TraceValidationError("Trace data must be a dict")

        required = {
            "schema_version",
            "trace_id",
            "created_at",
            "producer",
            "capture_mode",
        }
        missing = required - data.keys()
        if missing:
            raise TraceValidationError(
                f"Trace missing required fields: {', '.join(sorted(missing))}"
            )

        major = _parse_version(data["schema_version"])
        if major not in SUPPORTED_MAJORS:
            raise TraceValidationError(f"Unsupported schema major version {major}")

        capture_mode_raw = data["capture_mode"]
        if capture_mode_raw not in _CAPTURE_MODE_VALUES:
            raise TraceValidationError(f"Invalid capture_mode: {capture_mode_raw!r}")

        events = [
            Event.from_dict(e, seq_default=i)
            for i, e in enumerate(data.get("events", []))
        ]

        known_fields = {
            "schema_version",
            "trace_id",
            "created_at",
            "producer",
            "capture_mode",
            "session_key",
            "agent_label",
            "objective",
            "redactions",
            "events",
        }
        extra_fields = {k: v for k, v in data.items() if k not in known_fields}

        return cls(
            schema_version=data["schema_version"],
            trace_id=data["trace_id"],
            created_at=data["created_at"],
            producer=data["producer"],
            capture_mode=CaptureMode(capture_mode_raw),
            session_key=data.get("session_key"),
            agent_label=data.get("agent_label"),
            objective=data.get("objective"),
            redactions=data.get("redactions"),
            events=events,
            _extra_fields=extra_fields,
        )

    @classmethod
    def create(
        cls,
        session_key: str | None = None,
        capture_mode: CaptureMode = CaptureMode.PARTIAL_PAYLOAD,
        **kwargs: Any,
    ) -> Trace:
        """Create a trace with auto-generated id and timestamp."""
        return cls(
            trace_id=str(uuid.uuid4()),
            created_at=_now_rfc3339(),
            producer=f"kiru-ghostline/{__version__}",
            capture_mode=capture_mode,
            session_key=session_key,
            **kwargs,
        )


@dataclass
class Signal:
    """A detected disorder signal from trace analysis."""

    code: str
    confidence: float
    source: SignalSource
    producer: str
    explanation: str
    evidence_event_ids: list[str] = field(default_factory=list)
    score: float | None = None
    level: int | None = None
    _extra_fields: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        _validate_demx_code(self.code)
        if not 0.0 <= self.confidence <= 1.0:
            raise TraceValidationError(
                f"Signal confidence must be between 0.0 and 1.0, got {self.confidence}"
            )
        if self.source == SignalSource.DETECTOR and not self.evidence_event_ids:
            raise TraceValidationError(
                "Signal with source=detector requires non-empty evidence_event_ids"
            )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "code": self.code,
            "confidence": self.confidence,
            "source": self.source.value,
            "producer": self.producer,
            "explanation": self.explanation,
        }
        if self.evidence_event_ids:
            result["evidence_event_ids"] = self.evidence_event_ids
        if self.score is not None:
            result["score"] = self.score
        if self.level is not None:
            result["level"] = self.level
        result.update(self._extra_fields)
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Signal:
        if not isinstance(data, dict):
            raise TraceValidationError("Signal data must be a dict")

        required = {"code", "confidence", "source", "producer", "explanation"}
        missing = required - data.keys()
        if missing:
            raise TraceValidationError(
                f"Signal missing required fields: {', '.join(sorted(missing))}"
            )

        source_raw = data["source"]
        if source_raw not in _SIGNAL_SOURCE_VALUES:
            raise TraceValidationError(
                f"Invalid signal source: {source_raw!r}; "
                f"must be one of {_SIGNAL_SOURCE_VALUES}"
            )

        known_fields = {
            "code",
            "confidence",
            "source",
            "producer",
            "explanation",
            "evidence_event_ids",
            "score",
            "level",
        }
        extra_fields = {k: v for k, v in data.items() if k not in known_fields}

        return cls(
            code=data["code"],
            confidence=data["confidence"],
            source=SignalSource(source_raw),
            producer=data["producer"],
            explanation=data["explanation"],
            evidence_event_ids=data.get("evidence_event_ids", []),
            score=data.get("score"),
            level=data.get("level"),
            _extra_fields=extra_fields,
        )


@dataclass
class Diagnosis:
    """Aggregated analysis result linking signals to disorders."""

    diagnosis_id: str
    created_at: str
    catalog_version: str
    verdict: Verdict
    ran: list[str]
    schema_version: str = SCHEMA_VERSION
    trace_id: str | None = None
    threshold: float = 0.5
    signals: list[Signal] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    calls: int = 0
    _extra_fields: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        _validate_rfc3339(self.created_at, "created_at")
        self.signals = sorted(self.signals, key=lambda s: s.confidence, reverse=True)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "diagnosis_id": self.diagnosis_id,
            "created_at": self.created_at,
            "catalog_version": self.catalog_version,
            "verdict": self.verdict.value,
            "threshold": self.threshold,
            "signals": [s.to_dict() for s in self.signals],
            "ran": self.ran,
            "skipped": self.skipped,
            "calls": self.calls,
        }
        if self.trace_id is not None:
            result["trace_id"] = self.trace_id
        result.update(self._extra_fields)
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Diagnosis:
        if not isinstance(data, dict):
            raise TraceValidationError("Diagnosis data must be a dict")

        required = {"diagnosis_id", "created_at", "catalog_version", "verdict", "ran"}
        missing = required - data.keys()
        if missing:
            raise TraceValidationError(
                f"Diagnosis missing required fields: {', '.join(sorted(missing))}"
            )

        verdict_raw = data["verdict"]
        if verdict_raw not in _VERDICT_VALUES:
            raise TraceValidationError(
                f"Invalid verdict: {verdict_raw!r}; must be one of {_VERDICT_VALUES}"
            )

        signals = [Signal.from_dict(s) for s in data.get("signals", [])]

        known_fields = {
            "schema_version",
            "diagnosis_id",
            "created_at",
            "catalog_version",
            "verdict",
            "threshold",
            "signals",
            "ran",
            "skipped",
            "calls",
            "trace_id",
        }
        extra_fields = {k: v for k, v in data.items() if k not in known_fields}

        return cls(
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            diagnosis_id=data["diagnosis_id"],
            created_at=data["created_at"],
            catalog_version=data["catalog_version"],
            verdict=Verdict(verdict_raw),
            threshold=data.get("threshold", 0.5),
            signals=signals,
            ran=data["ran"],
            skipped=data.get("skipped", []),
            calls=data.get("calls", 0),
            trace_id=data.get("trace_id"),
            _extra_fields=extra_fields,
        )

    @classmethod
    def create(
        cls,
        catalog_version: str,
        ran: list[str],
        signals: list[Signal] | None = None,
        threshold: float = 0.5,
        **kwargs: Any,
    ) -> Diagnosis:
        """Create a diagnosis with auto-generated id and timestamp."""
        signals = signals or []
        verdict = (
            Verdict.SIGNAL
            if any(s.confidence >= threshold for s in signals)
            else Verdict.CLEAN
        )
        return cls(
            diagnosis_id=str(uuid.uuid4()),
            created_at=_now_rfc3339(),
            catalog_version=catalog_version,
            verdict=verdict,
            ran=ran,
            signals=signals,
            threshold=threshold,
            **kwargs,
        )


def _default_trace_path(session_key: str) -> Path:
    """Return default trace file path."""
    return Path(".ghostline") / "traces" / f"{session_key}.jsonl"


def write_jsonl(
    path: str | Path,
    trace: Trace,
    *,
    append: bool = False,
) -> None:
    """Write a trace to a JSONL file.

    If append=True and file exists, appends events without header.
    If append=True and file doesn't exist, writes header then events.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if append and path.exists():
        with path.open("a", encoding="utf-8") as f:
            for event in trace.events:
                line = {"kind": "event", **event.to_dict()}
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
    else:
        with path.open("w", encoding="utf-8") as f:
            header = _TraceHeader(
                schema_version=trace.schema_version,
                trace_id=trace.trace_id,
                created_at=trace.created_at,
                producer=trace.producer,
                capture_mode=trace.capture_mode,
                session_key=trace.session_key,
                agent_label=trace.agent_label,
                objective=trace.objective,
                redactions=trace.redactions,
                _extra_fields=trace._extra_fields,
            )
            f.write(json.dumps(header.to_dict(), ensure_ascii=False) + "\n")
            for event in trace.events:
                line = {"kind": "event", **event.to_dict()}
                f.write(json.dumps(line, ensure_ascii=False) + "\n")


def append_event(path: str | Path, event: Event, trace: Trace | None = None) -> None:
    """Append a single event to a JSONL file.

    If file doesn't exist and trace is provided, writes header first.
    If file doesn't exist and trace is None, raises TraceValidationError.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        if trace is None:
            raise TraceValidationError(
                "Cannot append to non-existent file without trace header"
            )
        with path.open("w", encoding="utf-8") as f:
            header = _TraceHeader(
                schema_version=trace.schema_version,
                trace_id=trace.trace_id,
                created_at=trace.created_at,
                producer=trace.producer,
                capture_mode=trace.capture_mode,
                session_key=trace.session_key,
                agent_label=trace.agent_label,
                objective=trace.objective,
                redactions=trace.redactions,
            )
            f.write(json.dumps(header.to_dict(), ensure_ascii=False) + "\n")

    with path.open("a", encoding="utf-8") as f:
        line = {"kind": "event", **event.to_dict()}
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def read_jsonl(path: str | Path) -> Trace:
    """Read a trace from a JSONL file (streaming)."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        return _read_jsonl_stream(f, str(path))


def _read_jsonl_stream(f: TextIO, source_name: str = "<stream>") -> Trace:
    """Read a trace from a stream (internal)."""
    header: _TraceHeader | None = None
    events: list[Event] = []
    line_number = 0
    last_line_truncated = False

    for raw_line in f:
        line_number += 1
        line = raw_line.rstrip("\n\r")

        if not line or line.isspace():
            continue

        try:
            data = json.loads(line)
        except json.JSONDecodeError as e:
            if line_number == 1:
                raise TraceParseError(
                    f"Invalid JSON in header: {e}", line_number=1
                ) from e
            last_line_truncated = True
            continue

        if not isinstance(data, dict):
            raise TraceParseError(
                f"Expected JSON object, got {type(data).__name__}",
                line_number=line_number,
            )

        if last_line_truncated:
            raise TraceParseError(
                "Malformed line (previous truncated line was not last)",
                line_number=line_number - 1,
            )

        if header is None:
            try:
                header = _TraceHeader.from_dict(data)
            except TraceValidationError as e:
                raise TraceParseError(str(e), line_number=1) from e
        else:
            kind = data.get("kind")
            if kind != "event":
                raise TraceParseError(
                    f"Expected kind='event', got {kind!r}",
                    line_number=line_number,
                )
            try:
                events.append(Event.from_dict(data, seq_default=len(events)))
            except TraceValidationError as e:
                raise TraceParseError(str(e), line_number=line_number) from e

    if last_line_truncated:
        warnings.warn(
            f"Truncated last line in {source_name} (crash safety: ignored)",
            stacklevel=3,
        )

    if header is None:
        raise TraceParseError("Empty file or missing header")

    return Trace(
        schema_version=header.schema_version,
        trace_id=header.trace_id,
        created_at=header.created_at,
        producer=header.producer,
        capture_mode=header.capture_mode,
        session_key=header.session_key,
        agent_label=header.agent_label,
        objective=header.objective,
        redactions=header.redactions,
        events=events,
        _extra_fields=header._extra_fields,
    )


def iter_events(path: str | Path) -> Iterator[Event]:
    """Iterate over events in a JSONL file (streaming)."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        yield from _iter_events_stream(f, str(path))


def _iter_events_stream(f: TextIO, source_name: str = "<stream>") -> Iterator[Event]:
    """Iterate events from a stream (internal)."""
    header_seen = False
    line_number = 0
    event_seq = 0
    last_line_truncated = False

    for raw_line in f:
        line_number += 1
        line = raw_line.rstrip("\n\r")

        if not line or line.isspace():
            continue

        try:
            data = json.loads(line)
        except json.JSONDecodeError as e:
            if line_number == 1:
                raise TraceParseError(
                    f"Invalid JSON in header: {e}", line_number=1
                ) from e
            last_line_truncated = True
            continue

        if not isinstance(data, dict):
            raise TraceParseError(
                f"Expected JSON object, got {type(data).__name__}",
                line_number=line_number,
            )

        if last_line_truncated:
            raise TraceParseError(
                "Malformed line (previous truncated line was not last)",
                line_number=line_number - 1,
            )

        if not header_seen:
            try:
                _TraceHeader.from_dict(data)
            except TraceValidationError as e:
                raise TraceParseError(str(e), line_number=1) from e
            header_seen = True
        else:
            kind = data.get("kind")
            if kind != "event":
                raise TraceParseError(
                    f"Expected kind='event', got {kind!r}",
                    line_number=line_number,
                )
            try:
                yield Event.from_dict(data, seq_default=event_seq)
                event_seq += 1
            except TraceValidationError as e:
                raise TraceParseError(str(e), line_number=line_number) from e

    if last_line_truncated:
        warnings.warn(
            f"Truncated last line in {source_name} (crash safety: ignored)",
            stacklevel=3,
        )

    if not header_seen:
        raise TraceParseError("Empty file or missing header")


def validate_jsonl(path: str | Path) -> list[str]:
    """Validate a JSONL file and return a list of issues (streaming)."""
    issues: list[str] = []
    path = Path(path)

    try:
        with path.open("r", encoding="utf-8") as f:
            header_seen = False
            line_number = 0

            for raw_line in f:
                line_number += 1
                line = raw_line.rstrip("\n\r")

                if not line or line.isspace():
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError as e:
                    issues.append(f"Line {line_number}: Invalid JSON: {e}")
                    continue

                if not isinstance(data, dict):
                    issues.append(
                        f"Line {line_number}: Expected JSON object, "
                        f"got {type(data).__name__}"
                    )
                    continue

                if not header_seen:
                    if data.get("kind") != "header":
                        issues.append("Line 1: Missing kind='header'")
                    if "schema_version" not in data:
                        issues.append("Line 1: Missing schema_version")
                    else:
                        try:
                            major = _parse_version(data["schema_version"])
                            if major not in SUPPORTED_MAJORS:
                                issues.append(
                                    f"Line 1: Unsupported major version {major}"
                                )
                        except TraceValidationError as e:
                            issues.append(f"Line 1: {e}")
                    header_seen = True
                else:
                    if data.get("kind") != "event":
                        issues.append(f"Line {line_number}: Expected kind='event'")
                    required = {
                        "event_id",
                        "event_type",
                        "ts",
                        "session_key",
                        "payload",
                    }
                    missing = required - data.keys()
                    if missing:
                        issues.append(
                            f"Line {line_number}: Missing fields: "
                            f"{', '.join(sorted(missing))}"
                        )

            if not header_seen:
                issues.append("Empty file or missing header")

    except FileNotFoundError:
        issues.append(f"File not found: {path}")
    except PermissionError:
        issues.append(f"Permission denied: {path}")

    return issues


def to_kiru_event(event: Event) -> dict[str, Any]:
    """Map an Event to KIRU TelemetryEvent format.

    Moves ts, seq, model, capture_mode into metadata.
    schema_version 'ghostline.v1' maps to 'v1'.
    """
    metadata = dict(event.metadata)
    metadata["ts"] = event.ts
    if event.seq is not None:
        metadata["seq"] = event.seq
    if event.model is not None:
        metadata["model"] = event.model.to_dict()
    metadata["capture_mode"] = event.capture_mode.value

    event_type_str = (
        event._raw_event_type
        if event._raw_event_type is not None
        else event.event_type.value
        if isinstance(event.event_type, EventType)
        else event.event_type
    )

    return {
        "schema_version": "v1",
        "event_id": event.event_id,
        "event_type": event_type_str,
        "idempotency_key": event.idempotency_key,
        "session_key": event.session_key,
        "agent_label": event.agent_label,
        "payload": event.payload,
        "metadata": metadata,
    }
