# kiru-ghostline

Behavioral diagnostics for AI agents — probe for known failure modes, watch for drift, document new ones.

```bash
pip install kiru-ghostline
ghostline probe --target my-agent
```

Part of [kiru](https://kiru.solutions) / DEM-X. The package is the execution plane:
batteries run where your agent lives (laptop, VPC, CI), so API keys and
inference spend stay with you. Findings can be uploaded to kiru (opt-in),
where they enter the DEM-X disorder lifecycle.

Status: pre-alpha scaffold. Batteries tracked in
[WoodaBaker/kiru#509](https://github.com/WoodaBaker/kiru/issues/509).

## Commands

- `ghostline probe --target <agent>` — run disorder probe batteries
- `ghostline watch --target <stream>` — continuous drift monitoring
- `ghostline report [--upload]` — document a finding (kiru upload is opt-in)
- `ghostline diff --from v1 --to v2` — version-to-version regression

## License

MIT
