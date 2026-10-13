"""Tests for DEM-X catalog and checker."""

import json
from pathlib import Path

from kiru_ghostline.checker import CheckResult, check_symptom, format_json, format_text
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
            assert "keywords" in detection
            assert "default_threshold" in detection


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


class TestChecker:
    def test_sycophancy_detection(self):
        """'it agreed with me when I said 2+2=5' should match GI-SYCO-01 top."""
        catalog = get_catalog()
        results = check_symptom(
            "it agreed with me when I said 2+2=5",
            catalog,
            top_n=3,
            threshold=0.1,
        )
        assert len(results) > 0
        assert results[0].code == "GI-SYCO-01"
        assert results[0].score > 0

    def test_hallucination_detection(self):
        """Fabricated citation should match INF-HALL-01."""
        catalog = get_catalog()
        results = check_symptom(
            "the model fabricated a citation and made up a fake reference",
            catalog,
            top_n=3,
            threshold=0.3,
        )
        assert len(results) > 0
        codes = [r.code for r in results]
        assert "INF-HALL-01" in codes

    def test_goal_drift_detection(self):
        """Lost track of objective should match GI-DRFT-01."""
        catalog = get_catalog()
        results = check_symptom(
            "the model drifted off-topic and lost track of the original goal",
            catalog,
            top_n=3,
            threshold=0.3,
        )
        assert len(results) > 0
        codes = [r.code for r in results]
        assert "GI-DRFT-01" in codes

    def test_empty_symptom(self):
        catalog = get_catalog()
        results = check_symptom("", catalog)
        assert results == []

    def test_no_match(self):
        catalog = get_catalog()
        results = check_symptom(
            "xyz123 completely unrelated gibberish",
            catalog,
            top_n=3,
            threshold=0.9,
        )
        matched = [r for r in results if r.score >= 0.9]
        assert len(matched) == 0

    def test_check_result_to_dict(self):
        result = CheckResult(
            code="GI-SYCO-01",
            name="Sycophancy",
            score=0.75,
            why=["keyword: agree"],
            spotter_items=["test item"],
        )
        d = result.to_dict()
        assert d["code"] == "GI-SYCO-01"
        assert d["score"] == 0.75
        assert "why" in d

    def test_format_text(self):
        results = [
            CheckResult(
                code="GI-SYCO-01",
                name="Sycophancy",
                score=0.75,
                why=["keyword: agree"],
                spotter_items=["check item"],
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
                why=["keyword: agree"],
                spotter_items=["check item"],
            )
        ]
        output = format_json(results)
        data = json.loads(output)
        assert len(data) == 1
        assert data[0]["code"] == "GI-SYCO-01"


class TestCheckerCLI:
    def test_check_command_sycophancy(self, capsys):
        """CLI check should detect sycophancy as top match."""
        exit_code = main(
            ["check", "--threshold", "0.1", "it agreed with me when I said 2+2=5"]
        )
        captured = capsys.readouterr()
        assert "GI-SYCO-01" in captured.out
        lines = [l for l in captured.out.split("\n") if l.strip()]
        assert "GI-SYCO-01" in lines[0]
        assert exit_code == 2

    def test_check_command_json_format(self, capsys):
        main(["check", "--format", "json", "model flipped its answer after pushback"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)

    def test_check_command_quiet(self, capsys):
        main(["check", "-q", "sycophantic agreement"])
        captured = capsys.readouterr()
        assert "Spotter checklist:" not in captured.out

    def test_check_command_fail_on(self, capsys):
        exit_code = main(
            ["check", "it agreed with me sycophantically", "--fail-on", "INF-HALL-01"]
        )
        assert exit_code == 0

    def test_check_command_threshold(self, capsys):
        exit_code = main(["check", "--threshold", "0.99", "some random text"])
        assert exit_code == 0

    def test_check_command_top(self, capsys):
        main(["check", "--top", "1", "--format", "json", "model behavior"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data) <= 1
