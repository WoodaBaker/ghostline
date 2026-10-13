# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in kiru-ghostline, please report it responsibly:

1. **Do not** open a public GitHub issue for security vulnerabilities.
2. Use [GitHub's private vulnerability reporting](https://github.com/WoodaBaker/ghostline/security/advisories/new) to submit the report.
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

## Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial assessment**: Within 1 week
- **Fix timeline**: Depends on severity, typically within 30 days for critical issues

## Security Considerations

kiru-ghostline runs diagnostic batteries against AI agent targets. Keep in mind:

- **API keys stay local**: Batteries run where your agent lives; keys are never transmitted to kiru unless you explicitly opt in to upload.
- **Budget limits**: Use `--max-calls` to cap inference spend during probes.
- **Scripted targets**: For testing, use `ScriptedTarget` or `EchoTarget` -- no API keys needed.

## Scope

This security policy covers:
- The `kiru-ghostline` Python package
- The MCP server (`mcp_server.py`)
- The CLI (`ghostline` command)

Third-party dependencies have their own security policies.
