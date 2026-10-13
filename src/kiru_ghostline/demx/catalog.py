"""Load the vendored DEM-X catalog.

The catalog is loaded once at module import via importlib.resources.
No network access is required at runtime.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any


@lru_cache(maxsize=1)
def get_catalog() -> dict[str, Any]:
    """Load and return the full DEM-X catalog.

    Returns the catalog dict with keys:
    - catalog_format: int
    - catalog_version: str
    - source_repo, source_path, source_commit, generated_at: str
    - disorders: list of disorder dicts
    """
    catalog_file = resources.files(__package__).joinpath("catalog.json")
    with catalog_file.open("r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _disorder_index() -> dict[str, dict[str, Any]]:
    """Build an index of disorders by code."""
    catalog = get_catalog()
    return {d["id"]: d for d in catalog["disorders"]}


def get_disorder(code: str) -> dict[str, Any] | None:
    """Get a disorder by its code (e.g., 'GI-SYCO-01').

    Returns None if the code is not found.
    """
    return _disorder_index().get(code)


def get_disorder_codes() -> list[str]:
    """Get all disorder codes in the catalog, sorted."""
    return sorted(_disorder_index().keys())


def is_valid_disorder_code(code: str) -> bool:
    """Check if a code exists in the catalog."""
    return code in _disorder_index()
