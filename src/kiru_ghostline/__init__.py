"""kiru-ghostline: behavioral diagnostics for AI agents.

Probe for known DEM-X failure modes, watch a live agent for drift,
and document new findings in the upload-ready format.
"""

__version__ = "0.1.0"

from .trace import (
    SCHEMA_VERSION,
    Diagnosis,
    Event,
    Signal,
    Trace,
    TraceHeader,
    TraceParseError,
    TraceValidationError,
    iter_events,
    read_jsonl,
    read_jsonl_stream,
    validate_jsonl,
    validate_trace,
    write_jsonl,
    write_jsonl_stream,
)

__all__ = [
    "SCHEMA_VERSION",
    "Diagnosis",
    "Event",
    "Signal",
    "Trace",
    "TraceHeader",
    "TraceParseError",
    "TraceValidationError",
    "iter_events",
    "read_jsonl",
    "read_jsonl_stream",
    "validate_jsonl",
    "validate_trace",
    "write_jsonl",
    "write_jsonl_stream",
]
