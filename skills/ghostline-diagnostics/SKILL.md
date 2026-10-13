# Ghostline diagnostics

You can run behavioral diagnostics on AI agents using the Ghostline toolkit.
Two surfaces: the `ghostline` CLI (batteries run where the agent lives) and
the `ghostline` MCP server (`probe_disorder`, `finding_report` tools).

## When to use

- The user asks to check an agent for a failure mode (goal drift, sycophancy,
  context corruption, prompt injection, boundary bypass).
- The user describes agent misbehavior and wants a DEM-X differential.
- The user wants to document a novel failure pattern as a finding.

## How

Prefer the MCP tools when available — they wrap the same battery registry
as the CLI. For local runs:

```bash
ghostline probe --target <agent> --disorders sycophancy-flip
ghostline report --behavior "..." --model <id> [--upload]
```

Key facts:
- Batteries are independent; run one, a few, or all. `--max-calls` caps spend.
- Exit code 2 from `probe` means a disorder signal was detected.
- `report --upload` to kiru is opt-in and not yet wired (kiru#509).
- Findings use the schema in `src/kiru_ghostline/findings.py`;
  `mechanistic_evidence` is reserved for future use.
- Never invent battery results. Only report what a run produced.
