# kiru-ghostline

Behavioral diagnostics for AI agents -- probe for known failure modes, watch for drift, document new ones.

```bash
pip install kiru-ghostline
ghostline probe --target echo --disorders sycophancy-flip
```

Part of [kiru](https://kiru.solutions) / DEM-X. The package is the execution plane:
batteries run where your agent lives (laptop, VPC, CI), so API keys and
inference spend stay with you. Findings can be uploaded to kiru (opt-in),
where they enter the DEM-X disorder lifecycle.

Status: pre-alpha. Framework is real (registry, runner, budgets, findings);
batteries tracked in [WoodaBaker/kiru#509](https://github.com/WoodaBaker/kiru/issues/509).

## Commands

- `ghostline probe --target <agent>` -- run disorder probe batteries (exit 2 on signal)
- `ghostline watch --target <stream>` -- continuous drift monitoring (stub)
- `ghostline report --behavior ... [--upload]` -- document a finding (upload opt-in)
- `ghostline diff --from v1 --to v2` -- version-to-version regression (stub)

## Layout

```
src/kiru_ghostline/
├── cli.py            # probe / watch / report / diff
├── runner.py         # battery selection, shared budget, RunReport
├── targets/          # Target interface + Budget; scripted targets for tests
├── batteries/
│   ├── base.py       # Battery ABC + BatteryResult
│   ├── registry.py   # @register -- the set of disorders we can probe
│   ├── sycophancy.py # GI-SYCO-01 flip-rate test (working example)
│   └── *.py          # goal_drift, context_corruption, prompt_injection,
│                     # boundary_bypass -- stubbed, methods documented
├── findings.py       # Finding format: the kiru upload contract
│                     # (mechanistic_evidence reserved for future use)
├── watch.py          # continuous monitoring (stub)
└── mcp_server.py     # MCP tools: probe_disorder, finding_report
skills/ghostline-diagnostics/SKILL.md  # agent skill for Claude Code plugin
.claude-plugin/      # plugin.json + marketplace.json
server.json          # official MCP registry listing
```

## Adding a battery

1. Subclass `batteries.base.Battery`, set `slug`, `disorder`, `description`.
2. Implement `run(target, budget)` -- call `budget.spend()` per model call.
3. Decorate with `@register`, import it in `batteries/__init__.py`.
4. Test against `ScriptedTarget` -- no API keys needed.

## Distribution

- PyPI: `kiru-ghostline` (trusted publishing on tag `v*`)
- MCP registry: `io.github.WoodaBaker/ghostline` (`mcp-publisher publish`)
- Claude Code: `/plugin marketplace add WoodaBaker/ghostline`

## License

MIT
