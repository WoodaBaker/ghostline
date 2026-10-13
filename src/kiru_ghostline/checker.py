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
    why: list[str]
    spotter_items: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "score": round(self.score, 3),
            "why": self.why,
            "spotter_items": self.spotter_items,
        }


def _tokenize(text: str) -> set[str]:
    """Tokenize text into lowercase words."""
    return set(re.findall(r"[a-z]+", text.lower()))


def _ngrams(tokens: set[str], n: int = 2) -> set[str]:
    """Generate n-grams from token list for phrase matching."""
    token_list = sorted(tokens)
    grams = set(token_list)
    for i in range(len(token_list) - n + 1):
        grams.add(" ".join(token_list[i : i + n]))
    return grams


def _match_keywords(symptom_tokens: set[str], keywords: list[str]) -> tuple[float, list[str]]:
    """Match symptom against keywords, return score and matched keywords."""
    matched = []
    for kw in keywords:
        kw_tokens = _tokenize(kw)
        if kw_tokens and kw_tokens <= symptom_tokens:
            matched.append(kw)
    if not keywords:
        return 0.0, []
    if matched:
        return min(1.0, len(matched) * 0.3), matched
    return 0.0, []


def _match_text_list(
    symptom_tokens: set[str], items: list[str], label: str
) -> tuple[float, list[str]]:
    """Match symptom against a list of text items."""
    matched = []
    for item in items:
        item_tokens = _tokenize(item)
        overlap = symptom_tokens & item_tokens
        if len(overlap) >= 3 or (item_tokens and len(overlap) / len(item_tokens) > 0.3):
            short = item[:80] + "..." if len(item) > 80 else item
            matched.append(f"{label}: {short}")
    if not items:
        return 0.0, []
    return len(matched) / len(items), matched


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
        List of CheckResult, sorted by score descending
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

        why = []
        scores = []

        kw_score, kw_matched = _match_keywords(symptom_tokens, keywords)
        if kw_matched:
            why.extend([f"keyword: {kw}" for kw in kw_matched[:3]])
            scores.append(("keyword", kw_score))

        man_score, man_matched = _match_text_list(symptom_tokens, manifestations, "manifestation")
        if man_matched:
            why.extend(man_matched[:2])
            scores.append(("manifestation", man_score * 0.8))

        spot_score, spot_matched = _match_text_list(
            symptom_tokens, spotter_checklist, "spotter"
        )
        if spot_matched:
            why.extend(spot_matched[:2])
            scores.append(("spotter", spot_score * 0.6))

        desc_tokens = _tokenize(description)
        desc_overlap = symptom_tokens & desc_tokens
        if len(desc_overlap) >= 4:
            scores.append(("description", min(1.0, len(desc_overlap) * 0.05)))
            why.append(f"description overlap: {len(desc_overlap)} tokens")

        if not scores:
            continue

        keyword_scores = [s for t, s in scores if t == "keyword"]
        other_scores = [s for t, s in scores if t != "keyword"]

        if keyword_scores:
            final_score = max(keyword_scores)
            if other_scores:
                final_score = max(final_score, max(other_scores) * 0.5)
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
                why=why[:5],
                spotter_items=spotter_checklist[:3],
            )
        )

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:top_n]


def load_catalog(catalog_path: Path | None = None) -> dict[str, Any]:
    """Load catalog from path or default."""
    if catalog_path:
        with catalog_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    from .demx.catalog import get_catalog

    return get_catalog()


def format_text(results: list[CheckResult], threshold: float, quiet: bool = False) -> str:
    """Format results as human-readable text."""
    if not results:
        return "No matches found."

    lines = []
    for i, r in enumerate(results, 1):
        status = "MATCH" if r.score >= threshold else "below threshold"
        lines.append(f"{i}. {r.code} ({r.name}) - score: {r.score:.3f} [{status}]")
        if not quiet:
            for reason in r.why:
                lines.append(f"   - {reason}")
            if r.spotter_items:
                lines.append("   Spotter checklist:")
                for item in r.spotter_items:
                    short = item[:100] + "..." if len(item) > 100 else item
                    lines.append(f"     * {short}")
        lines.append("")

    return "\n".join(lines)


def format_json(results: list[CheckResult]) -> str:
    """Format results as JSON."""
    return json.dumps([r.to_dict() for r in results], indent=2)


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
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        print(f"Error loading catalog: {e}", file=sys.stderr)
        return 1

    results = check_symptom(symptom, catalog, top_n=top_n, threshold=threshold)

    if output_format == "json":
        print(format_json(results), file=output)
    else:
        print(format_text(results, threshold, quiet=quiet), file=output)

    if fail_on:
        fail_codes = set(fail_on)
        matched_fail_codes = [r for r in results if r.code in fail_codes and r.score >= threshold]
        if matched_fail_codes:
            return 2
        return 0

    matched_above = [r for r in results if r.score >= threshold]
    if matched_above:
        return 2
    return 0
