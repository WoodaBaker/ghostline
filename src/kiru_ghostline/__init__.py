"""kiru-ghostline: behavioral diagnostics for AI agents.

Probe for known DEM-X failure modes, watch a live agent for drift,
and document new findings in the upload-ready format.
"""

__version__ = "0.1.0"

from .schema import (
    SCHEMA_VERSION,
    CaptureMode,
    Diagnosis,
    Event,
    EventType,
    ModelRef,
    Signal,
    SignalSource,
    Trace,
    TraceParseError,
    TraceValidationError,
    Verdict,
    append_event,
    iter_events,
    read_jsonl,
    to_kiru_event,
    validate_jsonl,
    write_jsonl,
)

__all__ = [
    "SCHEMA_VERSION",
    "CaptureMode",
    "Diagnosis",
    "Event",
    "EventType",
    "ModelRef",
    "Signal",
    "SignalSource",
    "Trace",
    "TraceParseError",
    "TraceValidationError",
    "Verdict",
    "append_event",
    "iter_events",
    "read_jsonl",
    "to_kiru_event",
    "validate_jsonl",
    "write_jsonl",
]
