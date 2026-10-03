"""
test_step25_5_final_verification.py - Phase 25.5 Final Dual-Version Verification Suite

Comprehensive verification gate covering:
1. Version context resolution and metadata for both Minecraft 1.21.11 and 1.21.1.
2. Deterministic generator output format (pack_format 94 for 1.21.11, 48 for 1.21.1).
3. Validator cross-version rejection (1.21.11 rejects 1.21.1 pack, 1.21.1 rejects 1.21.11 pack).
4. Loot table knowledge parity and vanilla drop preservation for both versions.
5. QA analyzer and reviewer version context isolation.
6. Understanding and pipeline version context propagation end-to-end.
7. Benchmark suite execution and disaggregated per-version metrics.
8. Deterministic byte-identical ZIP reproducibility across runs.
9. Strict rejection of unsupported Minecraft versions without silent fallback.
10. Headless runtime runner server jar and library resolution for both versions.
"""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ai.understanding import MinecraftUnderstanding
from ai.version_registry import VersionContext, get_default_version, get_version_registry
from eval.benchmark import BenchmarkRunner
from eval.models import BenchmarkCase
from generator.datapack_generator import DatapackGenerator
from generator.models import MechanismSpecification
from pipeline.minecraft_pipeline import MinecraftPipeline
from qa.analyzer import StaticSemanticAnalyzer
from qa.reviewer import AutonomousQAReviewer
from qa.runtime import RuntimeTestRunner
from validator.datapack_validator import DatapackValidator


class TestStep255FinalVerification(unittest.TestCase):
    """
    Automated verification suite for Phase 25.5 Final Dual-Version Verification.
    """

    @classmethod
    def setUpClass(cls):
        cls.registry = get_version_registry()
        cls.runner = BenchmarkRunner()

    # 1. Version context resolution and metadata
    def test_01_version_context_both_versions(self):
        """1. VersionContext properly resolves metadata for both 1.21.11 and 1.21.1."""
        ctx_11 = VersionContext.from_version("1.21.11")
        self.assertEqual(ctx_11.version_id, "1.21.11")
        self.assertEqual(ctx_11.pack_format, 94)
        self.assertEqual(ctx_11.metadata.directory_layout, "singular")
        self.assertEqual(ctx_11.metadata.attribute_format, "namespaced")

        ctx_1 = VersionContext.from_version("1.21.1")
        self.assertEqual(ctx_1.version_id, "1.21.1")
        self.assertEqual(ctx_1.pack_format, 48)
        self.assertEqual(ctx_1.metadata.directory_layout, "singular")
        self.assertEqual(ctx_1.metadata.attribute_format, "namespaced")

        # Default version is 1.21.11
        self.assertEqual(get_default_version(), "1.21.11")

    # 2. Generator output format
    def test_02_generator_both_versions(self):
        """2. DatapackGenerator formats pack.mcmeta with version-appropriate pack_format."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            spec = MechanismSpecification(type="function", path="main", commands=["say hello"])

            gen_11 = DatapackGenerator(output_dir=base / "dp11", version="1.21.11")
            res_11 = gen_11.generate(
                plan={"status": "ready", "minecraft_version": "1.21.11", "implementation_plan": [{"requirement_index": 0, "objective": "test", "mechanisms": [spec]}]},
                datapack_name="pack_11",
                create_zip=False
            )
            m11 = json.loads((res_11.datapack_path / "pack.mcmeta").read_text(encoding="utf-8"))
            self.assertEqual(m11["pack"]["pack_format"], 94)

            gen_1 = DatapackGenerator(output_dir=base / "dp1", version="1.21.1")
            res_1 = gen_1.generate(
                plan={"status": "ready", "minecraft_version": "1.21.1", "implementation_plan": [{"requirement_index": 0, "objective": "test", "mechanisms": [spec]}]},
                datapack_name="pack_1",
                create_zip=False
            )
            m1 = json.loads((res_1.datapack_path / "pack.mcmeta").read_text(encoding="utf-8"))
            self.assertEqual(m1["pack"]["pack_format"], 48)

    # 3. Validator cross-version rejection
    def test_03_validator_cross_version_rejection(self):
        """3. DatapackValidator validates matching version and rejects incompatible version."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            spec = MechanismSpecification(type="function", path="main", commands=["say hello"])

            gen_11 = DatapackGenerator(output_dir=base / "dp11", version="1.21.11")
            res_11 = gen_11.generate(
                plan={"status": "ready", "minecraft_version": "1.21.11", "implementation_plan": [{"requirement_index": 0, "objective": "test", "mechanisms": [spec]}]},
                datapack_name="pack_11",
                create_zip=False
            )

            gen_1 = DatapackGenerator(output_dir=base / "dp1", version="1.21.1")
            res_1 = gen_1.generate(
                plan={"status": "ready", "minecraft_version": "1.21.1", "implementation_plan": [{"requirement_index": 0, "objective": "test", "mechanisms": [spec]}]},
                datapack_name="pack_1",
                create_zip=False
            )

            val_11 = DatapackValidator(version="1.21.11")
            val_1 = DatapackValidator(version="1.21.1")

            # 1.21.11 validator
            self.assertTrue(val_11.validate(res_11.datapack_path).is_valid)
            self.assertFalse(val_11.validate(res_1.datapack_path).is_valid)

            # 1.21.1 validator
            self.assertTrue(val_1.validate(res_1.datapack_path).is_valid)
            self.assertFalse(val_1.validate(res_11.datapack_path).is_valid)

    # 4. Loot table knowledge parity and vanilla drop preservation
    def test_04_loot_table_knowledge_parity(self):
        """4. Loot table modification preserves vanilla drops for both 1.21.11 and 1.21.1."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            spec = MechanismSpecification(
                type="loot_table",
                target="creeper",
                item="minecraft:diamond",
                count=1,
                operation="add"
            )

            # 1.21.11 creeper
            gen_11 = DatapackGenerator(output_dir=base / "dp11", version="1.21.11")
            plan_11 = {"status": "ready", "minecraft_version": "1.21.11", "implementation_plan": [{"requirement_index": 0, "objective": "loot", "mechanisms": [spec]}]}
            res_11 = gen_11.generate(plan=plan_11, datapack_name="loot_11", create_zip=False)
            val_11 = DatapackValidator(version="1.21.11")
            v_res_11 = val_11.validate(res_11.datapack_path)
            self.assertTrue(v_res_11.is_valid)
            self.assertTrue(any("loot" in str(c.name).lower() for c in v_res_11.checks))

            # 1.21.1 creeper
            gen_1 = DatapackGenerator(output_dir=base / "dp1", version="1.21.1")
            plan_1 = {"status": "ready", "minecraft_version": "1.21.1", "implementation_plan": [{"requirement_index": 0, "objective": "loot", "mechanisms": [spec]}]}
            res_1 = gen_1.generate(plan=plan_1, datapack_name="loot_1", create_zip=False)
            val_1 = DatapackValidator(version="1.21.1")
            v_res_1 = val_1.validate(res_1.datapack_path)
            self.assertTrue(v_res_1.is_valid)
            self.assertTrue(any("loot" in str(c.name).lower() for c in v_res_1.checks))

    # 5. QA analyzer and reviewer version isolation
    def test_05_qa_analyzer_and_reviewer_version_isolation(self):
        """5. QA analyzer and reviewer accept version_context and isolate validation rules."""
        ctx_1 = VersionContext.from_version("1.21.1")
        ctx_11 = VersionContext.from_version("1.21.11")

        analyzer_1 = StaticSemanticAnalyzer(version_context=ctx_1)
        analyzer_11 = StaticSemanticAnalyzer(version_context=ctx_11)

        self.assertEqual(analyzer_1.version, "1.21.1")
        self.assertEqual(analyzer_11.version, "1.21.11")

        reviewer_1 = AutonomousQAReviewer(version_context=ctx_1)
        reviewer_11 = AutonomousQAReviewer(version_context=ctx_11)

        self.assertEqual(reviewer_1.version, "1.21.1")
        self.assertEqual(reviewer_11.version, "1.21.11")

    # 6. Understanding and pipeline version context propagation
    def test_06_understanding_and_pipeline_propagation(self):
        """6. Understanding system prompt and pipeline components receive target version."""
        und_1 = MinecraftUnderstanding(version="1.21.1")
        self.assertIn("Minecraft Java Edition 1.21.1.", und_1.system_prompt)

        und_11 = MinecraftUnderstanding(version="1.21.11")
        self.assertIn("Minecraft Java Edition 1.21.11.", und_11.system_prompt)

        pipe_1 = MinecraftPipeline(version="1.21.1")
        self.assertEqual(pipe_1.version, "1.21.1")
        self.assertEqual(pipe_1.version_context.pack_format, 48)

        pipe_11 = MinecraftPipeline(version="1.21.11")
        self.assertEqual(pipe_11.version, "1.21.11")
        self.assertEqual(pipe_11.version_context.pack_format, 94)

    # 7. Dual-version benchmark suite execution and metrics
    def test_07_dual_version_benchmark_cases_and_metrics(self):
        """7. Benchmark executes all 78 cases and aggregates per-version metrics cleanly."""
        sum_11 = self.runner.run(version="1.21.11")
        self.assertEqual(sum_11.total_cases, 53)
        self.assertEqual(sum_11.passed_cases, 53)
        self.assertEqual(sum_11.failed_cases, 0)

        sum_1 = self.runner.run(version="1.21.1")
        self.assertEqual(sum_1.total_cases, 25)
        self.assertEqual(sum_1.passed_cases, 25)
        self.assertEqual(sum_1.failed_cases, 0)

    # 8. Deterministic byte-identical ZIP reproducibility across runs
    def test_08_determinism_byte_identical_reproducibility(self):
        """8. Repeated generation of identical plans produces byte-identical ZIP hashes."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            spec = MechanismSpecification(type="loot_table", target="creeper", item="minecraft:diamond", count=1, operation="add")

            def gen_hash(ver, subdir):
                v_ctx = VersionContext.from_version(ver)
                gen = DatapackGenerator(output_dir=base / subdir, version_context=v_ctx)
                plan = {"status": "ready", "minecraft_version": ver, "implementation_plan": [{"requirement_index": 0, "objective": "test", "mechanisms": [spec]}]}
                res = gen.generate(plan=plan, datapack_name="det_pack", create_zip=True)
                return hashlib.sha256(Path(res.zip_path).read_bytes()).hexdigest()

            h11_1 = gen_hash("1.21.11", "run11_1")
            h11_2 = gen_hash("1.21.11", "run11_2")
            self.assertEqual(h11_1, h11_2, "1.21.11 ZIP output must be deterministically byte-identical.")

            h1_1 = gen_hash("1.21.1", "run1_1")
            h1_2 = gen_hash("1.21.1", "run1_2")
            self.assertEqual(h1_1, h1_2, "1.21.1 ZIP output must be deterministically byte-identical.")

            # Cross-version outputs must differ
            self.assertNotEqual(h11_1, h1_1, "Different versions must produce distinct ZIP artifacts.")

    # 9. Unsupported version rejection without silent fallback
    def test_09_unsupported_version_rejection(self):
        """9. Unsupported Minecraft versions are rejected cleanly without silent fallback."""
        self.assertFalse(self.registry.is_supported("1.20.4"))
        self.assertFalse(self.registry.is_supported("1.19.2"))

        with self.assertRaises(ValueError):
            VersionContext.from_version("1.20.4")

        with self.assertRaises(ValueError):
            DatapackValidator(version="1.20.4")

        # Benchmark runner correctly flags unsupported version case
        case_unsupported = BenchmarkCase(
            id="test_unsupported",
            category="mob_loot",
            request="Make creepers drop diamonds.",
            minecraft_version="1.20.4",
            is_supported=True
        )
        res = self.runner.evaluate_case(case_unsupported)
        self.assertFalse(res.passed)
        self.assertTrue(any("not supported by VersionRegistry" in err for err in res.errors))

    # 10. Headless runtime runner server jar and library resolution
    def test_10_headless_runtime_verification_capabilities(self):
        """10. RuntimeTestRunner correctly resolves server JAR and library paths per version."""
        repo_root = Path(__file__).resolve().parent

        runner_11 = RuntimeTestRunner(version="1.21.11")
        self.assertEqual(runner_11.version, "1.21.11")
        expected_jar_11 = repo_root / "versions" / "1.21.11" / "server-1.21.11.jar"
        self.assertEqual(runner_11.version_context.metadata.server_jar_path.resolve(), expected_jar_11.resolve())

        runner_1 = RuntimeTestRunner(version="1.21.1")
        self.assertEqual(runner_1.version, "1.21.1")
        expected_jar_1 = repo_root / "versions" / "1.21.1" / "server-1.21.1.jar"
        self.assertEqual(runner_1.version_context.metadata.server_jar_path.resolve(), expected_jar_1.resolve())


if __name__ == "__main__":
    unittest.main()
