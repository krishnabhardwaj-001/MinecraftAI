"""
test_step25_4_dual_version_benchmark.py - Phase 25.4 Dual-Version Benchmark Test Suite

Verifies:
1. Existing 1.21.11 cases remain valid (53/53 pass).
2. Dataset supports explicit Minecraft versions ('1.21.11' and '1.21.1').
3. 1.21.1 cases are actually executed against 1.21.1 (VersionContext, pack_format 48).
4. 1.21.11 cases are actually executed against 1.21.11 (VersionContext, pack_format 94).
5. Missing version falls back to registered default ('1.21.11').
6. Benchmark reports results separately by version (version_metrics and report text).
7. Version-specific expectations are respected (pack_format and loot knowledge preservation).
8. No benchmark case silently executes against the wrong version (unsupported versions rejected, cross-version validation rejected).
9. Existing benchmark behavior remains compatible (category filtering, version filtering, JSON output).
10. Benchmark results are deterministic where expected across repeated runs.
"""

import json
import tempfile
import unittest
from pathlib import Path

from ai.version_registry import VersionContext, get_default_version, get_version_registry
from eval.benchmark import BenchmarkRunner
from eval.models import BenchmarkCase, BenchmarkSummary, CaseEvaluationResult
from generator.datapack_generator import DatapackGenerator
from generator.models import MechanismSpecification
from validator.datapack_validator import DatapackValidator


class TestStep254DualVersionBenchmark(unittest.TestCase):
    """
    Automated verification suite for Phase 25.4 Dual-Version Evaluation Benchmark.
    """

    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parent
        cls.dataset_path = cls.repo_root / "eval" / "dataset.json"
        cls.runner = BenchmarkRunner(dataset_path=cls.dataset_path)
        cls.cases = cls.runner.load_dataset()
        cls.registry = get_version_registry()

    # 1. Existing 1.21.11 cases remain valid
    def test_01_existing_1_21_11_cases_remain_valid(self):
        """1. Existing 1.21.11 cases: all 53 baseline cases execute and pass 100%."""
        cases_12111 = [c for c in self.cases if c.minecraft_version == "1.21.11"]
        self.assertEqual(len(cases_12111), 53, "Existing 1.21.11 cases count must remain exactly 53.")

        summary = self.runner.run(cases=cases_12111)
        self.assertEqual(summary.total_cases, 53)
        self.assertEqual(summary.passed_cases, 53)
        self.assertEqual(summary.failed_cases, 0)

    # 2. Dataset supports explicit Minecraft version
    def test_02_dataset_supports_explicit_minecraft_version(self):
        """2. Dataset supports explicit Minecraft versions: both 1.21.11 and 1.21.1 are present."""
        raw_data = json.loads(self.dataset_path.read_text(encoding="utf-8"))
        self.assertEqual(len(raw_data), 78, "Total dataset cases must be 78 (53 for 1.21.11 + 25 for 1.21.1).")

        explicit_1211 = [c for c in raw_data if c.get("minecraft_version") == "1.21.1"]
        self.assertEqual(len(explicit_1211), 25, "Must have exactly 25 explicit 1.21.1 cases in dataset.")

        # Ensure all cases parse into BenchmarkCase with valid version
        for c in self.cases:
            self.assertIn(c.minecraft_version, ("1.21.1", "1.21.11"))
            self.assertTrue(self.registry.is_supported(c.minecraft_version))

    # 3. 1.21.1 cases are actually executed against 1.21.1
    def test_03_1_21_1_cases_execute_against_1_21_1(self):
        """3. 1.21.1 cases execute against 1.21.1: evaluates with VersionContext 1.21.1 and format 48."""
        case = next(c for c in self.cases if c.id == "case_1211_01_loot_creeper_diamond")
        self.assertEqual(case.minecraft_version, "1.21.1")

        result = self.runner.evaluate_case(case)
        self.assertTrue(result.passed, f"1.21.1 creeper case failed: {result.errors}")
        self.assertEqual(result.minecraft_version, "1.21.1")

        # Verify that generating a 1.21.1 pack emits pack_format 48 and is rejected by 1.21.11 validator
        with tempfile.TemporaryDirectory(prefix="test_1211_exec_") as td:
            v_ctx = VersionContext.from_version("1.21.1")
            gen = DatapackGenerator(output_dir=Path(td), version_context=v_ctx)
            spec = MechanismSpecification(type="loot_table", target="creeper", item="minecraft:diamond", count=1, operation="add")
            plan = {
                "status": "ready",
                "minecraft_version": "1.21.1",
                "summary": "1.21.1 test",
                "implementation_plan": [{"requirement_index": 0, "objective": "test", "mechanisms": [spec]}]
            }
            res = gen.generate(plan=plan, datapack_name="test_1211_pack", create_zip=False)
            self.assertEqual(res.status, "success")

            mcmeta = json.loads((res.datapack_path / "pack.mcmeta").read_text(encoding="utf-8"))
            self.assertEqual(mcmeta["pack"]["pack_format"], 48)

            # 1.21.1 validator accepts
            val_1211 = DatapackValidator(version="1.21.1")
            self.assertTrue(val_1211.validate(res.datapack_path).is_valid)

            # 1.21.11 validator rejects
            val_12111 = DatapackValidator(version="1.21.11")
            self.assertFalse(val_12111.validate(res.datapack_path).is_valid)

    # 4. 1.21.11 cases are actually executed against 1.21.11
    def test_04_1_21_11_cases_execute_against_1_21_11(self):
        """4. 1.21.11 cases execute against 1.21.11: evaluates with VersionContext 1.21.11 and format 94."""
        case = next(c for c in self.cases if c.id == "case_01_loot_creeper_diamond")
        self.assertEqual(case.minecraft_version, "1.21.11")

        result = self.runner.evaluate_case(case)
        self.assertTrue(result.passed, f"1.21.11 creeper case failed: {result.errors}")
        self.assertEqual(result.minecraft_version, "1.21.11")

        # Verify that generating a 1.21.11 pack emits pack_format 94 and is rejected by 1.21.1 validator
        with tempfile.TemporaryDirectory(prefix="test_12111_exec_") as td:
            v_ctx = VersionContext.from_version("1.21.11")
            gen = DatapackGenerator(output_dir=Path(td), version_context=v_ctx)
            spec = MechanismSpecification(type="loot_table", target="creeper", item="minecraft:diamond", count=1, operation="add")
            plan = {
                "status": "ready",
                "minecraft_version": "1.21.11",
                "summary": "1.21.11 test",
                "implementation_plan": [{"requirement_index": 0, "objective": "test", "mechanisms": [spec]}]
            }
            res = gen.generate(plan=plan, datapack_name="test_12111_pack", create_zip=False)
            self.assertEqual(res.status, "success")

            mcmeta = json.loads((res.datapack_path / "pack.mcmeta").read_text(encoding="utf-8"))
            self.assertEqual(mcmeta["pack"]["pack_format"], 94)

            # 1.21.11 validator accepts
            val_12111 = DatapackValidator(version="1.21.11")
            self.assertTrue(val_12111.validate(res.datapack_path).is_valid)

            # 1.21.1 validator rejects
            val_1211 = DatapackValidator(version="1.21.1")
            self.assertFalse(val_1211.validate(res.datapack_path).is_valid)

    # 5. Missing version falls back to registered default
    def test_05_missing_version_falls_back_to_registered_default(self):
        """5. Missing or None version: cleanly falls back to registered project default (1.21.11)."""
        case_no_ver = BenchmarkCase(
            id="case_fallback_test",
            category="mob_loot",
            request="Make every creeper drop diamonds.",
            expected_mechanism="loot_table",
            expected_target="creeper",
            metadata={"item": "minecraft:diamond"}
        )
        self.assertEqual(case_no_ver.minecraft_version, get_default_version())
        self.assertEqual(case_no_ver.minecraft_version, "1.21.11")

        res = self.runner.evaluate_case(case_no_ver)
        self.assertEqual(res.minecraft_version, "1.21.11")
        self.assertTrue(res.passed)

        # Explicit None falls back as well via field_validator
        case_none_ver = BenchmarkCase(
            id="case_none_ver_test",
            category="mob_loot",
            request="Make every creeper drop diamonds.",
            expected_mechanism="loot_table",
            expected_target="creeper",
            metadata={"item": "minecraft:diamond"},
            minecraft_version=None
        )
        self.assertEqual(case_none_ver.minecraft_version, "1.21.11")

    # 6. Benchmark reports results separately by version
    def test_06_benchmark_reports_results_separately_by_version(self):
        """6. Benchmark reports results separately by version: version_metrics and formatted output."""
        summary = self.runner.run()

        self.assertIn("1.21.11", summary.version_metrics)
        self.assertIn("1.21.1", summary.version_metrics)

        # 1.21.11 metrics
        m11 = summary.version_metrics["1.21.11"]
        self.assertEqual(m11["total"], 53)
        self.assertEqual(m11["passed"], 53)
        self.assertEqual(m11["failed"], 0)
        self.assertEqual(m11["accuracy_pct"], 100.0)

        # 1.21.1 metrics
        m1 = summary.version_metrics["1.21.1"]
        self.assertEqual(m1["total"], 25)
        self.assertEqual(m1["passed"], 25)
        self.assertEqual(m1["failed"], 0)
        self.assertEqual(m1["accuracy_pct"], 100.0)

        # Formatted report text contains both version sections
        report = self.runner.format_report(summary)
        self.assertIn("Version Summary", report)
        self.assertIn("VERSION 1.21.1", report)
        self.assertIn("VERSION 1.21.11", report)
        self.assertIn("Cases:   25", report)
        self.assertIn("Cases:   53", report)

    # 7. Version-specific expectations are respected
    def test_07_version_specific_expectations_respected(self):
        """7. Version-specific expectations respected: pack_format verified per version in evaluation."""
        case_1211 = next(c for c in self.cases if c.id == "case_1211_01_loot_creeper_diamond")
        self.assertEqual(case_1211.metadata.get("expected_pack_format"), 48)

        # Case passes when generated with 48
        res = self.runner.evaluate_case(case_1211)
        self.assertTrue(res.passed)

        # Synthetic mismatch: case expecting format 99 fails pack_format check
        case_mismatch = BenchmarkCase(
            id="case_synthetic_mismatch",
            category="mob_loot",
            request="Make every creeper drop diamonds.",
            minecraft_version="1.21.1",
            expected_mechanism="loot_table",
            metadata={"item": "minecraft:diamond", "expected_pack_format": 99}
        )
        res_mismatch = self.runner.evaluate_case(case_mismatch)
        self.assertFalse(res_mismatch.passed)
        self.assertTrue(any("Expected pack_format 99, got 48" in err for err in res_mismatch.errors))

    # 8. No benchmark case silently executes against the wrong version
    def test_08_no_case_silently_executes_against_wrong_version(self):
        """8. No case executes against wrong version: unsupported versions rejected; cross-version detected."""
        # Unsupported version with is_supported=True must fail
        unsupported_case = BenchmarkCase(
            id="case_unsupported_ver",
            category="mob_loot",
            request="Make creepers drop diamonds.",
            minecraft_version="1.20.1",
            is_supported=True
        )
        res = self.runner.evaluate_case(unsupported_case)
        self.assertFalse(res.passed)
        self.assertTrue(any("not supported by VersionRegistry" in err for err in res.errors))

        # Unsupported version with is_supported=False passes as expected rejection
        unsupported_neg_case = BenchmarkCase(
            id="case_unsupported_neg",
            category="invalid_unsupported",
            request="Make creepers drop diamonds.",
            minecraft_version="1.20.1",
            is_supported=False,
            expect_validation_success=False
        )
        res_neg = self.runner.evaluate_case(unsupported_neg_case)
        self.assertTrue(res_neg.passed)
        self.assertIn("unsupported Minecraft version '1.20.1'", res_neg.details)

    # 9. Existing benchmark behavior remains compatible
    def test_09_existing_benchmark_behavior_remains_compatible(self):
        """9. Existing benchmark compatibility: CLI filtering, category filtering, and JSON export."""
        # Version filter 1.21.11 returns only 53 cases
        sum_11 = self.runner.run(version="1.21.11")
        self.assertEqual(sum_11.total_cases, 53)
        self.assertEqual(list(sum_11.version_metrics.keys()), ["1.21.11"])

        # Version filter 1.21.1 returns only 25 cases
        sum_1 = self.runner.run(version="1.21.1")
        self.assertEqual(sum_1.total_cases, 25)
        self.assertEqual(list(sum_1.version_metrics.keys()), ["1.21.1"])

        # Category filter aggregates across versions
        sum_loot = self.runner.run(category="mob_loot")
        self.assertEqual(sum_loot.total_cases, 7)  # 4 from 1.21.11 + 3 from 1.21.1
        self.assertEqual(sum_loot.passed_cases, 7)

        # JSON dump contains version_metrics
        json_str = sum_loot.model_dump_json()
        parsed = json.loads(json_str)
        self.assertIn("version_metrics", parsed)
        self.assertIn("1.21.1", parsed["version_metrics"])
        self.assertIn("1.21.11", parsed["version_metrics"])

    # 10. Benchmark results are deterministic where expected
    def test_10_benchmark_results_are_deterministic(self):
        """10. Deterministic execution: repeated evaluation of mixed-version cases produces identical outcomes."""
        sample_cases = [c for c in self.cases if c.id in (
            "case_01_loot_creeper_diamond",
            "case_1211_01_loot_creeper_diamond",
            "case_08_tag_tick_loop",
            "case_1211_07_tag_tick_loop",
            "case_11_pred_weather_rain",
            "case_1211_09_pred_weather_rain"
        )]
        self.assertEqual(len(sample_cases), 6)

        run1 = self.runner.run(cases=sample_cases)
        run2 = self.runner.run(cases=sample_cases)

        self.assertEqual(run1.total_cases, run2.total_cases)
        self.assertEqual(run1.passed_cases, run2.passed_cases)
        self.assertEqual(run1.failed_cases, run2.failed_cases)

        for r1, r2 in zip(run1.results, run2.results):
            self.assertEqual(r1.case_id, r2.case_id)
            self.assertEqual(r1.minecraft_version, r2.minecraft_version)
            self.assertEqual(r1.passed, r2.passed)
            self.assertEqual(r1.validation_passed, r2.validation_passed)
            self.assertEqual(r1.qa_passed, r2.qa_passed)
            self.assertEqual(r1.errors, r2.errors)


if __name__ == "__main__":
    unittest.main()
