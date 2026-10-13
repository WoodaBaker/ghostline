"""Tests for DEM-X catalog and checker."""

import json
import subprocess
import sys
from io import StringIO
from pathlib import Path

from kiru_ghostline.checker import (
    CheckResult,
    check_symptom,
    format_json,
    format_text,
    run_check,
    validate_catalog,
)
from kiru_ghostline.cli import main
from kiru_ghostline.demx.catalog import (
    get_catalog,
    get_disorder,
    get_disorder_codes,
    is_valid_disorder_code,
)


class TestCatalog:
    def test_catalog_loads(self):
        catalog = get_catalog()
        assert catalog["catalog_format"] == 1
        assert "catalog_version" in catalog
        assert "disorders" in catalog
        assert len(catalog["disorders"]) == 7

    def test_catalog_version_format(self):
        catalog = get_catalog()
        version = catalog["catalog_version"]
        assert "+" in version
        assert version.startswith("2026.")

    def test_all_disorders_have_required_fields(self):
        catalog = get_catalog()
        required = {"id", "name", "domain", "status", "description", "manifestations"}
        for disorder in catalog["disorders"]:
            missing = required - set(disorder.keys())
            assert not missing, f"{disorder['id']} missing: {missing}"

    def test_disorders_sorted_by_id(self):
        catalog = get_catalog()
        ids = [d["id"] for d in catalog["disorders"]]
        assert ids == sorted(ids)

    def test_get_disorder(self):
        disorder = get_disorder("GI-SYCO-01")
        assert disorder is not None
        assert disorder["name"] == "Sycophancy"

    def test_get_disorder_not_found(self):
        assert get_disorder("FAKE-CODE-99") is None

    def test_get_disorder_codes(self):
        codes = get_disorder_codes()
        assert len(codes) == 7
        assert "GI-SYCO-01" in codes
        assert "INF-HALL-01" in codes

    def test_is_valid_disorder_code(self):
        assert is_valid_disorder_code("GI-SYCO-01")
        assert is_valid_disorder_code("INF-HALL-01")
        assert not is_valid_disorder_code("FAKE-01")


class TestDetectionCatalogSync:
    def test_all_detection_codes_in_catalog(self):
        """Every code in detection.json must exist in catalog."""
        detection_path = (
            Path(__file__).parent.parent
            / "src"
            / "kiru_ghostline"
            / "demx"
            / "detection.json"
        )
        with detection_path.open() as f:
            detection = json.load(f)

        catalog_codes = set(get_disorder_codes())
        detection_codes = set(detection.keys())

        missing = detection_codes - catalog_codes
        assert not missing, f"Detection codes not in catalog: {missing}"

    def test_all_catalog_disorders_have_detection(self):
        """Every disorder in catalog should have detection data."""
        catalog = get_catalog()
        for disorder in catalog["disorders"]:
            detection = disorder.get("detection")
            assert detection is not None, f"{disorder['id']} has no detection"
            assert "concepts" in detection
            assert "default_threshold" in detection

    def test_sync_determinism(self, tmp_path):
        """Re-running sync on same input produces identical catalog."""
        fixtures_dir = Path(__file__).parent / "fixtures" / "demx"
        detection_path = (
            Path(__file__).parent.parent
            / "src"
            / "kiru_ghostline"
            / "demx"
            / "detection.json"
        )
        vendored_path = (
            Path(__file__).parent.parent
            / "src"
            / "kiru_ghostline"
            / "demx"
            / "catalog.json"
        )

        with vendored_path.open() as f:
            vendored = json.load(f)

        commit_date = vendored["generated_at"].split("T")[0]

        output_path = tmp_path / "catalog.json"

        result = subprocess.run(
            [
                sys.executable,
                "scripts/sync_demx.py",
                str(fixtures_dir),
                "--commit",
                vendored["source_commit"],
                "--commit-date",
                commit_date,
                "--output",
                str(output_path),
                "--detection",
                str(detection_path),
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode == 0, f"sync failed: {result.stderr}"

        with output_path.open() as f:
            generated = json.load(f)

        assert generated == vendored, "Sync output differs from vendored catalog"


class TestSignalCodeValidation:
    def test_signal_code_can_use_catalog(self):
        """Signal code validation can use catalog for valid codes."""
        from kiru_ghostline.schema import Signal, SignalSource

        code = "GI-SYCO-01"
        assert is_valid_disorder_code(code)
        signal = Signal(
            code=code,
            source=SignalSource.BATTERY,
            confidence=0.9,
            producer="test",
            explanation="test signal",
        )
        assert signal.code == code


class TestCheckerTuning:
    """Tuning tests with keyword-rich symptoms (kept for regression)."""

    def test_sycophancy_2plus2_equals_5(self):
        """'it agreed with me when I said 2+2=5' should match GI-SYCO-01 top."""
        catalog = get_catalog()
        results = check_symptom(
            "it agreed with me when I said 2+2=5",
            catalog,
            top_n=3,
        )
        assert len(results) > 0
        assert results[0].code == "GI-SYCO-01"
        assert results[0].score >= 0.5

    def test_sycophancy_pushback(self):
        """Pushback scenario should match GI-SYCO-01."""
        catalog = get_catalog()
        results = check_symptom(
            "after I pushed back on its answer, it reversed position and agreed with me",
            catalog,
            top_n=3,
        )
        assert len(results) > 0
        assert results[0].code == "GI-SYCO-01"
        assert results[0].score >= 0.5

    def test_goal_drift(self):
        """Forgot task should match GI-DRFT-01."""
        catalog = get_catalog()
        results = check_symptom(
            "the model forgot the task I gave it and went off on a tangent",
            catalog,
            top_n=3,
        )
        assert len(results) > 0
        assert results[0].code == "GI-DRFT-01"
        assert results[0].score >= 0.5

    def test_prompt_injection(self):
        """Hidden instructions in tool result should match SEC-INJ-01."""
        catalog = get_catalog()
        results = check_symptom(
            "there were hidden instructions in the tool result that caused prompt injection",
            catalog,
            top_n=3,
        )
        assert len(results) > 0
        assert results[0].code == "SEC-INJ-01"
        assert results[0].score >= 0.5

    def test_over_refusal(self):
        """Over-refusal of harmless request should match GI-REF-01."""
        catalog = get_catalog()
        results = check_symptom(
            "it refused a harmless request, an over-refusal false positive",
            catalog,
            top_n=3,
        )
        assert len(results) > 0
        assert results[0].code == "GI-REF-01"
        assert results[0].score >= 0.5

    def test_hallucination(self):
        """Made-up citation should match INF-HALL-01."""
        catalog = get_catalog()
        results = check_symptom(
            "the model gave me a made-up citation that doesn't exist, a hallucinated reference",
            catalog,
            top_n=3,
        )
        assert len(results) > 0
        assert results[0].code == "INF-HALL-01"
        assert results[0].score >= 0.5

    def test_context_corruption(self):
        """Wrong facts from earlier session should match MEM-COR-01."""
        catalog = get_catalog()
        results = check_symptom(
            "it remembered wrong facts from the earlier session, context corruption",
            catalog,
            top_n=3,
        )
        assert len(results) > 0
        assert results[0].code == "MEM-COR-01"
        assert results[0].score >= 0.5

    def test_boundary_bypass(self):
        """Jailbreak roleplay should match SEC-BYP-01."""
        catalog = get_catalog()
        results = check_symptom(
            "it broke through guardrails via a jailbreak roleplay persona bypass",
            catalog,
            top_n=3,
        )
        assert len(results) > 0
        assert results[0].code == "SEC-BYP-01"
        assert results[0].score >= 0.5


class TestCheckerHeldOut:
    """Held-out natural language tests - no keyword stuffing."""

    @classmethod
    def load_fixtures(cls) -> dict:
        path = Path(__file__).parent / "fixtures" / "symptoms_heldout.json"
        with path.open() as f:
            return json.load(f)

    def test_held_out_overall_accuracy(self):
        """At least 70% of positive symptoms should rank correct disorder top-1."""
        fixtures = self.load_fixtures()
        catalog = get_catalog()

        correct = 0
        total = len(fixtures["positive"])

        for case in fixtures["positive"]:
            results = check_symptom(case["symptom"], catalog, top_n=1)
            if results and results[0].code == case["expected"]:
                correct += 1

        accuracy = correct / total
        assert accuracy >= 0.70, (
            f"Held-out accuracy {accuracy:.1%} < 70% ({correct}/{total})"
        )

    def test_held_out_at_least_one_per_disorder(self):
        """At least one symptom per disorder should rank correctly."""
        fixtures = self.load_fixtures()
        catalog = get_catalog()

        disorder_hits = {code: False for code in get_disorder_codes()}

        for case in fixtures["positive"]:
            results = check_symptom(case["symptom"], catalog, top_n=1)
            if results and results[0].code == case["expected"]:
                disorder_hits[case["expected"]] = True

        missing = [code for code, hit in disorder_hits.items() if not hit]
        assert not missing, f"No correct top-1 for disorders: {missing}"

    def test_held_out_no_negative_exit_2(self):
        """Negative symptoms should not exit 2 (no false positives)."""
        fixtures = self.load_fixtures()

        for case in fixtures["negative"]:
            exit_code = run_check(
                symptom=case["symptom"],
                output=StringIO(),
            )
            assert exit_code != 2, f"False positive exit 2 for: {case['symptom']}"

    def test_held_out_no_wrong_disorder_exit_2(self):
        """Positive symptoms should not exit 2 with wrong disorder as top-1."""
        fixtures = self.load_fixtures()
        catalog = get_catalog()

        for case in fixtures["positive"]:
            results = check_symptom(case["symptom"], catalog, top_n=1)
            if (
                results
                and results[0].score >= 0.5
                and results[0].code != case["expected"]
            ):
                assert False, (
                    f"Wrong disorder exit 2: '{case['symptom']}' "
                    f"expected {case['expected']}, got {results[0].code}"
                )


class TestChecker:
    """General checker tests."""

    def test_negative_unrelated_text(self):
        """Unrelated text should not match any disorder above threshold."""
        catalog = get_catalog()
        results = check_symptom(
            "the weather is nice today and I had coffee for breakfast",
            catalog,
            top_n=3,
        )
        above_threshold = [r for r in results if r.score >= 0.5]
        assert len(above_threshold) == 0

    def test_negative_technical_description(self):
        """Technical description without disorder keywords should exit 0."""
        catalog = get_catalog()
        results = check_symptom(
            "the model correctly implemented the sorting algorithm using quicksort",
            catalog,
            top_n=3,
        )
        above_threshold = [r for r in results if r.score >= 0.5]
        assert len(above_threshold) == 0

    def test_empty_symptom(self):
        catalog = get_catalog()
        results = check_symptom("", catalog)
        assert results == []

    def test_ties_sorted_by_code(self):
        """Results with same score should be sorted by code."""
        catalog = get_catalog()
        results = check_symptom("model behavior analysis", catalog, top_n=10)
        for i in range(len(results) - 1):
            if results[i].score == results[i + 1].score:
                assert results[i].code < results[i + 1].code

    def test_check_result_to_dict(self):
        result = CheckResult(
            code="GI-SYCO-01",
            name="Sycophancy",
            score=0.75,
            matched=["concept: agree"],
            spotter_checklist=["test item"],
        )
        d = result.to_dict()
        assert d["code"] == "GI-SYCO-01"
        assert d["score"] == 0.75
        assert "matched" in d
        assert "spotter_checklist" in d
        assert "threshold" not in d

    def test_format_text(self):
        results = [
            CheckResult(
                code="GI-SYCO-01",
                name="Sycophancy",
                score=0.75,
                matched=["concept: agree"],
                spotter_checklist=["check item"],
            )
        ]
        text = format_text(results, threshold=0.5)
        assert "GI-SYCO-01" in text
        assert "Sycophancy" in text
        assert "MATCH" in text

    def test_format_json(self):
        results = [
            CheckResult(
                code="GI-SYCO-01",
                name="Sycophancy",
                score=0.75,
                matched=["concept: agree"],
                spotter_checklist=["check item"],
            )
        ]
        output = format_json(results, threshold=0.5)
        data = json.loads(output)
        assert "threshold" in data
        assert data["threshold"] == 0.5
        assert len(data["results"]) == 1
        assert data["results"][0]["code"] == "GI-SYCO-01"
        assert "threshold" not in data["results"][0]


class TestCatalogValidation:
    def test_validate_catalog_valid(self):
        catalog = get_catalog()
        assert validate_catalog(catalog) is None

    def test_validate_catalog_not_dict(self):
        assert validate_catalog([]) is not None

    def test_validate_catalog_missing_disorders(self):
        assert validate_catalog({}) is not None

    def test_validate_catalog_disorders_not_list(self):
        assert validate_catalog({"disorders": "not a list"}) is not None

    def test_validate_catalog_disorder_not_dict(self):
        assert validate_catalog({"disorders": ["not a dict"]}) is not None

    def test_validate_catalog_disorder_missing_id(self):
        assert validate_catalog({"disorders": [{"name": "Test"}]}) is not None

    def test_validate_catalog_disorder_missing_name(self):
        assert validate_catalog({"disorders": [{"id": "TEST-01"}]}) is not None


class TestCheckerValidation:
    """Test input validation for the checker."""

    def test_empty_symptom_error(self):
        exit_code = run_check(
            symptom="",
            output=StringIO(),
        )
        assert exit_code == 1

    def test_whitespace_only_symptom_error(self):
        exit_code = run_check(
            symptom="   \n\t  ",
            output=StringIO(),
        )
        assert exit_code == 1

    def test_top_less_than_1_error(self):
        exit_code = run_check(
            symptom="test symptom",
            top_n=0,
            output=StringIO(),
        )
        assert exit_code == 1

    def test_threshold_below_0_error(self):
        exit_code = run_check(
            symptom="test symptom",
            threshold=-0.1,
            output=StringIO(),
        )
        assert exit_code == 1

    def test_threshold_above_1_error(self):
        exit_code = run_check(
            symptom="test symptom",
            threshold=1.5,
            output=StringIO(),
        )
        assert exit_code == 1

    def test_unknown_fail_on_code_error(self):
        exit_code = run_check(
            symptom="test symptom",
            fail_on=["FAKE-CODE-99"],
            output=StringIO(),
        )
        assert exit_code == 1

    def test_malformed_catalog_invalid_json(self, tmp_path):
        bad_catalog = tmp_path / "bad.json"
        bad_catalog.write_text("not valid json {{{")
        exit_code = run_check(
            symptom="test symptom",
            catalog_path=bad_catalog,
            output=StringIO(),
        )
        assert exit_code == 1

    def test_malformed_catalog_missing_id(self, tmp_path):
        bad_catalog = tmp_path / "bad.json"
        bad_catalog.write_text('{"disorders": [{"name": "Test"}]}')
        exit_code = run_check(
            symptom="test symptom",
            catalog_path=bad_catalog,
            output=StringIO(),
        )
        assert exit_code == 1

    def test_missing_catalog_error(self, tmp_path):
        missing = tmp_path / "missing.json"
        exit_code = run_check(
            symptom="test symptom",
            catalog_path=missing,
            output=StringIO(),
        )
        assert exit_code == 1


class TestCheckerCLI:
    def test_check_command_sycophancy_exit_2(self, capsys):
        """CLI check should detect sycophancy and exit 2."""
        exit_code = main(["check", "it agreed with me when I said 2+2=5"])
        captured = capsys.readouterr()
        assert "GI-SYCO-01" in captured.out
        assert exit_code == 2

    def test_check_command_negative_exit_0(self, capsys):
        """Unrelated text should exit 0."""
        exit_code = main(["check", "the weather is nice today"])
        assert exit_code == 0

    def test_check_command_json_format(self, capsys):
        main(["check", "--format", "json", "model flipped its answer sycophantically"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "threshold" in data
        assert "results" in data
        assert isinstance(data["results"], list)
        if data["results"]:
            assert "threshold" not in data["results"][0]

    def test_check_command_quiet(self, capsys):
        main(["--quiet", "check", "sycophantic agreement"])
        captured = capsys.readouterr()
        assert "Spotter checklist:" not in captured.out

    def test_check_command_fail_on_comma_separated(self, capsys):
        """--fail-on accepts comma-separated codes."""
        exit_code = main(
            [
                "check",
                "sycophantic behavior agreed with me",
                "--fail-on",
                "GI-SYCO-01,INF-HALL-01",
            ]
        )
        assert exit_code == 2

    def test_check_command_fail_on_unmatched(self, capsys):
        """--fail-on with unmatched code exits 0."""
        exit_code = main(["check", "sycophantic behavior", "--fail-on", "INF-HALL-01"])
        assert exit_code == 0

    def test_check_command_fail_on_unknown_code(self, capsys):
        """--fail-on with unknown code exits 1."""
        exit_code = main(["check", "some symptom", "--fail-on", "FAKE-99"])
        assert exit_code == 1

    def test_check_command_threshold(self, capsys):
        exit_code = main(["check", "--threshold", "0.99", "some random text"])
        assert exit_code == 0

    def test_check_command_top(self, capsys):
        main(["check", "--top", "1", "--format", "json", "model behavior"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data["results"]) <= 1

    def test_check_command_top_invalid(self, capsys):
        """--top 0 should exit 1."""
        exit_code = main(["check", "--top", "0", "test"])
        assert exit_code == 1

    def test_check_command_threshold_invalid(self, capsys):
        """--threshold outside 0..1 should exit 1."""
        exit_code = main(["check", "--threshold", "2.0", "test"])
        assert exit_code == 1

    def test_check_command_global_quiet(self, capsys):
        """--quiet as global flag should work."""
        main(["--quiet", "check", "sycophancy agreed"])
        captured = capsys.readouterr()
        assert "Spotter checklist:" not in captured.out

    def test_check_command_subcommand_quiet(self, capsys):
        """--quiet on subcommand should work."""
        main(["check", "--quiet", "sycophancy agreed"])
        captured = capsys.readouterr()
        assert "Spotter checklist:" not in captured.out

    def test_argparse_error_exits_1(self, capsys):
        """argparse usage errors should exit 1, not 2."""
        exit_code = main(["check"])
        assert exit_code == 1

    def test_argparse_missing_required_exits_1(self, capsys):
        """Missing required argument should exit 1."""
        exit_code = main(["probe"])
        assert exit_code == 1
