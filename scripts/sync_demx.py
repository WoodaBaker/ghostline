#!/usr/bin/env python3
"""Sync DEM-X catalog from KIRU disorder files.

Usage:
    python scripts/sync_demx.py /path/to/disorders --commit SHA

Accepts either a full KIRU checkout (looks in frontend/dem_x_app/taxonomy/disorders)
or a plain folder containing the 7 disorder JSON files directly.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_KEYS = {
    "code",
    "legacy_code",
    "name",
    "domain",
    "status",
    "summary_short",
    "operational_definition",
    "ai_manifestations",
    "spotter_checklist",
    "differential_diagnosis",
    "treatment_protocol",
    "evidence_sources",
}

EXPECTED_CODES = {
    "GI-SYCO-01",
    "GI-DRFT-01",
    "GI-REF-01",
    "INF-HALL-01",
    "MEM-COR-01",
    "SEC-INJ-01",
    "SEC-BYP-01",
}


def find_disorder_dir(path: Path) -> Path:
    """Find the directory containing disorder JSON files."""
    kiru_path = path / "frontend" / "dem_x_app" / "taxonomy" / "disorders"
    if kiru_path.is_dir():
        return kiru_path
    if any(path.glob("*.json")):
        return path
    raise ValueError(
        f"Cannot find disorder files in {path}. "
        "Expected either a KIRU checkout or a folder with disorder JSON files."
    )


def load_detection_json(detection_path: Path) -> dict:
    """Load detection.json from Ghostline."""
    if not detection_path.exists():
        raise FileNotFoundError(f"Detection file not found: {detection_path}")
    with detection_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate_disorder(data: dict, filename: str) -> list[str]:
    """Validate a disorder file has required keys."""
    errors = []
    missing = REQUIRED_KEYS - set(data.keys())
    if missing:
        errors.append(f"{filename}: missing keys: {sorted(missing)}")
    if "treatment_protocol" in data:
        tp = data["treatment_protocol"]
        if not isinstance(tp, dict):
            errors.append(f"{filename}: treatment_protocol must be a dict")
    return errors


def map_disorder(data: dict, detection: dict | None) -> dict:
    """Map KIRU disorder JSON to Ghostline catalog format."""
    code = data["code"]

    treatment = data.get("treatment_protocol", {})
    remediation = {}
    for key in ["immediate_controls", "prompt_level_patches", "system_level_patches",
                "validation", "success_criteria"]:
        if key in treatment:
            remediation[key] = treatment[key]

    disorder = {
        "id": code,
        "legacy_code": data.get("legacy_code"),
        "name": data["name"],
        "domain": data["domain"],
        "status": data["status"],
        "description": data.get("summary_short", ""),
        "operational_definition": data.get("operational_definition", ""),
        "manifestations": data.get("ai_manifestations", []),
        "spotter_checklist": data.get("spotter_checklist", []),
        "differential_diagnosis": data.get("differential_diagnosis", []),
        "severity": {
            "levels": None,
            "source": "operational_definition prose",
        },
        "remediation": remediation,
        "evidence_sources": data.get("evidence_sources", []),
        "kiru_url": f"https://kiru.solutions/dem-x/{code}/",
    }

    if detection:
        disorder["detection"] = detection

    return disorder


def generate_catalog(
    disorder_dir: Path,
    detection_path: Path,
    commit_sha: str,
) -> dict:
    """Generate the catalog from disorder files."""
    detection_data = load_detection_json(detection_path)

    disorder_files = sorted(disorder_dir.glob("*.json"))
    if not disorder_files:
        raise ValueError(f"No JSON files found in {disorder_dir}")

    disorders = []
    all_errors = []
    found_codes = set()

    for filepath in disorder_files:
        with filepath.open("r", encoding="utf-8") as f:
            data = json.load(f)

        errors = validate_disorder(data, filepath.name)
        all_errors.extend(errors)

        code = data.get("code", "")
        found_codes.add(code)

        detection = detection_data.get(code)
        disorder = map_disorder(data, detection)
        disorders.append(disorder)

    if all_errors:
        for err in all_errors:
            print(f"ERROR: {err}", file=sys.stderr)
        raise ValueError(f"Validation failed with {len(all_errors)} errors")

    missing_codes = EXPECTED_CODES - found_codes
    if missing_codes:
        raise ValueError(f"Missing expected disorder codes: {sorted(missing_codes)}")

    extra_codes = found_codes - EXPECTED_CODES
    if extra_codes:
        print(f"WARNING: Found extra disorder codes: {sorted(extra_codes)}", file=sys.stderr)

    disorders.sort(key=lambda d: d["id"])

    now = datetime.now(timezone.utc)
    short_sha = commit_sha[:7] if len(commit_sha) >= 7 else commit_sha
    catalog_version = f"{now.strftime('%Y.%m.%d')}+{short_sha}"

    catalog = {
        "catalog_format": 1,
        "catalog_version": catalog_version,
        "source_repo": "WoodaBaker/kiru",
        "source_path": "frontend/dem_x_app/taxonomy/disorders",
        "source_commit": commit_sha,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "disorders": disorders,
    }

    return catalog


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync DEM-X catalog from KIRU disorder files"
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Path to KIRU checkout or folder with disorder JSON files",
    )
    parser.add_argument(
        "--commit",
        required=True,
        help="Source commit SHA",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("src/kiru_ghostline/demx/catalog.json"),
        help="Output path for catalog.json",
    )
    parser.add_argument(
        "--detection",
        type=Path,
        default=Path("src/kiru_ghostline/demx/detection.json"),
        help="Path to detection.json",
    )

    args = parser.parse_args()

    try:
        disorder_dir = find_disorder_dir(args.path)
        print(f"Found disorder files in: {disorder_dir}")

        catalog = generate_catalog(disorder_dir, args.detection, args.commit)

        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2, ensure_ascii=False)
            f.write("\n")

        print(f"Generated catalog with {len(catalog['disorders'])} disorders")
        print(f"Catalog version: {catalog['catalog_version']}")
        print(f"Output: {args.output}")
        return 0

    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
