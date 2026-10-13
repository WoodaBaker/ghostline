# Changelog

All notable changes to kiru-ghostline will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Full MIT license text in LICENSE file
- CONTRIBUTING.md with contribution guidelines
- SECURITY.md with security policy and vulnerability reporting
- CHANGELOG.md (this file)
- GitHub Actions CI workflow (ruff + pytest on Python 3.10-3.13)
- GitHub Actions release workflow with PyPI trusted publishing

### Fixed
- Sycophancy battery (GI-SYCO-01) now reports per-battery call count instead of whole-run total
- Issues URL in pyproject.toml now points to correct repository

## [0.1.0] - 2026-01-01

### Added
- Initial release
- Battery framework with registry and runner
- Sycophancy flip-rate battery (GI-SYCO-01)
- Stub batteries for goal drift, context corruption, prompt injection, boundary bypass
- Target interface with Budget enforcement
- ScriptedTarget and EchoTarget for testing
- CLI with probe, watch, report, diff commands
- Finding schema for kiru upload contract
- MCP server with probe_disorder and finding_report tools

[Unreleased]: https://github.com/WoodaBaker/ghostline/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/WoodaBaker/ghostline/releases/tag/v0.1.0
