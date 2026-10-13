# ghostline.v1 Schema Contract

This document defines the ghostline.v1 trace schema for capturing and analyzing AI agent behavior.

## Enums

### EventType (str, Enum)
- `prompt_started` - Start of a prompt/request
- `response_received` - Model response received
- `tool_called` - Tool/function invocation
- `tool_result` - Result from tool execution
- `session_closed` - Session termination
- `objective_set` - Objective/goal definition
- `custom` - Application-specific events

### CaptureMode
- `metadata_only` - Only metadata, no payload content
- `partial_payload` - First 200 chars per text field
- `full_payload` - Complete payload content

### Verdict
- `clean` - No signals detected
- `signal` - One or more signals above threshold
- `inconclusive` - Unable to determine

### SignalSource
- `detector` - Automated detector
- `battery` - Probe battery
- `checker` - Rule-based checker
- `judge` - LLM judge

## Event

| Field | Type | Required | Default | Constraints |
|-------|------|----------|---------|-------------|
| event_id | str | yes | - | UUID4, client-generated |
| event_type | EventType | yes | - | - |
| ts | str | yes | - | RFC3339 UTC |
| session_key | str | yes | - | max 120 chars |
| idempotency_key | str | no | '' | max 128 chars |
| agent_label | str | no | '' | max 120 chars |
| seq | int | no | line order | - |
| model | ModelRef\|None | no | None | {provider, name, params} |
| payload | dict | yes | - | may be {} |
| capture_mode | CaptureMode | no | partial_payload | - |
| metadata | dict | no | {} | - |

### Payload Known Keys (all optional)
- `messages`: list[{role, content}]
- `response`: str
- `tool`: {name, args, result}
- `usage`: {input_tokens, output_tokens}
- `latency_ms`: int
- `logprobs`: list\|None
- `objective`: str (for objective_set events)

Unknown keys are preserved.

## Trace

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| schema_version | str | yes | 'ghostline.v1' | - |
| trace_id | str | yes | - | UUID4 |
| created_at | str | yes | - | RFC3339 UTC |
| producer | str | yes | - | e.g. 'kiru-ghostline/0.1.0' |
| session_key | str | no | None | - |
| agent_label | str | no | None | - |
| objective | str | no | None | Mirror of first objective_set |
| capture_mode | CaptureMode | yes | - | Most permissive used |
| redactions | list[str] | no | None | - |
| events | list[Event] | - | [] | In memory only, not serialized |

## Signal

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| code | str | yes | - | DEM-X format, e.g. GI-SYCO-01 |
| confidence | float | yes | - | 0.0 to 1.0 |
| source | SignalSource | yes | - | - |
| producer | str | yes | - | - |
| evidence_event_ids | list[str] | conditional | [] | Required non-empty when source=detector |
| explanation | str | yes | - | - |
| score | float\|None | no | None | - |
| level | int\|None | no | None | - |

## Diagnosis

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| schema_version | str | yes | 'ghostline.v1' | - |
| diagnosis_id | str | yes | - | UUID4 |
| created_at | str | yes | - | RFC3339 UTC |
| trace_id | str\|None | no | None | - |
| catalog_version | str | yes | - | - |
| verdict | Verdict | yes | - | signal if any signal >= threshold |
| threshold | float | no | 0.5 | - |
| signals | list[Signal] | no | [] | Sorted by confidence desc |
| ran | list[str] | yes | - | Producers that ran |
| skipped | list[{producer, reason}] | no | [] | - |
| calls | int | no | 0 | - |

`from_dict` must NOT silently invent ids/timestamps for missing required fields; raise.

## Finding

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| id | str | yes | - | UUID4 |
| schema_version | str | yes | 'ghostline.v1' | - |
| suspected_disorder | str\|None | no | None | Optional; not required for CLI use |
| observed_behavior | str | yes | - | - |
| model | str | no | '' | - |
| scaffolding | str\|None | no | None | - |
| repeatability | float\|None | no | None | Legacy strings like '4/5 runs' converted to fraction |
| battery_scores | dict | no | {} | - |
| telemetry_excerpts | list[Event] | no | [] | Redacted events |
| diagnosis_id | str\|None | no | None | - |
| catalog_version | str | yes | - | - |
| mechanistic_evidence | dict\|None | no | None | Always None in v0.1 |

## JSONL Format

- Default path: `.ghostline/traces/<session_key>.jsonl`
- Encoding: UTF-8 (`encoding='utf-8'`, `ensure_ascii=False`)
- One JSON object per line, terminated with `\n`

### Line 1 (Header)
```json
{"kind": "header", "schema_version": "ghostline.v1", "trace_id": "...", ...}
```
All Trace fields except `events`.

### Subsequent Lines (Events)
```json
{"kind": "event", "event_id": "...", "event_type": "prompt_started", ...}
```

### Rules
- Append only; appending to missing file writes header first
- No header or unknown major version => error
- Blank lines skipped
- Truncated LAST line => `warnings.warn` (crash safety), ignored
- Malformed lines elsewhere => error with line number
- Non-object JSON lines => `TraceParseError` with line number

## Versioning

- Format: `ghostline.v<MAJOR>`
- Readers accept current major (1) and previous (0), reject others
- Unknown fields: ignore but preserve (round-trip)
- Unknown event_type: keep as `custom` in memory, preserve raw string, write back unchanged
- Timestamps: validate RFC3339 UTC on read, emit with `Z` suffix on write

## KIRU Upload Mapping

The `to_kiru_event` helper maps Event to KIRU TelemetryEvent format:
- `ts`, `seq`, `model`, `capture_mode` go into `metadata`
- `schema_version` 'ghostline.v1' maps to 'v1'

## Streaming

Read and validate operations must stream line by line, not load entire file into memory.
