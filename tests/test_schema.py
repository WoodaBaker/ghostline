"""Tests for ghostline.v1 schema contract.

Covers: Event, Trace, Signal, Diagnosis, Finding, JSONL serialization,
KIRU TelemetryEvent mapping, streaming, unknown fields/types round-trip,
version handling, error cases.
"""

import json
import locale
import warnings

import pytest

from kiru_ghostline import (
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
from kiru_ghostline.findings import Finding


class TestEventType:
    def test_all_event_types(self):
        assert EventType.PROMPT_STARTED.value == "prompt_started"
        assert EventType.RESPONSE_RECEIVED.value == "response_received"
        assert EventType.TOOL_CALLED.value == "tool_called"
        assert EventType.TOOL_RESULT.value == "tool_result"
        assert EventType.SESSION_CLOSED.value == "session_closed"
        assert EventType.OBJECTIVE_SET.value == "objective_set"
        assert EventType.CUSTOM.value == "custom"


class TestCaptureMode:
    def test_all_capture_modes(self):
        assert CaptureMode.METADATA_ONLY.value == "metadata_only"
        assert CaptureMode.PARTIAL_PAYLOAD.value == "partial_payload"
        assert CaptureMode.FULL_PAYLOAD.value == "full_payload"


class TestVerdict:
    def test_all_verdicts(self):
        assert Verdict.CLEAN.value == "clean"
        assert Verdict.SIGNAL.value == "signal"
        assert Verdict.INCONCLUSIVE.value == "inconclusive"


class TestSignalSource:
    def test_all_signal_sources(self):
        assert SignalSource.DETECTOR.value == "detector"
        assert SignalSource.BATTERY.value == "battery"
        assert SignalSource.CHECKER.value == "checker"
        assert SignalSource.JUDGE.value == "judge"


class TestModelRef:
    def test_create_model_ref(self):
        model = ModelRef(provider="openai", name="gpt-4")
        assert model.provider == "openai"
        assert model.name == "gpt-4"
        assert model.params == {}

    def test_model_ref_with_params(self):
        model = ModelRef(
            provider="anthropic", name="claude-3", params={"temperature": 0.7}
        )
        assert model.params["temperature"] == 0.7

    def test_model_ref_to_dict(self):
        model = ModelRef(provider="openai", name="gpt-4", params={"max_tokens": 100})
        d = model.to_dict()
        assert d == {
            "provider": "openai",
            "name": "gpt-4",
            "params": {"max_tokens": 100},
        }

    def test_model_ref_from_dict(self):
        model = ModelRef.from_dict({"provider": "openai", "name": "gpt-4"})
        assert model.provider == "openai"
        assert model.name == "gpt-4"

    def test_model_ref_from_dict_missing_provider(self):
        with pytest.raises(
            TraceValidationError, match="missing required field 'provider'"
        ):
            ModelRef.from_dict({"name": "gpt-4"})

    def test_model_ref_from_dict_missing_name(self):
        with pytest.raises(TraceValidationError, match="missing required field 'name'"):
            ModelRef.from_dict({"provider": "openai"})


class TestEvent:
    def test_create_event(self):
        event = Event(
            event_id="test-uuid",
            event_type=EventType.PROMPT_STARTED,
            ts="2026-01-01T00:00:00Z",
            session_key="session-123",
            payload={"messages": [{"role": "user", "content": "Hello"}]},
        )
        assert event.event_id == "test-uuid"
        assert event.event_type == EventType.PROMPT_STARTED
        assert event.session_key == "session-123"
        assert event.idempotency_key == ""
        assert event.agent_label == ""
        assert event.seq is None
        assert event.model is None
        assert event.capture_mode == CaptureMode.PARTIAL_PAYLOAD
        assert event.metadata == {}

    def test_event_create_helper(self):
        event = Event.create(
            EventType.TOOL_CALLED,
            "session-abc",
            payload={"tool": {"name": "search", "args": {"q": "test"}}},
        )
        assert event.event_id  # UUID generated
        assert event.ts  # Timestamp generated
        assert event.ts.endswith("Z")
        assert event.session_key == "session-abc"

    def test_event_session_key_max_length(self):
        with pytest.raises(TraceValidationError, match="session_key exceeds 120"):
            Event(
                event_id="test",
                event_type=EventType.CUSTOM,
                ts="2026-01-01T00:00:00Z",
                session_key="x" * 121,
                payload={},
            )

    def test_event_idempotency_key_max_length(self):
        with pytest.raises(TraceValidationError, match="idempotency_key exceeds 128"):
            Event(
                event_id="test",
                event_type=EventType.CUSTOM,
                ts="2026-01-01T00:00:00Z",
                session_key="session",
                payload={},
                idempotency_key="x" * 129,
            )

    def test_event_agent_label_max_length(self):
        with pytest.raises(TraceValidationError, match="agent_label exceeds 120"):
            Event(
                event_id="test",
                event_type=EventType.CUSTOM,
                ts="2026-01-01T00:00:00Z",
                session_key="session",
                payload={},
                agent_label="x" * 121,
            )

    def test_event_invalid_timestamp(self):
        with pytest.raises(TraceValidationError, match="Invalid RFC3339"):
            Event(
                event_id="test",
                event_type=EventType.CUSTOM,
                ts="not-a-timestamp",
                session_key="session",
                payload={},
            )

    def test_event_to_dict(self):
        event = Event(
            event_id="test-uuid",
            event_type=EventType.RESPONSE_RECEIVED,
            ts="2026-01-01T00:00:00Z",
            session_key="session-123",
            payload={"response": "Hello!"},
            idempotency_key="idem-123",
            seq=5,
            capture_mode=CaptureMode.FULL_PAYLOAD,
        )
        d = event.to_dict()
        assert d["event_id"] == "test-uuid"
        assert d["event_type"] == "response_received"
        assert d["session_key"] == "session-123"
        assert d["idempotency_key"] == "idem-123"
        assert d["seq"] == 5
        assert d["capture_mode"] == "full_payload"

    def test_event_to_dict_omits_defaults(self):
        event = Event(
            event_id="test",
            event_type=EventType.CUSTOM,
            ts="2026-01-01T00:00:00Z",
            session_key="session",
            payload={},
        )
        d = event.to_dict()
        assert "idempotency_key" not in d
        assert "agent_label" not in d
        assert "seq" not in d
        assert "model" not in d
        assert "capture_mode" in d
        assert "metadata" not in d

    def test_event_from_dict(self):
        event = Event.from_dict(
            {
                "event_id": "test-uuid",
                "event_type": "tool_called",
                "ts": "2026-01-01T00:00:00Z",
                "session_key": "session-123",
                "payload": {"tool": {"name": "search"}},
            }
        )
        assert event.event_type == EventType.TOOL_CALLED
        assert event.payload["tool"]["name"] == "search"

    def test_event_from_dict_with_model(self):
        event = Event.from_dict(
            {
                "event_id": "test",
                "event_type": "prompt_started",
                "ts": "2026-01-01T00:00:00Z",
                "session_key": "session",
                "payload": {},
                "model": {"provider": "openai", "name": "gpt-4"},
            }
        )
        assert event.model is not None
        assert event.model.provider == "openai"

    def test_event_from_dict_missing_required(self):
        with pytest.raises(TraceValidationError, match="missing required fields"):
            Event.from_dict({"event_id": "test"})

    def test_event_from_dict_invalid_capture_mode(self):
        with pytest.raises(TraceValidationError, match="Invalid capture_mode"):
            Event.from_dict(
                {
                    "event_id": "test",
                    "event_type": "custom",
                    "ts": "2026-01-01T00:00:00Z",
                    "session_key": "session",
                    "payload": {},
                    "capture_mode": "invalid",
                }
            )

    def test_event_from_dict_non_dict(self):
        with pytest.raises(TraceValidationError, match="must be a dict"):
            Event.from_dict("not a dict")

    def test_event_objective_set(self):
        event = Event.create(
            EventType.OBJECTIVE_SET,
            "session",
            payload={"objective": "Find the answer to life"},
        )
        assert event.event_type == EventType.OBJECTIVE_SET
        assert event.payload["objective"] == "Find the answer to life"


class TestEventUnknownType:
    def test_unknown_event_type_roundtrip(self):
        """Unknown event_type kept as custom, raw string preserved."""
        data = {
            "event_id": "test",
            "event_type": "future_event_type",
            "ts": "2026-01-01T00:00:00Z",
            "session_key": "session",
            "payload": {},
        }
        event = Event.from_dict(data)
        assert event.event_type == EventType.CUSTOM
        assert event._raw_event_type == "future_event_type"

        d = event.to_dict()
        assert d["event_type"] == "future_event_type"


class TestEventUnknownFields:
    def test_unknown_fields_roundtrip(self):
        """Unknown fields preserved in round-trip."""
        data = {
            "event_id": "test",
            "event_type": "custom",
            "ts": "2026-01-01T00:00:00Z",
            "session_key": "session",
            "payload": {},
            "future_field": "preserved",
            "another_unknown": {"nested": True},
        }
        event = Event.from_dict(data)
        d = event.to_dict()
        assert d["future_field"] == "preserved"
        assert d["another_unknown"] == {"nested": True}


class TestTrace:
    def test_create_trace(self):
        trace = Trace.create("session-123")
        assert trace.trace_id  # UUID generated
        assert trace.created_at.endswith("Z")
        assert trace.producer.startswith("kiru-ghostline/")
        assert trace.schema_version == SCHEMA_VERSION
        assert trace.session_key == "session-123"
        assert trace.events == []

    def test_trace_add_event(self):
        trace = Trace.create("session")
        event = Event.create(EventType.PROMPT_STARTED, "session", {})
        trace.add_event(event)
        assert len(trace.events) == 1
        assert trace.events[0] is event

    def test_trace_objective_from_event(self):
        trace = Trace.create("session")
        event = Event.create(
            EventType.OBJECTIVE_SET,
            "session",
            {"objective": "Complete the task"},
        )
        trace.add_event(event)
        assert trace.objective == "Complete the task"

    def test_trace_capture_mode_upgrade(self):
        trace = Trace.create("session", capture_mode=CaptureMode.METADATA_ONLY)
        event = Event.create(
            EventType.CUSTOM,
            "session",
            {},
            capture_mode=CaptureMode.FULL_PAYLOAD,
        )
        trace.add_event(event)
        assert trace.capture_mode == CaptureMode.FULL_PAYLOAD

    def test_trace_to_dict(self):
        trace = Trace(
            trace_id="trace-123",
            created_at="2026-01-01T00:00:00Z",
            producer="test/1.0",
            capture_mode=CaptureMode.PARTIAL_PAYLOAD,
            session_key="session",
            objective="Test objective",
        )
        d = trace.to_dict()
        assert d["schema_version"] == SCHEMA_VERSION
        assert d["trace_id"] == "trace-123"
        assert d["session_key"] == "session"
        assert d["objective"] == "Test objective"
        assert d["events"] == []

    def test_trace_from_dict(self):
        trace = Trace.from_dict(
            {
                "schema_version": SCHEMA_VERSION,
                "trace_id": "trace-123",
                "created_at": "2026-01-01T00:00:00Z",
                "producer": "test/1.0",
                "capture_mode": "full_payload",
                "events": [
                    {
                        "event_id": "e1",
                        "event_type": "custom",
                        "ts": "2026-01-01T00:00:01Z",
                        "session_key": "session",
                        "payload": {},
                    }
                ],
            }
        )
        assert trace.trace_id == "trace-123"
        assert trace.capture_mode == CaptureMode.FULL_PAYLOAD
        assert len(trace.events) == 1

    def test_trace_from_dict_missing_required(self):
        with pytest.raises(TraceValidationError, match="missing required fields"):
            Trace.from_dict({"trace_id": "test"})


class TestSignal:
    def test_create_signal(self):
        signal = Signal(
            code="GI-SYCO-01",
            confidence=0.85,
            source=SignalSource.BATTERY,
            producer="sycophancy-flip",
            explanation="Flip detected in 4/5 questions",
        )
        assert signal.code == "GI-SYCO-01"
        assert signal.confidence == 0.85
        assert signal.source == SignalSource.BATTERY

    def test_signal_invalid_code_format(self):
        with pytest.raises(TraceValidationError, match="Invalid DEM-X code"):
            Signal(
                code="invalid",
                confidence=0.5,
                source=SignalSource.CHECKER,
                producer="test",
                explanation="test",
            )

    def test_signal_confidence_out_of_range(self):
        with pytest.raises(TraceValidationError, match="must be between 0.0 and 1.0"):
            Signal(
                code="GI-DRFT-01",
                confidence=1.5,
                source=SignalSource.JUDGE,
                producer="test",
                explanation="test",
            )

    def test_signal_detector_requires_evidence(self):
        with pytest.raises(TraceValidationError, match="requires non-empty evidence"):
            Signal(
                code="SEC-INJ-01",
                confidence=0.9,
                source=SignalSource.DETECTOR,
                producer="test",
                explanation="test",
                evidence_event_ids=[],
            )

    def test_signal_detector_with_evidence(self):
        signal = Signal(
            code="SEC-INJ-01",
            confidence=0.9,
            source=SignalSource.DETECTOR,
            producer="injection-detector",
            explanation="Injection detected",
            evidence_event_ids=["event-1", "event-2"],
        )
        assert len(signal.evidence_event_ids) == 2

    def test_signal_to_dict(self):
        signal = Signal(
            code="GI-SYCO-01",
            confidence=0.75,
            source=SignalSource.BATTERY,
            producer="test",
            explanation="Test explanation",
            score=0.8,
            level=2,
        )
        d = signal.to_dict()
        assert d["code"] == "GI-SYCO-01"
        assert d["confidence"] == 0.75
        assert d["source"] == "battery"
        assert d["score"] == 0.8
        assert d["level"] == 2

    def test_signal_from_dict(self):
        signal = Signal.from_dict(
            {
                "code": "MEM-COR-01",
                "confidence": 0.6,
                "source": "checker",
                "producer": "context-checker",
                "explanation": "Context corruption detected",
            }
        )
        assert signal.code == "MEM-COR-01"
        assert signal.source == SignalSource.CHECKER

    def test_signal_from_dict_missing_required(self):
        with pytest.raises(TraceValidationError, match="missing required fields"):
            Signal.from_dict({"code": "GI-SYCO-01"})


class TestDiagnosis:
    def test_create_diagnosis(self):
        diagnosis = Diagnosis.create(
            catalog_version="dem-x/2026.1",
            ran=["sycophancy-flip", "goal-drift"],
        )
        assert diagnosis.diagnosis_id
        assert diagnosis.created_at.endswith("Z")
        assert diagnosis.verdict == Verdict.CLEAN
        assert diagnosis.ran == ["sycophancy-flip", "goal-drift"]

    def test_diagnosis_verdict_signal(self):
        signal = Signal(
            code="GI-SYCO-01",
            confidence=0.8,
            source=SignalSource.BATTERY,
            producer="test",
            explanation="test",
        )
        diagnosis = Diagnosis.create(
            catalog_version="dem-x/2026.1",
            ran=["test"],
            signals=[signal],
            threshold=0.5,
        )
        assert diagnosis.verdict == Verdict.SIGNAL

    def test_diagnosis_signals_sorted_by_confidence(self):
        signals = [
            Signal(
                code="GI-SYCO-01",
                confidence=0.3,
                source=SignalSource.BATTERY,
                producer="a",
                explanation="low",
            ),
            Signal(
                code="GI-DRFT-01",
                confidence=0.9,
                source=SignalSource.BATTERY,
                producer="b",
                explanation="high",
            ),
            Signal(
                code="SEC-INJ-01",
                confidence=0.6,
                source=SignalSource.CHECKER,
                producer="c",
                explanation="mid",
            ),
        ]
        diagnosis = Diagnosis(
            diagnosis_id="test",
            created_at="2026-01-01T00:00:00Z",
            catalog_version="test",
            verdict=Verdict.SIGNAL,
            ran=["test"],
            signals=signals,
        )
        assert diagnosis.signals[0].confidence == 0.9
        assert diagnosis.signals[1].confidence == 0.6
        assert diagnosis.signals[2].confidence == 0.3

    def test_diagnosis_to_dict(self):
        diagnosis = Diagnosis(
            diagnosis_id="diag-123",
            created_at="2026-01-01T00:00:00Z",
            catalog_version="dem-x/2026.1",
            verdict=Verdict.CLEAN,
            ran=["test"],
            calls=10,
        )
        d = diagnosis.to_dict()
        assert d["diagnosis_id"] == "diag-123"
        assert d["verdict"] == "clean"
        assert d["calls"] == 10

    def test_diagnosis_from_dict(self):
        diagnosis = Diagnosis.from_dict(
            {
                "diagnosis_id": "diag-123",
                "created_at": "2026-01-01T00:00:00Z",
                "catalog_version": "dem-x/2026.1",
                "verdict": "signal",
                "ran": ["test"],
                "signals": [
                    {
                        "code": "GI-SYCO-01",
                        "confidence": 0.8,
                        "source": "battery",
                        "producer": "test",
                        "explanation": "test",
                    }
                ],
            }
        )
        assert diagnosis.verdict == Verdict.SIGNAL
        assert len(diagnosis.signals) == 1

    def test_diagnosis_from_dict_missing_required(self):
        """from_dict must NOT invent ids/timestamps for missing required fields."""
        with pytest.raises(TraceValidationError, match="missing required fields"):
            Diagnosis.from_dict(
                {
                    "catalog_version": "test",
                    "verdict": "clean",
                    "ran": [],
                }
            )


class TestFinding:
    def test_create_finding(self):
        finding = Finding(
            observed_behavior="Agent flipped on sycophancy test",
            catalog_version="dem-x/2026.1",
        )
        assert finding.id
        assert finding.schema_version == "ghostline.v1"
        assert finding.observed_behavior == "Agent flipped on sycophancy test"

    def test_finding_to_dict(self):
        finding = Finding(
            observed_behavior="Test behavior",
            catalog_version="dem-x/2026.1",
            model="gpt-4",
            suspected_disorder="GI-SYCO-01",
        )
        d = finding.to_dict()
        assert d["observed_behavior"] == "Test behavior"
        assert d["catalog_version"] == "dem-x/2026.1"
        assert d["model"] == "gpt-4"
        assert d["suspected_disorder"] == "GI-SYCO-01"

    def test_finding_from_dict(self):
        finding = Finding.from_dict(
            {
                "observed_behavior": "Test",
                "catalog_version": "test/1.0",
            }
        )
        assert finding.observed_behavior == "Test"
        assert finding.catalog_version == "test/1.0"

    def test_finding_from_dict_missing_required(self):
        with pytest.raises(ValueError, match="missing required field"):
            Finding.from_dict({"model": "test"})


class TestJSONLWriteRead:
    def test_write_and_read_jsonl(self, tmp_path):
        trace = Trace.create("session-123")
        event = Event.create(EventType.PROMPT_STARTED, "session-123", {"messages": []})
        trace.add_event(event)

        path = tmp_path / "trace.jsonl"
        write_jsonl(path, trace)

        loaded = read_jsonl(path)
        assert loaded.trace_id == trace.trace_id
        assert loaded.session_key == "session-123"
        assert len(loaded.events) == 1
        assert loaded.events[0].event_type == EventType.PROMPT_STARTED

    def test_write_creates_directories(self, tmp_path):
        trace = Trace.create("session")
        path = tmp_path / "deep" / "nested" / "trace.jsonl"
        write_jsonl(path, trace)
        assert path.exists()

    def test_jsonl_format(self, tmp_path):
        trace = Trace.create("session")
        event = Event.create(EventType.CUSTOM, "session", {})
        trace.add_event(event)

        path = tmp_path / "trace.jsonl"
        write_jsonl(path, trace)

        with path.open("r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == 2
        header = json.loads(lines[0])
        assert header["kind"] == "header"
        assert header["schema_version"] == SCHEMA_VERSION

        event_line = json.loads(lines[1])
        assert event_line["kind"] == "event"
        assert event_line["event_type"] == "custom"

    def test_append_mode(self, tmp_path):
        trace = Trace.create("session")
        event1 = Event.create(EventType.PROMPT_STARTED, "session", {})
        trace.add_event(event1)

        path = tmp_path / "trace.jsonl"
        write_jsonl(path, trace)

        trace2 = Trace.create("session")
        event2 = Event.create(EventType.RESPONSE_RECEIVED, "session", {})
        trace2.add_event(event2)
        write_jsonl(path, trace2, append=True)

        loaded = read_jsonl(path)
        assert len(loaded.events) == 2

    def test_append_event(self, tmp_path):
        trace = Trace.create("session")
        path = tmp_path / "trace.jsonl"

        event1 = Event.create(EventType.PROMPT_STARTED, "session", {})
        append_event(path, event1, trace)

        event2 = Event.create(EventType.RESPONSE_RECEIVED, "session", {})
        append_event(path, event2)

        loaded = read_jsonl(path)
        assert len(loaded.events) == 2

    def test_append_event_no_trace_no_file(self, tmp_path):
        path = tmp_path / "missing.jsonl"
        event = Event.create(EventType.CUSTOM, "session", {})
        with pytest.raises(TraceValidationError, match="Cannot append"):
            append_event(path, event)

    def test_iter_events(self, tmp_path):
        trace = Trace.create("session")
        for i in range(5):
            trace.add_event(Event.create(EventType.CUSTOM, "session", {"i": i}))

        path = tmp_path / "trace.jsonl"
        write_jsonl(path, trace)

        events = list(iter_events(path))
        assert len(events) == 5
        assert events[0].payload["i"] == 0
        assert events[4].payload["i"] == 4


class TestJSONLErrors:
    def test_empty_file(self, tmp_path):
        path = tmp_path / "empty.jsonl"
        path.write_text("")
        with pytest.raises(TraceParseError, match="Empty file"):
            read_jsonl(path)

    def test_invalid_json_header(self, tmp_path):
        path = tmp_path / "bad.jsonl"
        path.write_text("not json\n", encoding="utf-8")
        with pytest.raises(TraceParseError, match="Line 1.*Invalid JSON"):
            read_jsonl(path)

    def test_missing_schema_version(self, tmp_path):
        path = tmp_path / "bad.jsonl"
        path.write_text('{"kind": "header"}\n', encoding="utf-8")
        with pytest.raises(TraceParseError, match="Line 1.*schema_version"):
            read_jsonl(path)

    def test_unsupported_major_version(self, tmp_path):
        path = tmp_path / "bad.jsonl"
        path.write_text(
            '{"kind": "header", "schema_version": "ghostline.v99"}\n', encoding="utf-8"
        )
        with pytest.raises(TraceParseError, match="Unsupported schema major"):
            read_jsonl(path)

    def test_invalid_event_json(self, tmp_path):
        """Malformed JSON not on the last line should error."""
        path = tmp_path / "bad.jsonl"
        content = (
            '{"kind": "header", "schema_version": "ghostline.v1", '
            '"trace_id": "t", "created_at": "2026-01-01T00:00:00Z", '
            '"producer": "test", "capture_mode": "full_payload"}\n'
            "not json\n"
            '{"kind": "event", "event_id": "e1", "event_type": "custom", '
            '"ts": "2026-01-01T00:00:01Z", "session_key": "s", "payload": {}}\n'
        )
        path.write_text(content, encoding="utf-8")
        with pytest.raises(TraceParseError, match="Malformed line"):
            read_jsonl(path)

    def test_non_object_json_line(self, tmp_path):
        """Non-object JSON lines => TraceParseError with line number."""
        path = tmp_path / "bad.jsonl"
        content = (
            '{"kind": "header", "schema_version": "ghostline.v1", '
            '"trace_id": "t", "created_at": "2026-01-01T00:00:00Z", '
            '"producer": "test", "capture_mode": "full_payload"}\n'
            '"just a string"\n'
        )
        path.write_text(content, encoding="utf-8")
        with pytest.raises(TraceParseError, match="Line 2.*Expected JSON object"):
            read_jsonl(path)

    def test_non_object_header(self, tmp_path):
        """Non-object header => TraceParseError."""
        path = tmp_path / "bad.jsonl"
        path.write_text('["array", "not", "object"]\n', encoding="utf-8")
        with pytest.raises(TraceParseError, match="Line 1.*Expected JSON object"):
            read_jsonl(path)

    def test_truncated_last_line_ignored(self, tmp_path):
        """Truncated LAST line => warnings.warn, ignored."""
        path = tmp_path / "truncated.jsonl"
        content = (
            '{"kind": "header", "schema_version": "ghostline.v1", '
            '"trace_id": "t", "created_at": "2026-01-01T00:00:00Z", '
            '"producer": "test", "capture_mode": "full_payload"}\n'
            '{"kind": "event", "event_id": "e1", "event_type": "custom", '
            '"ts": "2026-01-01T00:00:01Z", "session_key": "s", "payload": {}}\n'
            '{"kind": "event", "event_id":'  # truncated
        )
        path.write_text(content, encoding="utf-8")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            trace = read_jsonl(path)
            assert len(w) == 1
            assert "Truncated last line" in str(w[0].message)

        assert len(trace.events) == 1

    def test_truncated_non_last_line_error(self, tmp_path):
        """Truncated line that's NOT last => error."""
        path = tmp_path / "bad.jsonl"
        content = (
            '{"kind": "header", "schema_version": "ghostline.v1", '
            '"trace_id": "t", "created_at": "2026-01-01T00:00:00Z", '
            '"producer": "test", "capture_mode": "full_payload"}\n'
            '{"kind": "event", truncated\n'
            '{"kind": "event", "event_id": "e2", "event_type": "custom", '
            '"ts": "2026-01-01T00:00:01Z", "session_key": "s", "payload": {}}\n'
        )
        path.write_text(content, encoding="utf-8")
        with pytest.raises(TraceParseError, match="Malformed line"):
            read_jsonl(path)

    def test_blank_lines_skipped(self, tmp_path):
        path = tmp_path / "blank.jsonl"
        content = (
            '{"kind": "header", "schema_version": "ghostline.v1", '
            '"trace_id": "t", "created_at": "2026-01-01T00:00:00Z", '
            '"producer": "test", "capture_mode": "full_payload"}\n'
            "\n"
            "   \n"
            '{"kind": "event", "event_id": "e1", "event_type": "custom", '
            '"ts": "2026-01-01T00:00:01Z", "session_key": "s", "payload": {}}\n'
        )
        path.write_text(content, encoding="utf-8")
        trace = read_jsonl(path)
        assert len(trace.events) == 1


class TestVersioning:
    def test_current_version(self):
        assert SCHEMA_VERSION == "ghostline.v1"

    def test_previous_major_version_accepted(self, tmp_path):
        """Previous major version (v0) accepted."""
        path = tmp_path / "v0.jsonl"
        content = (
            '{"kind": "header", "schema_version": "ghostline.v0", '
            '"trace_id": "t", "created_at": "2026-01-01T00:00:00Z", '
            '"producer": "test", "capture_mode": "full_payload"}\n'
        )
        path.write_text(content, encoding="utf-8")
        trace = read_jsonl(path)
        assert trace.schema_version == "ghostline.v0"

    def test_write_always_uses_current_schema_version(self, tmp_path):
        """write_jsonl always writes SCHEMA_VERSION even when Trace read from v0."""
        v0_path = tmp_path / "v0_input.jsonl"
        content = (
            '{"kind": "header", "schema_version": "ghostline.v0", '
            '"trace_id": "t", "created_at": "2026-01-01T00:00:00Z", '
            '"producer": "test", "capture_mode": "full_payload"}\n'
            '{"kind": "event", "event_id": "e1", "event_type": "custom", '
            '"ts": "2026-01-01T00:00:01Z", "session_key": "s", "payload": {}}\n'
        )
        v0_path.write_text(content, encoding="utf-8")
        trace = read_jsonl(v0_path)
        assert trace.schema_version == "ghostline.v0"

        v1_path = tmp_path / "v1_output.jsonl"
        write_jsonl(v1_path, trace)

        with v1_path.open("r", encoding="utf-8") as f:
            header_line = json.loads(f.readline())
        assert header_line["schema_version"] == SCHEMA_VERSION
        assert header_line["schema_version"] == "ghostline.v1"

    def test_unknown_major_version_rejected(self, tmp_path):
        path = tmp_path / "v99.jsonl"
        content = '{"kind": "header", "schema_version": "ghostline.v99"}\n'
        path.write_text(content, encoding="utf-8")
        with pytest.raises(TraceParseError, match="Unsupported schema major"):
            read_jsonl(path)

    def test_leading_zero_version_rejected(self, tmp_path):
        """Leading zeros in version number rejected (ghostline.v01)."""
        path = tmp_path / "v01.jsonl"
        content = '{"kind": "header", "schema_version": "ghostline.v01"}\n'
        path.write_text(content, encoding="utf-8")
        with pytest.raises(TraceParseError, match="Invalid schema version format"):
            read_jsonl(path)

    def test_unknown_fields_roundtrip(self, tmp_path):
        """Unknown fields preserved in round-trip."""
        path = tmp_path / "unknown.jsonl"
        content = (
            '{"kind": "header", "schema_version": "ghostline.v1", '
            '"trace_id": "t", "created_at": "2026-01-01T00:00:00Z", '
            '"producer": "test", "capture_mode": "full_payload", '
            '"future_field": "preserved"}\n'
            '{"kind": "event", "event_id": "e1", "event_type": "custom", '
            '"ts": "2026-01-01T00:00:01Z", "session_key": "s", "payload": {}, '
            '"unknown_event_field": 42}\n'
        )
        path.write_text(content, encoding="utf-8")
        trace = read_jsonl(path)
        assert trace._extra_fields["future_field"] == "preserved"
        assert trace.events[0]._extra_fields["unknown_event_field"] == 42

        out_path = tmp_path / "out.jsonl"
        write_jsonl(out_path, trace)
        trace2 = read_jsonl(out_path)
        assert trace2._extra_fields["future_field"] == "preserved"
        assert trace2.events[0]._extra_fields["unknown_event_field"] == 42

    def test_unknown_event_type_roundtrip(self, tmp_path):
        """Unknown event_type preserved in round-trip."""
        path = tmp_path / "unknown_type.jsonl"
        content = (
            '{"kind": "header", "schema_version": "ghostline.v1", '
            '"trace_id": "t", "created_at": "2026-01-01T00:00:00Z", '
            '"producer": "test", "capture_mode": "full_payload"}\n'
            '{"kind": "event", "event_id": "e1", "event_type": "future_type", '
            '"ts": "2026-01-01T00:00:01Z", "session_key": "s", "payload": {}}\n'
        )
        path.write_text(content, encoding="utf-8")
        trace = read_jsonl(path)
        assert trace.events[0].event_type == EventType.CUSTOM
        assert trace.events[0]._raw_event_type == "future_type"

        out_path = tmp_path / "out.jsonl"
        write_jsonl(out_path, trace)
        with out_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        event_line = json.loads(lines[1])
        assert event_line["event_type"] == "future_type"


class TestValidateJSONL:
    def test_validate_valid_file(self, tmp_path):
        trace = Trace.create("session")
        trace.add_event(Event.create(EventType.CUSTOM, "session", {}))
        path = tmp_path / "valid.jsonl"
        write_jsonl(path, trace)

        issues = validate_jsonl(path)
        assert issues == []

    def test_validate_missing_file(self, tmp_path):
        issues = validate_jsonl(tmp_path / "missing.jsonl")
        assert any("File not found" in i for i in issues)

    def test_validate_multiple_issues(self, tmp_path):
        path = tmp_path / "bad.jsonl"
        content = (
            '{"kind": "header", "schema_version": "ghostline.v1", '
            '"trace_id": "t", "created_at": "2026-01-01T00:00:00Z", '
            '"producer": "test", "capture_mode": "full_payload"}\n'
            '{"kind": "event", "event_type": "custom"}\n'
            '{"kind": "wrong"}\n'
        )
        path.write_text(content, encoding="utf-8")
        issues = validate_jsonl(path)
        assert len(issues) >= 2


class TestKIRUMapping:
    def test_to_kiru_event(self):
        event = Event(
            event_id="e-123",
            event_type=EventType.PROMPT_STARTED,
            ts="2026-01-01T00:00:00Z",
            session_key="session-abc",
            payload={"messages": [{"role": "user", "content": "Hello"}]},
            idempotency_key="idem-key",
            agent_label="my-agent",
            seq=5,
            model=ModelRef(provider="openai", name="gpt-4"),
            capture_mode=CaptureMode.FULL_PAYLOAD,
            metadata={"custom": "data"},
        )

        kiru = to_kiru_event(event)

        assert kiru["schema_version"] == "v1"
        assert kiru["event_id"] == "e-123"
        assert kiru["event_type"] == "prompt_started"
        assert kiru["idempotency_key"] == "idem-key"
        assert kiru["session_key"] == "session-abc"
        assert kiru["agent_label"] == "my-agent"
        assert kiru["payload"] == {"messages": [{"role": "user", "content": "Hello"}]}

        assert kiru["metadata"]["ts"] == "2026-01-01T00:00:00Z"
        assert kiru["metadata"]["seq"] == 5
        assert kiru["metadata"]["model"]["provider"] == "openai"
        assert kiru["metadata"]["capture_mode"] == "full_payload"
        assert kiru["metadata"]["custom"] == "data"

    def test_to_kiru_event_preserves_unknown_type(self):
        event = Event.from_dict(
            {
                "event_id": "e",
                "event_type": "future_type",
                "ts": "2026-01-01T00:00:00Z",
                "session_key": "s",
                "payload": {},
            }
        )
        kiru = to_kiru_event(event)
        assert kiru["event_type"] == "future_type"


class TestKIRUTelemetryEventParity:
    """Verify field parity with KIRU TelemetryEvent contract."""

    def test_required_kiru_fields_present(self):
        event = Event.create(EventType.CUSTOM, "session", {})
        kiru = to_kiru_event(event)

        required = {
            "event_id",
            "event_type",
            "idempotency_key",
            "session_key",
            "agent_label",
            "payload",
            "metadata",
        }
        assert required <= set(kiru.keys())

    def test_all_kiru_fields_have_values(self):
        event = Event.create(
            EventType.PROMPT_STARTED,
            "session-key",
            {"messages": []},
            idempotency_key="idem",
            agent_label="agent",
        )
        kiru = to_kiru_event(event)

        assert isinstance(kiru["event_id"], str)
        assert isinstance(kiru["event_type"], str)
        assert isinstance(kiru["idempotency_key"], str)
        assert isinstance(kiru["session_key"], str)
        assert isinstance(kiru["agent_label"], str)
        assert isinstance(kiru["payload"], dict)
        assert isinstance(kiru["metadata"], dict)


class TestUnicode:
    def test_unicode_payload(self, tmp_path):
        trace = Trace.create("session")
        event = Event.create(
            EventType.RESPONSE_RECEIVED,
            "session",
            {"response": "Hello \u4e16\u754c \U0001f600 \u00e9\u00e0\u00fc"},
        )
        trace.add_event(event)

        path = tmp_path / "unicode.jsonl"
        write_jsonl(path, trace)

        loaded = read_jsonl(path)
        assert (
            loaded.events[0].payload["response"]
            == "Hello \u4e16\u754c \U0001f600 \u00e9\u00e0\u00fc"
        )

    def test_ensure_ascii_false(self, tmp_path):
        trace = Trace.create("session")
        event = Event.create(EventType.CUSTOM, "session", {"text": "\u4e2d\u6587"})
        trace.add_event(event)

        path = tmp_path / "unicode.jsonl"
        write_jsonl(path, trace)

        content = path.read_text(encoding="utf-8")
        assert "\u4e2d\u6587" in content
        assert "\\u" not in content

    def test_read_under_different_locale(self, tmp_path, monkeypatch):
        """Read should work regardless of locale."""
        trace = Trace.create("session")
        event = Event.create(
            EventType.CUSTOM, "session", {"text": "\u00e9\u00e0\u00fc"}
        )
        trace.add_event(event)

        path = tmp_path / "locale.jsonl"
        write_jsonl(path, trace)

        try:
            locale.setlocale(locale.LC_ALL, "C")
        except locale.Error:
            pytest.skip("C locale not available")

        loaded = read_jsonl(path)
        assert loaded.events[0].payload["text"] == "\u00e9\u00e0\u00fc"


class TestLargeFileStreaming:
    def test_large_file_streaming(self, tmp_path):
        """iter_events should stream without loading entire file."""
        trace = Trace.create("session")
        num_events = 10000

        path = tmp_path / "large.jsonl"
        with path.open("w", encoding="utf-8") as f:
            from kiru_ghostline.schema import _TraceHeader

            header = _TraceHeader(
                schema_version=trace.schema_version,
                trace_id=trace.trace_id,
                created_at=trace.created_at,
                producer=trace.producer,
                capture_mode=trace.capture_mode,
            )
            f.write(json.dumps(header.to_dict(), ensure_ascii=False) + "\n")

            for i in range(num_events):
                event = Event.create(EventType.CUSTOM, "session", {"i": i})
                f.write(
                    json.dumps({"kind": "event", **event.to_dict()}, ensure_ascii=False)
                    + "\n"
                )

        count = 0
        for event in iter_events(path):
            count += 1
            if count == 100:
                break

        assert count == 100

    def test_validate_streams(self, tmp_path):
        """validate_jsonl should stream."""
        trace = Trace.create("session")
        path = tmp_path / "valid.jsonl"
        write_jsonl(path, trace)
        for i in range(1000):
            append_event(path, Event.create(EventType.CUSTOM, "session", {}))

        issues = validate_jsonl(path)
        assert issues == []
