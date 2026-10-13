"""Tests for ghostline.v1 trace schema and JSONL serialization."""

import io
import json

import pytest

from kiru_ghostline import (
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


class TestEvent:
    def test_create_event(self):
        event = Event(kind="model_call", ts="2026-01-01T00:00:00Z")
        assert event.kind == "model_call"
        assert event.ts == "2026-01-01T00:00:00Z"
        assert event.data == {}
        assert event.id  # UUID generated

    def test_event_with_data(self):
        event = Event(
            kind="tool_use",
            ts="2026-01-01T00:00:00Z",
            data={"tool": "search", "query": "test"},
        )
        assert event.data["tool"] == "search"

    def test_event_now(self):
        event = Event.now("observation", {"key": "value"})
        assert event.kind == "observation"
        assert event.ts  # Timestamp set
        assert event.data == {"key": "value"}

    def test_invalid_event_kind(self):
        with pytest.raises(TraceValidationError, match="Invalid event kind"):
            Event(kind="invalid", ts="2026-01-01T00:00:00Z")

    def test_event_to_dict(self):
        event = Event(kind="error", ts="2026-01-01T00:00:00Z", id="test-id")
        d = event.to_dict()
        assert d["kind"] == "error"
        assert d["ts"] == "2026-01-01T00:00:00Z"
        assert d["id"] == "test-id"

    def test_event_from_dict(self):
        event = Event.from_dict(
            {"kind": "custom", "ts": "2026-01-01T00:00:00Z", "data": {"x": 1}}
        )
        assert event.kind == "custom"
        assert event.data == {"x": 1}

    def test_event_from_dict_missing_kind(self):
        with pytest.raises(TraceValidationError, match="missing required field 'kind'"):
            Event.from_dict({"ts": "2026-01-01T00:00:00Z"})

    def test_event_from_dict_missing_ts(self):
        with pytest.raises(TraceValidationError, match="missing required field 'ts'"):
            Event.from_dict({"kind": "model_call"})

    def test_event_from_dict_ignores_unknown_fields(self):
        event = Event.from_dict(
            {"kind": "model_call", "ts": "2026-01-01T00:00:00Z", "unknown": "ignored"}
        )
        assert event.kind == "model_call"
        assert not hasattr(event, "unknown")


class TestSignal:
    def test_create_signal(self):
        signal = Signal(disorder="GI-SYCO-01", score=0.75)
        assert signal.disorder == "GI-SYCO-01"
        assert signal.score == 0.75
        assert signal.evidence == []
        assert signal.id

    def test_signal_with_evidence(self):
        signal = Signal(
            disorder="GI-DRFT-01",
            score=0.5,
            evidence=["event-1", "event-2"],
            details={"pattern": "goal_shift"},
        )
        assert signal.evidence == ["event-1", "event-2"]
        assert signal.details["pattern"] == "goal_shift"

    def test_signal_score_out_of_range_low(self):
        with pytest.raises(TraceValidationError, match="score must be between"):
            Signal(disorder="TEST", score=-0.1)

    def test_signal_score_out_of_range_high(self):
        with pytest.raises(TraceValidationError, match="score must be between"):
            Signal(disorder="TEST", score=1.5)

    def test_signal_boundary_scores(self):
        Signal(disorder="TEST", score=0.0)  # OK
        Signal(disorder="TEST", score=1.0)  # OK

    def test_signal_to_dict(self):
        signal = Signal(disorder="GI-SYCO-01", score=0.8, id="sig-1")
        d = signal.to_dict()
        assert d["disorder"] == "GI-SYCO-01"
        assert d["score"] == 0.8
        assert d["id"] == "sig-1"

    def test_signal_from_dict(self):
        signal = Signal.from_dict({"disorder": "SEC-INJ-01", "score": 0.3})
        assert signal.disorder == "SEC-INJ-01"
        assert signal.score == 0.3

    def test_signal_from_dict_missing_disorder(self):
        with pytest.raises(
            TraceValidationError, match="missing required field 'disorder'"
        ):
            Signal.from_dict({"score": 0.5})

    def test_signal_from_dict_missing_score(self):
        with pytest.raises(
            TraceValidationError, match="missing required field 'score'"
        ):
            Signal.from_dict({"disorder": "TEST"})


class TestDiagnosis:
    def test_create_diagnosis(self):
        diagnosis = Diagnosis()
        assert diagnosis.signals == []
        assert diagnosis.summary == ""
        assert diagnosis.ts
        assert diagnosis.id

    def test_diagnosis_with_signals(self):
        signals = [
            Signal(disorder="GI-SYCO-01", score=0.8),
            Signal(disorder="GI-DRFT-01", score=0.3),
        ]
        diagnosis = Diagnosis(signals=signals, summary="Sycophancy detected")
        assert len(diagnosis.signals) == 2
        assert diagnosis.has_signals is True
        assert diagnosis.max_score == 0.8

    def test_diagnosis_no_signals(self):
        diagnosis = Diagnosis()
        assert diagnosis.has_signals is False
        assert diagnosis.max_score == 0.0

    def test_diagnosis_to_dict(self):
        signal = Signal(disorder="TEST", score=0.5)
        diagnosis = Diagnosis(signals=[signal], summary="Test", model="gpt-4")
        d = diagnosis.to_dict()
        assert len(d["signals"]) == 1
        assert d["summary"] == "Test"
        assert d["model"] == "gpt-4"

    def test_diagnosis_from_dict(self):
        data = {
            "signals": [{"disorder": "TEST", "score": 0.5}],
            "summary": "Analysis complete",
            "model": "claude-3",
        }
        diagnosis = Diagnosis.from_dict(data)
        assert len(diagnosis.signals) == 1
        assert diagnosis.signals[0].disorder == "TEST"
        assert diagnosis.summary == "Analysis complete"


class TestTrace:
    def test_create_trace(self):
        trace = Trace()
        assert trace.events == []
        assert trace.model == ""
        assert trace.capture_mode == "full"
        assert trace.ts
        assert trace.id

    def test_trace_with_events(self):
        events = [
            Event(kind="model_call", ts="2026-01-01T00:00:00Z"),
            Event(kind="tool_use", ts="2026-01-01T00:00:01Z"),
        ]
        trace = Trace(events=events, model="gpt-4", capture_mode="sample")
        assert len(trace.events) == 2
        assert trace.model == "gpt-4"
        assert trace.capture_mode == "sample"

    def test_trace_add_event(self):
        trace = Trace()
        event = Event(kind="observation", ts="2026-01-01T00:00:00Z")
        trace.add_event(event)
        assert len(trace.events) == 1
        assert trace.events[0] is event

    def test_trace_invalid_capture_mode(self):
        with pytest.raises(TraceValidationError, match="Invalid capture_mode"):
            Trace(capture_mode="invalid")

    def test_trace_valid_capture_modes(self):
        Trace(capture_mode="full")
        Trace(capture_mode="sample")
        Trace(capture_mode="summary")

    def test_trace_with_diagnosis(self):
        diagnosis = Diagnosis(signals=[Signal(disorder="TEST", score=0.5)])
        trace = Trace(diagnosis=diagnosis)
        assert trace.diagnosis is not None
        assert trace.diagnosis.signals[0].disorder == "TEST"

    def test_trace_to_dict(self):
        event = Event(kind="model_call", ts="2026-01-01T00:00:00Z")
        trace = Trace(events=[event], model="test-model", metadata={"key": "value"})
        d = trace.to_dict()
        assert len(d["events"]) == 1
        assert d["model"] == "test-model"
        assert d["metadata"] == {"key": "value"}

    def test_trace_from_dict(self):
        data = {
            "events": [{"kind": "model_call", "ts": "2026-01-01T00:00:00Z"}],
            "model": "claude-3",
            "capture_mode": "summary",
        }
        trace = Trace.from_dict(data)
        assert len(trace.events) == 1
        assert trace.model == "claude-3"
        assert trace.capture_mode == "summary"

    def test_trace_from_dict_with_diagnosis(self):
        data = {
            "events": [],
            "diagnosis": {"signals": [{"disorder": "TEST", "score": 0.9}]},
        }
        trace = Trace.from_dict(data)
        assert trace.diagnosis is not None
        assert trace.diagnosis.signals[0].score == 0.9


class TestTraceHeader:
    def test_create_header(self):
        header = TraceHeader()
        assert header.schema_version == SCHEMA_VERSION
        assert header.ts
        assert header.model == ""
        assert header.capture_mode == "full"

    def test_header_to_dict(self):
        header = TraceHeader(model="gpt-4", capture_mode="sample")
        d = header.to_dict()
        assert d["schema_version"] == SCHEMA_VERSION
        assert d["model"] == "gpt-4"
        assert d["capture_mode"] == "sample"

    def test_header_from_dict(self):
        data = {"schema_version": SCHEMA_VERSION, "model": "test"}
        header = TraceHeader.from_dict(data)
        assert header.model == "test"

    def test_header_missing_version(self):
        with pytest.raises(
            TraceValidationError, match="missing required field 'schema_version'"
        ):
            TraceHeader.from_dict({})

    def test_header_wrong_version(self):
        with pytest.raises(TraceValidationError, match="Unsupported schema version"):
            TraceHeader.from_dict({"schema_version": "unknown.v99"})


class TestJSONLRoundTrip:
    def test_write_and_read_jsonl(self, tmp_path):
        events = [
            Event(kind="model_call", ts="2026-01-01T00:00:00Z", data={"prompt": "Hi"}),
            Event(kind="tool_use", ts="2026-01-01T00:00:01Z", data={"tool": "search"}),
        ]
        trace = Trace(events=events, model="gpt-4", capture_mode="full")

        path = tmp_path / "trace.jsonl"
        write_jsonl(path, trace)

        loaded = read_jsonl(path)
        assert len(loaded.events) == 2
        assert loaded.model == "gpt-4"
        assert loaded.capture_mode == "full"
        assert loaded.events[0].kind == "model_call"
        assert loaded.events[1].data["tool"] == "search"

    def test_write_and_read_stream(self):
        events = [Event(kind="observation", ts="2026-01-01T00:00:00Z")]
        trace = Trace(events=events, model="claude-3")

        buffer = io.StringIO()
        write_jsonl_stream(buffer, trace)

        buffer.seek(0)
        loaded = read_jsonl_stream(buffer)
        assert len(loaded.events) == 1
        assert loaded.model == "claude-3"

    def test_roundtrip_preserves_data(self, tmp_path):
        original = Trace(
            events=[
                Event(
                    kind="model_call",
                    ts="2026-01-01T00:00:00Z",
                    data={"nested": {"deep": [1, 2, 3]}},
                )
            ],
            model="test-model",
            capture_mode="sample",
            metadata={"session": "abc123"},
        )

        path = tmp_path / "trace.jsonl"
        write_jsonl(path, original)
        loaded = read_jsonl(path)

        assert loaded.events[0].data["nested"]["deep"] == [1, 2, 3]
        # Note: metadata is not preserved in JSONL header (only in full Trace)

    def test_empty_trace_roundtrip(self, tmp_path):
        trace = Trace()
        path = tmp_path / "empty.jsonl"
        write_jsonl(path, trace)
        loaded = read_jsonl(path)
        assert loaded.events == []

    def test_iter_events(self, tmp_path):
        events = [
            Event(kind="model_call", ts="2026-01-01T00:00:00Z"),
            Event(kind="tool_use", ts="2026-01-01T00:00:01Z"),
            Event(kind="observation", ts="2026-01-01T00:00:02Z"),
        ]
        trace = Trace(events=events)

        path = tmp_path / "trace.jsonl"
        write_jsonl(path, trace)

        iterated = list(iter_events(path))
        assert len(iterated) == 3
        assert iterated[0].kind == "model_call"
        assert iterated[2].kind == "observation"


class TestJSONLMalformedInput:
    def test_read_empty_file(self, tmp_path):
        path = tmp_path / "empty.jsonl"
        path.write_text("")
        with pytest.raises(TraceParseError, match="Empty file"):
            read_jsonl(path)

    def test_read_nonexistent_file(self, tmp_path):
        path = tmp_path / "nonexistent.jsonl"
        with pytest.raises(TraceParseError, match="File not found"):
            read_jsonl(path)

    def test_read_invalid_json_header(self, tmp_path):
        path = tmp_path / "bad.jsonl"
        path.write_text("not valid json\n")
        with pytest.raises(TraceParseError, match="Invalid JSON in header"):
            read_jsonl(path)

    def test_read_missing_schema_version(self, tmp_path):
        path = tmp_path / "bad.jsonl"
        path.write_text('{"model": "test"}\n')
        with pytest.raises(TraceValidationError, match="missing required field"):
            read_jsonl(path)

    def test_read_wrong_schema_version(self, tmp_path):
        path = tmp_path / "bad.jsonl"
        path.write_text('{"schema_version": "old.v0"}\n')
        with pytest.raises(TraceValidationError, match="Unsupported schema version"):
            read_jsonl(path)

    def test_read_invalid_event_json(self, tmp_path):
        path = tmp_path / "bad.jsonl"
        path.write_text(f'{{"schema_version": "{SCHEMA_VERSION}"}}\nnot json\n')
        with pytest.raises(TraceParseError, match="Line 2.*Invalid JSON"):
            read_jsonl(path)

    def test_read_event_missing_kind(self, tmp_path):
        path = tmp_path / "bad.jsonl"
        path.write_text(
            f'{{"schema_version": "{SCHEMA_VERSION}"}}\n{{"ts": "2026-01-01"}}\n'
        )
        with pytest.raises(TraceParseError, match="Line 2.*missing required field"):
            read_jsonl(path)

    def test_read_event_invalid_kind(self, tmp_path):
        path = tmp_path / "bad.jsonl"
        path.write_text(
            f'{{"schema_version": "{SCHEMA_VERSION}"}}\n'
            f'{{"kind": "bad_kind", "ts": "2026-01-01"}}\n'
        )
        with pytest.raises(TraceParseError, match="Line 2.*Invalid event kind"):
            read_jsonl(path)

    def test_iter_events_malformed(self, tmp_path):
        path = tmp_path / "bad.jsonl"
        path.write_text(
            f'{{"schema_version": "{SCHEMA_VERSION}"}}\n'
            f'{{"kind": "model_call", "ts": "2026-01-01"}}\n'
            f"bad json\n"
        )
        events = iter_events(path)
        next(events)  # First event OK
        with pytest.raises(TraceParseError, match="Line 3.*Invalid JSON"):
            next(events)


class TestValidation:
    def test_validate_trace_valid(self):
        trace = Trace(
            events=[Event(kind="model_call", ts="2026-01-01T00:00:00Z")],
            capture_mode="full",
        )
        issues = validate_trace(trace)
        assert issues == []

    def test_validate_trace_missing_ts(self):
        trace = Trace(ts="")
        issues = validate_trace(trace)
        assert "Trace missing timestamp" in issues[0]

    def test_validate_trace_diagnosis_bad_score(self):
        # Create trace then manually set bad score to bypass __post_init__
        signal = Signal.__new__(Signal)
        signal.disorder = "TEST"
        signal.score = 1.5  # Invalid
        signal.evidence = []
        signal.details = {}
        signal.id = "test"

        diagnosis = Diagnosis(signals=[signal])
        trace = Trace(diagnosis=diagnosis)
        issues = validate_trace(trace)
        assert any("score" in i and "out of range" in i for i in issues)

    def test_validate_jsonl_valid(self, tmp_path):
        trace = Trace(events=[Event(kind="model_call", ts="2026-01-01T00:00:00Z")])
        path = tmp_path / "valid.jsonl"
        write_jsonl(path, trace)

        issues = validate_jsonl(path)
        assert issues == []

    def test_validate_jsonl_missing_file(self, tmp_path):
        path = tmp_path / "missing.jsonl"
        issues = validate_jsonl(path)
        assert "File not found" in issues[0]

    def test_validate_jsonl_empty(self, tmp_path):
        path = tmp_path / "empty.jsonl"
        path.write_text("")
        issues = validate_jsonl(path)
        assert "Empty file" in issues[0]

    def test_validate_jsonl_bad_header(self, tmp_path):
        path = tmp_path / "bad.jsonl"
        path.write_text('{"no_version": true}\n')
        issues = validate_jsonl(path)
        assert any("schema_version" in i for i in issues)

    def test_validate_jsonl_mixed_errors(self, tmp_path):
        path = tmp_path / "mixed.jsonl"
        path.write_text(
            f'{{"schema_version": "{SCHEMA_VERSION}"}}\n'
            f'{{"kind": "model_call", "ts": "ok"}}\n'
            f'{{"kind": "bad", "ts": "ok"}}\n'
            f'{{"kind": "tool_use"}}\n'
        )
        issues = validate_jsonl(path)
        assert len(issues) == 2  # bad kind + missing ts
        assert any("Line 3" in i and "Invalid event kind" in i for i in issues)
        assert any("Line 4" in i and "missing required field 'ts'" in i for i in issues)


class TestSchemaVersion:
    def test_schema_version_constant(self):
        assert SCHEMA_VERSION == "ghostline.v1"

    def test_header_uses_schema_version(self):
        header = TraceHeader()
        assert header.schema_version == "ghostline.v1"

    def test_written_file_has_version(self, tmp_path):
        trace = Trace()
        path = tmp_path / "trace.jsonl"
        write_jsonl(path, trace)

        with path.open() as f:
            header = json.loads(f.readline())
        assert header["schema_version"] == "ghostline.v1"
