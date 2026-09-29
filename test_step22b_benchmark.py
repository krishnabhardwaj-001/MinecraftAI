"""
test_step22b_benchmark.py - Test Suite for Step 22B CI/CD & Automated Evaluation Benchmark

Verifies:
1. Dataset schema validity (all cases parse cleanly into BenchmarkCase)
2. Every benchmark case contains all required fields
3. Category coverage across all 16 required capability domains
4. Deterministic benchmark execution across repeated runs
5. Expected clarification behavior (ambiguous requests flag clarification)
6. Expected semantic IR structure for property modifications
7. Expected mechanism selection across mechanism domains
8. Expected validator and QA outcomes for valid and invalid cases
9. Absence of hardcoded case-ID or prompt-specific shortcuts
10. Stable, well-formed benchmark summary and reporting
"""

import json
import re
import unittest
from pathlib import Path

from eval.models import BenchmarkCase, BenchmarkSummary, CaseEvaluationResult
from eval.benchmark import BenchmarkRunner
from ai.numeric_interpreter import NumericSemanticInterpreter
from ai.clarification import SemanticClarificationEngine


class TestStep22BBenchmark(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parent
        cls.dataset_path = cls.repo_root / "eval" / "dataset.json"
        with open(cls.dataset_path, "r", encoding="utf-8") as f:
            cls.raw_data = json.load(f)
        cls.cases = [BenchmarkCase(**item) for item in cls.raw_data]
        cls.runner = BenchmarkRunner(dataset_path=cls.dataset_path)

    def test_01_dataset_schema_validity(self):
        """1. Dataset schema validity: all entries parse as BenchmarkCase without errors."""
        self.assertGreaterEqual(len(self.cases), 50, "Benchmark must contain at least 50 cases.")
        for case in self.cases:
            self.assertIsInstance(case, BenchmarkCase)
            self.assertTrue(case.id.startswith("case_"), f"Case ID '{case.id}' must start with 'case_'")

    def test_02_benchmark_case_required_fields(self):
        """2. Every benchmark case has required fields."""
        for case in self.cases:
            self.assertTrue(bool(case.id.strip()), "Case ID must not be blank")
            self.assertTrue(bool(case.category.strip()), f"Case {case.id} must have a non-empty category")
            self.assertTrue(bool(case.request.strip()), f"Case {case.id} must have a non-empty request")
            self.assertIsInstance(case.metadata, dict, f"Case {case.id} metadata must be a dictionary")
            self.assertIsInstance(case.requires_clarification, bool)
            self.assertIsInstance(case.expect_validation_success, bool)

    def test_03_category_coverage(self):
        """3. Category coverage: all 16 required capability categories represented with >= 3 cases each."""
        required_categories = [
            "mob_loot",
            "functions",
            "function_tags",
            "predicates",
            "advancements",
            "recipes",
            "state_machines",
            "scoreboard_operations",
            "property_multipliers",
            "property_relative",
            "property_percentage",
            "property_absolute",
            "entity_specific_targets",
            "compound_requests",
            "clarification_required",
            "invalid_unsupported"
        ]
        counts = {}
        for case in self.cases:
            counts[case.category] = counts.get(case.category, 0) + 1

        for cat in required_categories:
            self.assertIn(cat, counts, f"Required category '{cat}' missing from benchmark dataset")
            self.assertGreaterEqual(counts[cat], 3, f"Category '{cat}' must have at least 3 cases, got {counts[cat]}")

    def test_04_deterministic_benchmark_execution(self):
        """4. Deterministic benchmark execution: repeated evaluation yields identical metrics."""
        summary1 = self.runner.run(limit=10)
        summary2 = self.runner.run(limit=10)

        self.assertEqual(summary1.total_cases, summary2.total_cases)
        self.assertEqual(summary1.passed_cases, summary2.passed_cases)
        self.assertEqual(summary1.failed_cases, summary2.failed_cases)
        self.assertEqual(summary1.clarification_cases, summary2.clarification_cases)
        self.assertEqual(summary1.validation_failures, summary2.validation_failures)
        self.assertEqual(summary1.qa_failures, summary2.qa_failures)

        for r1, r2 in zip(summary1.results, summary2.results):
            self.assertEqual(r1.case_id, r2.case_id)
            self.assertEqual(r1.passed, r2.passed)
            self.assertEqual(r1.semantic_interpretation_passed, r2.semantic_interpretation_passed)
            self.assertEqual(r1.validation_passed, r2.validation_passed)
            self.assertEqual(r1.qa_passed, r2.qa_passed)

    def test_05_expected_clarification_behavior(self):
        """5. Expected clarification behavior: ambiguous requests trigger clarification."""
        clarification_cases = [c for c in self.cases if c.category == "clarification_required"]
        self.assertGreaterEqual(len(clarification_cases), 3)

        engine = SemanticClarificationEngine()
        for case in clarification_cases:
            self.assertTrue(case.requires_clarification)
            eval_res = self.runner.evaluate_case(case)
            self.assertTrue(eval_res.passed, f"Clarification case {case.id} failed: {eval_res.errors}")
            self.assertTrue(eval_res.clarification_passed)
            self.assertIn("Clarification", eval_res.details)

    def test_06_expected_semantic_ir(self):
        """6. Expected semantic IR: property modifications produce structured representations."""
        property_cases = [c for c in self.cases if c.category in (
            "property_multipliers", "property_relative", "property_percentage", "property_absolute"
        )]
        self.assertGreaterEqual(len(property_cases), 12)

        interpreter = NumericSemanticInterpreter()
        for case in property_cases:
            eval_res = self.runner.evaluate_case(case)
            self.assertTrue(eval_res.passed, f"Property case {case.id} failed: {eval_res.errors}")
            self.assertTrue(eval_res.semantic_interpretation_passed)

            ir = interpreter.interpret(case.request)
            self.assertIsNotNone(ir.property, f"Case {case.id} was not recognized as property modification")
            if case.expected_property:
                self.assertEqual(ir.property, case.expected_property)
            if case.expected_operation:
                self.assertEqual(ir.operation, case.expected_operation)
            if case.expected_value_kind and ir.value:
                self.assertEqual(ir.value.kind, case.expected_value_kind)

    def test_07_expected_mechanism_selection(self):
        """7. Expected mechanism selection: verifies proper mapping to datapack mechanism domains."""
        expected_mappings = {
            "mob_loot": "loot_table",
            "functions": "function",
            "function_tags": "function_tag",
            "predicates": "predicate",
            "advancements": "advancement",
            "recipes": "recipe",
            "state_machines": "state_machine",
            "scoreboard_operations": ["scoreboard_objective", "function"],
        }
        for category, expected_mech in expected_mappings.items():
            matching_cases = [c for c in self.cases if c.category == category]
            for case in matching_cases:
                if isinstance(expected_mech, list):
                    self.assertIn(case.expected_mechanism, expected_mech,
                                  f"Case {case.id} unexpected mechanism {case.expected_mechanism}")
                else:
                    self.assertEqual(case.expected_mechanism, expected_mech,
                                     f"Case {case.id} expected mechanism {expected_mech}")

    def test_08_expected_validator_and_qa_outcomes(self):
        """8. Expected validator and QA outcome: valid cases pass; invalid/unsupported fail properly."""
        invalid_cases = [c for c in self.cases if c.category == "invalid_unsupported"]
        self.assertGreaterEqual(len(invalid_cases), 3)

        for case in invalid_cases:
            self.assertFalse(case.expect_validation_success)
            eval_res = self.runner.evaluate_case(case)
            self.assertTrue(eval_res.passed, f"Invalid case {case.id} handling failed: {eval_res.errors}")
            self.assertFalse(eval_res.validation_passed)

        valid_loot = [c for c in self.cases if c.category == "mob_loot"]
        for case in valid_loot:
            eval_res = self.runner.evaluate_case(case)
            self.assertTrue(eval_res.passed, f"Loot case {case.id} failed: {eval_res.errors}")
            self.assertTrue(eval_res.validation_passed)
            self.assertTrue(eval_res.qa_passed)

    def test_09_no_hardcoded_shortcuts(self):
        """9. No hardcoded request/entity implementation shortcuts in runner or generators."""
        benchmark_file = self.repo_root / "eval" / "benchmark.py"
        with open(benchmark_file, "r", encoding="utf-8") as f:
            code = f.read()

        # Check that benchmark.py does not branch on specific case IDs
        for case in self.cases:
            pattern = rf'case\.id\s*==\s*["\']{re.escape(case.id)}["\']'
            self.assertIsNone(re.search(pattern, code), f"Found hardcoded case ID check in benchmark.py: {case.id}")

        # Check that benchmark.py does not branch on entire exact prompt strings
        exact_request_check = re.search(r'case\.request\s*==\s*["\']', code)
        self.assertIsNone(exact_request_check, "Found hardcoded exact case.request matching in benchmark.py")

    def test_10_stable_benchmark_reporting(self):
        """10. Stable benchmark reporting: summary contains counts, categories, and formatted report."""
        summary = self.runner.run(limit=16)
        report_text = self.runner.format_report(summary)

        self.assertIn("MinecraftAI Automated Evaluation Benchmark Report", report_text)
        self.assertIn("Total Test Cases:", report_text)
        self.assertIn("Passed Cases:", report_text)
        self.assertIn("Average Duration Per Case:", report_text)
        self.assertIn("Category", report_text)
        self.assertIn("Accuracy", report_text)
        self.assertEqual(summary.total_cases, 16)
        self.assertIsInstance(summary.category_metrics, dict)
        self.assertGreater(len(summary.category_metrics), 0)


if __name__ == "__main__":
    unittest.main()
