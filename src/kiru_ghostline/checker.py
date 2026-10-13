"""Offline deterministic symptom checker.

Matches symptom descriptions against the DEM-X catalog using
concept matching with light stemming, weighted scoring across
keywords, concepts, manifestations, differential diagnosis, and spotter checklist.
No external dependencies, no LLM, no network access.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

GENERIC_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "it",
        "its",
        "is",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "shall",
        "can",
        "need",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "under",
        "again",
        "further",
        "then",
        "once",
        "here",
        "there",
        "when",
        "where",
        "why",
        "how",
        "all",
        "each",
        "every",
        "both",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "nor",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "just",
        "also",
        "now",
        "i",
        "me",
        "my",
        "myself",
        "we",
        "our",
        "ours",
        "you",
        "your",
        "yours",
        "he",
        "him",
        "his",
        "she",
        "her",
        "hers",
        "they",
        "them",
        "their",
        "theirs",
        "what",
        "which",
        "who",
        "whom",
        "this",
        "that",
        "these",
        "those",
        "am",
        "are",
        "and",
        "but",
        "if",
        "or",
        "because",
        "until",
        "while",
        "although",
        "though",
        "doesn",
        "doesn't",
        "don",
        "don't",
        "didn",
        "didn't",
        "isn",
        "isn't",
        "wasn",
        "wasn't",
        "weren",
        "weren't",
        "haven",
        "haven't",
        "hasn",
        "hasn't",
        "hadn",
        "hadn't",
        "won",
        "won't",
        "wouldn",
        "wouldn't",
        "can't",
        "cannot",
        "couldn",
        "couldn't",
        "shouldn",
        "shouldn't",
        "never",
        "long",
        "about",
        "like",
        "get",
        "got",
        "getting",
        "make",
        "made",
        "making",
        "take",
        "took",
        "taking",
        "know",
        "knew",
        "known",
        "think",
        "thought",
        "say",
        "said",
        "saying",
        "see",
        "saw",
        "seen",
        "come",
        "came",
        "coming",
        "go",
        "went",
        "gone",
        "going",
        "give",
        "gave",
        "given",
        "giving",
        "use",
        "used",
        "using",
        "find",
        "found",
        "want",
        "wanted",
        "wanting",
        "tell",
        "told",
        "telling",
        "ask",
        "asked",
        "asking",
        "work",
        "worked",
        "working",
        "seem",
        "seemed",
        "feel",
        "felt",
        "try",
        "tried",
        "trying",
        "leave",
        "left",
        "call",
        "called",
        "calling",
        "keep",
        "kept",
        "let",
        "begin",
        "began",
        "begun",
        "show",
        "showed",
        "shown",
        "hear",
        "heard",
        "play",
        "played",
        "run",
        "ran",
        "running",
        "move",
        "moved",
        "live",
        "lived",
        "believe",
        "believed",
        "bring",
        "brought",
        "happen",
        "happened",
        "write",
        "wrote",
        "written",
        "provide",
        "provided",
        "sit",
        "sat",
        "stand",
        "stood",
        "lose",
        "lost",
        "pay",
        "paid",
        "meet",
        "met",
        "include",
        "included",
        "continue",
        "continued",
        "set",
        "learn",
        "learned",
        "change",
        "changed",
        "lead",
        "led",
        "understand",
        "understood",
        "watch",
        "watched",
        "follow",
        "followed",
        "stop",
        "stopped",
        "create",
        "created",
        "speak",
        "spoke",
        "spoken",
        "read",
        "allow",
        "allowed",
        "add",
        "added",
        "spend",
        "spent",
        "grow",
        "grew",
        "grown",
        "open",
        "opened",
        "walk",
        "walked",
        "win",
        "offer",
        "offered",
        "remember",
        "remembered",
        "love",
        "loved",
        "consider",
        "considered",
        "appear",
        "appeared",
        "buy",
        "bought",
        "wait",
        "waited",
        "serve",
        "served",
        "die",
        "died",
        "send",
        "sent",
        "expect",
        "expected",
        "build",
        "built",
        "stay",
        "stayed",
        "fall",
        "fell",
        "fallen",
        "cut",
        "reach",
        "reached",
        "kill",
        "killed",
        "remain",
        "remained",
    }
)

STEM_SUFFIXES = [
    ("ying", "y"),
    ("ying", "ie"),
    ("ies", "y"),
    ("ied", "y"),
    ("ing", ""),
    ("ing", "e"),
    ("ed", ""),
    ("ed", "e"),
    ("er", ""),
    ("er", "e"),
    ("est", ""),
    ("est", "e"),
    ("ly", ""),
    ("ness", ""),
    ("ment", ""),
    ("tion", ""),
    ("sion", ""),
    ("ity", ""),
    ("ful", ""),
    ("less", ""),
    ("able", ""),
    ("ible", ""),
    ("ous", ""),
    ("ive", ""),
    ("al", ""),
    ("s", ""),
]


def _stem(word: str) -> str:
    """Apply light stemming to a word."""
    if len(word) <= 3:
        return word
    for suffix, replacement in STEM_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) + len(replacement) >= 3:
            return word[: -len(suffix)] + replacement
    return word


@dataclass
class CheckResult:
    """Result of checking a symptom against a disorder."""

    code: str
    name: str
    score: float
    matched: list[str]
    spotter_checklist: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "score": round(self.score, 3),
            "matched": self.matched,
            "spotter_checklist": self.spotter_checklist,
        }


def _tokenize(text: str) -> set[str]:
    """Tokenize text into lowercase tokens, keeping digits and some symbols."""
    tokens = re.findall(
        r"[a-z0-9]+(?:\+[a-z0-9]+)*(?:=[a-z0-9]+)?|[a-z]+", text.lower()
    )
    return set(tokens)


def _tokenize_stemmed(text: str) -> set[str]:
    """Tokenize and stem text, excluding generic words."""
    tokens = _tokenize(text)
    result = set()
    for t in tokens:
        if t not in GENERIC_WORDS:
            result.add(t)
            stemmed = _stem(t)
            if stemmed != t:
                result.add(stemmed)
    return result


def _normalize_phrase(phrase: str) -> str:
    """Normalize a phrase for matching."""
    return " ".join(re.findall(r"[a-z0-9]+", phrase.lower()))


def _phrase_in_text(phrase: str, text: str) -> bool:
    """Check if a phrase appears in the text (normalized)."""
    norm_phrase = _normalize_phrase(phrase)
    norm_text = _normalize_phrase(text)
    return norm_phrase in norm_text


def _concept_match(
    symptom: str,
    symptom_tokens: set[str],
    symptom_stemmed: set[str],
    concepts: list[str],
) -> tuple[float, list[str]]:
    """Match symptom against concept/synonym list with stemming.

    Multi-word concepts require exact phrase match.
    Single-word concepts allow token/stemmed matching.
    """
    matched = []
    phrase_matches = 0
    stem_matches = 0

    for concept in concepts:
        concept_lower = concept.lower()
        concept_tokens = _tokenize(concept_lower)

        if len(concept_tokens) > 1:
            if _phrase_in_text(concept, symptom):
                matched.append(concept)
                phrase_matches += 1
            continue

        for ct in concept_tokens:
            if ct in symptom_tokens or ct in symptom_stemmed:
                matched.append(concept)
                stem_matches += 1
                break
            ct_stem = _stem(ct)
            if ct_stem in symptom_stemmed:
                matched.append(concept)
                stem_matches += 1
                break

    if not matched:
        return 0.0, []

    score = min(1.0, phrase_matches * 0.5 + stem_matches * 0.2)
    return score, matched


def _match_text_list(
    symptom_stemmed: set[str], items: list[str], label: str, min_overlap: int = 2
) -> tuple[float, list[str]]:
    """Match symptom against a list of text items using stemmed tokens."""
    matched = []
    for item in items:
        item_stemmed = _tokenize_stemmed(item)
        overlap = symptom_stemmed & item_stemmed
        if len(overlap) >= min_overlap:
            short = item[:80] + "..." if len(item) > 80 else item
            matched.append(f"{label}: {short}")
    if not items:
        return 0.0, []
    return min(1.0, len(matched) * 0.2), matched


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
    symptom_stemmed = _tokenize_stemmed(symptom)
    if not symptom_stemmed:
        return []

    results = []

    for disorder in catalog.get("disorders", []):
        code = disorder["id"]
        name = disorder["name"]

        detection = disorder.get("detection", {})
        concepts = detection.get("concepts", [])
        manifestations = disorder.get("manifestations", [])
        spotter_checklist = disorder.get("spotter_checklist", [])
        differential = disorder.get("differential_diagnosis", [])

        matched: list[str] = []
        scores: list[tuple[str, float]] = []

        concept_score, concept_matched = _concept_match(
            symptom, symptom_tokens, symptom_stemmed, concepts
        )
        if concept_matched:
            matched.extend([f"concept: {c}" for c in concept_matched[:5]])
            scores.append(("concept", concept_score))

        man_score, man_matched = _match_text_list(
            symptom_stemmed, manifestations, "manifestation", min_overlap=2
        )
        if man_matched:
            matched.extend(man_matched[:3])
            scores.append(("manifestation", man_score * 0.7))

        diff_texts = []
        for d in differential:
            if isinstance(d, dict):
                diff_texts.append(d.get("distinguishing_feature", ""))
            elif isinstance(d, str):
                diff_texts.append(d)
        diff_score, diff_matched = _match_text_list(
            symptom_stemmed, diff_texts, "differential", min_overlap=2
        )
        if diff_matched:
            matched.extend(diff_matched[:2])
            scores.append(("differential", diff_score * 0.5))

        spot_score, spot_matched = _match_text_list(
            symptom_stemmed, spotter_checklist, "spotter", min_overlap=2
        )
        if spot_matched:
            matched.extend(spot_matched[:2])
            scores.append(("spotter", spot_score * 0.4))

        if not scores:
            continue

        concept_scores = [s for t, s in scores if t == "concept"]
        other_scores = [s for t, s in scores if t != "concept"]

        if concept_scores:
            final_score = max(concept_scores)
            if other_scores:
                final_score = min(1.0, final_score + max(other_scores) * 0.4)
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


def validate_catalog(catalog: Any) -> str | None:
    """Validate catalog structure, return error message or None if valid."""
    if not isinstance(catalog, dict):
        return "catalog must be a JSON object"
    if "disorders" not in catalog:
        return "catalog missing 'disorders' key"
    if not isinstance(catalog["disorders"], list):
        return "'disorders' must be a list"
    for i, disorder in enumerate(catalog["disorders"]):
        if not isinstance(disorder, dict):
            return f"disorder at index {i} is not an object"
        if "id" not in disorder:
            return f"disorder at index {i} missing 'id'"
        if "name" not in disorder:
            return f"disorder at index {i} missing 'name'"
    return None


def load_catalog(catalog_path: Path | None = None) -> dict[str, Any]:
    """Load and validate catalog from path or default."""
    if catalog_path:
        with catalog_path.open("r", encoding="utf-8") as f:
            catalog = json.load(f)
    else:
        from .demx.catalog import get_catalog

        catalog = get_catalog()

    error = validate_catalog(catalog)
    if error:
        raise ValueError(error)
    return catalog


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
            "results": [r.to_dict() for r in results],
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
    except ValueError as e:
        print(f"Error loading catalog: {e}", file=sys.stderr)
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
