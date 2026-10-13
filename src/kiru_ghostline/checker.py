"""Offline deterministic symptom checker.

Matches symptom descriptions against the DEM-X catalog using
simple tokenized scoring on keywords, manifestations, and spotter checklist.
No external dependencies, no LLM, no network access.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO


@dataclass
class CheckResult:
    """Result of checking a symptom against a disorder."""

    code: str
    name: str
    score: float
    matched: list[str]
    spotter_checklist: list[str]

    def to_dict(self, include_threshold: float | None = None) -> dict[str, Any]:
        result = {
            "code": self.code,
            "name": self.name,
            "score": round(self.score, 3),
            "matched": self.matched,
            "spotter_checklist": self.spotter_checklist,
        }
        if include_threshold is not None:
            result["threshold"] = include_threshold
        return result


def _tokenize(text: str) -> set[str]:
    """Tokenize text into lowercase tokens, keeping digits and some symbols."""
    tokens = re.findall(
        r"[a-z0-9]+(?:\+[a-z0-9]+)*(?:=[a-z0-9]+)?|[a-z]+", text.lower()
    )
    return set(tokens)


def _normalize_phrase(phrase: str) -> str:
    """Normalize a phrase for matching."""
    return " ".join(re.findall(r"[a-z0-9]+", phrase.lower()))


def _phrase_in_text(phrase: str, text: str) -> bool:
    """Check if a phrase appears in the text (normalized)."""
    norm_phrase = _normalize_phrase(phrase)
    norm_text = _normalize_phrase(text)
    return norm_phrase in norm_text


def _match_keywords(
    symptom: str, symptom_tokens: set[str], keywords: list[str]
) -> tuple[float, list[str]]:
    """Match symptom against keywords, return score and matched keywords."""
    matched = []
    phrase_matches = 0
    token_matches = 0

    for kw in keywords:
        kw_tokens = _tokenize(kw)
        if len(kw_tokens) > 1:
            if _phrase_in_text(kw, symptom):
                matched.append(kw)
                phrase_matches += 1
        elif kw_tokens and kw_tokens <= symptom_tokens:
            matched.append(kw)
            token_matches += 1

    if not matched:
        return 0.0, []

    score = min(1.0, phrase_matches * 0.4 + token_matches * 0.15)
    return score, matched


def _match_text_list(
    symptom: str, symptom_tokens: set[str], items: list[str], label: str
) -> tuple[float, list[str]]:
    """Match symptom against a list of text items."""
    matched = []
    for item in items:
        item_tokens = _tokenize(item)
        overlap = symptom_tokens & item_tokens
        if _phrase_in_text(symptom, item) or (
            len(overlap) >= 3 or (item_tokens and len(overlap) / len(item_tokens) > 0.3)
        ):
            short = item[:80] + "..." if len(item) > 80 else item
            matched.append(f"{label}: {short}")
    if not items:
        return 0.0, []
    return min(1.0, len(matched) * 0.25), matched


def check_symptom(
    symptom: str,
    catalog: dict[str, Any],
    top_n: int = 3,
    threshold: float = 0.5,
) -> list[CheckResult]:
    """Check a symptom against the catalog.

    Args:
        symptom: The symptom description text
        catalog: The DEM-X catalog dict
        top_n: Number of top results to return
        threshold: Minimum score threshold (results below are still returned but marked)

    Returns:
        List of CheckResult, sorted by score descending, then by code
    """
    symptom_tokens = _tokenize(symptom)
    if not symptom_tokens:
        return []

    results = []

    for disorder in catalog.get("disorders", []):
        code = disorder["id"]
        name = disorder["name"]

        detection = disorder.get("detection", {})
        keywords = detection.get("keywords", [])
        manifestations = disorder.get("manifestations", [])
        spotter_checklist = disorder.get("spotter_checklist", [])
        description = disorder.get("description", "")

        matched: list[str] = []
        scores: list[tuple[str, float]] = []

        kw_score, kw_matched = _match_keywords(symptom, symptom_tokens, keywords)
        if kw_matched:
            matched.extend([f"keyword: {kw}" for kw in kw_matched[:5]])
            scores.append(("keyword", kw_score))

        man_score, man_matched = _match_text_list(
            symptom, symptom_tokens, manifestations, "manifestation"
        )
        if man_matched:
            matched.extend(man_matched[:3])
            scores.append(("manifestation", man_score * 0.8))

        spot_score, spot_matched = _match_text_list(
            symptom, symptom_tokens, spotter_checklist, "spotter"
        )
        if spot_matched:
            matched.extend(spot_matched[:3])
            scores.append(("spotter", spot_score * 0.6))

        desc_tokens = _tokenize(description)
        desc_overlap = symptom_tokens & desc_tokens
        if len(desc_overlap) >= 4:
            scores.append(("description", min(0.3, len(desc_overlap) * 0.05)))
            matched.append(f"description overlap: {len(desc_overlap)} tokens")

        if not scores:
            continue

        keyword_scores = [s for t, s in scores if t == "keyword"]
        other_scores = [s for t, s in scores if t != "keyword"]

        if keyword_scores:
            final_score = max(keyword_scores)
            if other_scores:
                final_score = min(1.0, final_score + max(other_scores) * 0.3)
        elif other_scores:
            final_score = max(other_scores)
        else:
            continue

        final_score = min(final_score, 1.0)

        results.append(
            CheckResult(
                code=code,
                name=name,
                score=final_score,
                matched=matched[:8],
                spotter_checklist=spotter_checklist[:3],
            )
        )

    results.sort(key=lambda r: (-r.score, r.code))
    return results[:top_n]


def load_catalog(catalog_path: Path | None = None) -> dict[str, Any]:
    """Load catalog from path or default."""
    if catalog_path:
        with catalog_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    from .demx.catalog import get_catalog

    return get_catalog()


def format_text(
    results: list[CheckResult], threshold: float, quiet: bool = False
) -> str:
    """Format results as human-readable text."""
    if not results:
        return "No matches found."

    lines = []
    for i, r in enumerate(results, 1):
        status = "MATCH" if r.score >= threshold else "below threshold"
        lines.append(f"{i}. {r.code} ({r.name}) - score: {r.score:.3f} [{status}]")
        if not quiet:
            for reason in r.matched:
                lines.append(f"   - {reason}")
            if r.spotter_checklist:
                lines.append("   Spotter checklist:")
                for item in r.spotter_checklist:
                    short = item[:100] + "..." if len(item) > 100 else item
                    lines.append(f"     * {short}")
        lines.append("")

    return "\n".join(lines)


def format_json(results: list[CheckResult], threshold: float) -> str:
    """Format results as JSON."""
    return json.dumps(
        {
            "threshold": threshold,
            "results": [r.to_dict(include_threshold=threshold) for r in results],
        },
        indent=2,
    )


def validate_args(
    symptom: str,
    top_n: int,
    threshold: float,
    fail_on: list[str] | None,
    catalog: dict[str, Any],
) -> str | None:
    """Validate arguments, return error message or None if valid."""
    if not symptom or not symptom.strip():
        return "Error: symptom cannot be empty"

    if top_n < 1:
        return "Error: --top must be at least 1"

    if not (0.0 <= threshold <= 1.0):
        return "Error: --threshold must be between 0.0 and 1.0"

    if fail_on:
        valid_codes = {d["id"] for d in catalog.get("disorders", [])}
        unknown = [c for c in fail_on if c not in valid_codes]
        if unknown:
            return f"Error: unknown disorder codes: {', '.join(unknown)}"

    return None


def run_check(
    symptom: str,
    catalog_path: Path | None = None,
    top_n: int = 3,
    threshold: float = 0.5,
    output_format: str = "text",
    fail_on: list[str] | None = None,
    quiet: bool = False,
    output: TextIO | None = None,
) -> int:
    """Run the check command.

    Returns:
        0: No match >= threshold (or no --fail-on codes matched)
        1: Error
        2: Match >= threshold found (or --fail-on codes matched)
    """
    if output is None:
        output = sys.stdout

    try:
        catalog = load_catalog(catalog_path)
    except FileNotFoundError as e:
        print(f"Error loading catalog: {e}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"Error loading catalog: invalid JSON - {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"Error loading catalog: {e}", file=sys.stderr)
        return 1

    error = validate_args(symptom, top_n, threshold, fail_on, catalog)
    if error:
        print(error, file=sys.stderr)
        return 1

    results = check_symptom(symptom, catalog, top_n=top_n, threshold=threshold)

    if output_format == "json":
        print(format_json(results, threshold), file=output)
    else:
        print(format_text(results, threshold, quiet=quiet), file=output)

    if fail_on:
        fail_codes = set(fail_on)
        matched_fail_codes = [
            r for r in results if r.code in fail_codes and r.score >= threshold
        ]
        if matched_fail_codes:
            return 2
        return 0

    matched_above = [r for r in results if r.score >= threshold]
    if matched_above:
        return 2
    return 0
