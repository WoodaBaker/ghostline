# Contributing to kiru-ghostline

Thank you for your interest in contributing to kiru-ghostline! This document provides guidelines for contributing to the project.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/ghostline.git`
3. Install development dependencies: `pip install -e ".[dev]"`
4. Create a feature branch: `git checkout -b your-feature-name`

## Development Setup

```bash
# Install the package in editable mode with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
ruff check .
ruff format --check .
```

## Adding a Battery

1. Subclass `batteries.base.Battery`, set `slug`, `disorder`, `description`.
2. Implement `run(target, budget)` -- call `budget.spend()` per model call.
3. Decorate with `@register`, import it in `batteries/__init__.py`.
4. Test against `ScriptedTarget` -- no API keys needed.

## Code Style

- Follow PEP 8 guidelines
- Use type hints where appropriate
- Write docstrings for public functions and classes
- Keep lines under 88 characters (ruff default)

## Testing

- All new features should include tests
- Use `ScriptedTarget` for battery tests (no API keys required)
- Run the full test suite before submitting: `pytest`
- Ensure linting passes: `ruff check .`

## Pull Request Process

1. Update documentation if needed
2. Add tests for new functionality
3. Ensure CI passes (ruff + pytest)
4. Request review from maintainers

## Reporting Issues

- Use the GitHub issue tracker
- Include steps to reproduce
- Include Python version and OS
- Include relevant error messages

## Code of Conduct

Be respectful and constructive in all interactions. We're building tools to make AI agents safer -- let's do it collaboratively.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
