import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

from generator.datapack_generator import DatapackGenerator
from pipeline import MinecraftPipeline, run_minecraft_pipeline
from validator.datapack_validator import DatapackValidator


class CorruptFirstRunGenerator(DatapackGenerator):
    """
    Generator that intentionally creates a corrupted datapack on its first invocation
    (simulating a generator bug/defect), but produces clean output on subsequent calls.
    Used to test Stage 5 validation failure -> Stage 6 AI repair loop invocation.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.call_count = 0

    def generate(self, *args, **kwargs):
        self.call_count += 1
        res = super().generate(*args, **kwargs)
        if self.call_count == 1:
            # Corrupt pack.mcmeta by deleting it
            mcmeta = res.datapack_path / "pack.mcmeta"
            if mcmeta.exists():
                mcmeta.unlink()
            if res.zip_path and res.zip_path.exists():
                res.zip_path.unlink()
        return res


class PermanentlyCorruptGenerator(DatapackGenerator):
    """
    Generator that consistently corrupts generated datapacks on every invocation.
    Used to test that repair failure exhausts retries and returns a clean failure.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.call_count = 0

    def generate(self, *args, **kwargs):
        self.call_count += 1
        res = super().generate(*args, **kwargs)
        mcmeta = res.datapack_path / "pack.mcmeta"
        if mcmeta.exists():
            mcmeta.unlink()
        if res.zip_path and res.zip_path.exists():
            res.zip_path.unlink()
        return res


class TestMinecraftPipeline(unittest.TestCase):
    """
    Step 8 Comprehensive Test Suite for MinecraftAI Pipeline.
    Tests end-to-end flow, generic behavior, clarification, AI repair, and validation.
    """

    @classmethod
    def setUpClass(cls):
        cls.test_dir = Path("generated") / "test_pipeline_run"
        if cls.test_dir.exists():
            shutil.rmtree(cls.test_dir, ignore_errors=True)
        cls.test_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        if cls.test_dir.exists():
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    def tearDown(self):
        # Clean test directory contents between tests
        if self.test_dir.exists():
            for item in self.test_dir.iterdir():
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                elif item.is_file():
                    item.unlink(missing_ok=True)

    def test_1_creeper_drops_diamonds(self):
        """
        TEST 1:
        'Make every creeper drop diamonds.'
        Expected:
        - understanding ready
        - knowledge contains creeper loot table + diamond item
        - planner ready
        - generator succeeds
        - validator succeeds
        - repair is skipped
        - final ZIP exists
        """
        print("\n" + "=" * 70)
        print("TEST 1: Make every creeper drop diamonds (End-to-End Success)")
        print("=" * 70)

        result = run_minecraft_pipeline(
            request="Make every creeper drop diamonds.",
            minecraft_version="1.21.11",
            provider="ollama",
            create_zip=True,
            output_dir=self.test_dir,
            verbose=True
        )

        self.assertEqual(result.status, "success", f"Pipeline failed: {result.errors}")
        self.assertTrue(result.is_success)

        # 1. Understanding
        self.assertIsNotNone(result.understanding)
        self.assertIn(result.understanding.get("status"), ["ready", "understood"])

        # 2. Knowledge
        self.assertIsNotNone(result.context)
        knowledge = result.context.get("knowledge", {})
        loot_tables = knowledge.get("loot_tables", [])
        self.assertTrue(
            any("creeper" in str(t.get("path", "")) for t in loot_tables),
            "Creeper loot table should be retrieved."
        )
        items = knowledge.get("items", [])
        self.assertTrue(
            any("diamond" in str(i.get("name", "")) for i in items),
            "Diamond item should be retrieved."
        )

        # 3. Planner
        self.assertIsNotNone(result.plan)
        self.assertEqual(result.plan.get("status"), "ready")

        # 4. Generator
        self.assertIsNotNone(result.generation)
        self.assertTrue(Path(result.final_datapack_path).exists())

        # 5. Validator
        self.assertIsNotNone(result.validation)
        self.assertTrue(result.validation.is_valid)

        # 6. Repair skipped
        self.assertIsNone(result.repair, "Repair loop should be skipped for valid datapack.")

        # 7. Final ZIP exists and is valid
        self.assertIsNotNone(result.final_zip_path)
        self.assertTrue(Path(result.final_zip_path).exists())

        # Validate ZIP directly
        zip_val = DatapackValidator(version="1.21.11").validate(result.final_zip_path)
        self.assertTrue(zip_val.is_valid, f"ZIP validation failed: {zip_val.errors}")
        print("[OK] Test 1 passed: Creeper drops diamonds completed end-to-end cleanly.")

    def test_2_skeleton_drops_iron(self):
        """
        TEST 2:
        'Make every skeleton drop iron.'
        Expected:
        - generic behavior
        - no creeper-specific code
        - final datapack validates
        """
        print("\n" + "=" * 70)
        print("TEST 2: Make every skeleton drop iron (Generic Pipeline Behavior)")
        print("=" * 70)

        result = run_minecraft_pipeline(
            request="Make every skeleton drop iron.",
            minecraft_version="1.21.11",
            provider="ollama",
            create_zip=True,
            output_dir=self.test_dir,
            verbose=True
        )

        self.assertEqual(result.status, "success", f"Pipeline failed: {result.errors}")
        self.assertTrue(result.is_success)

        # Check knowledge is generic to skeleton and iron
        knowledge = result.context.get("knowledge", {})
        loot_tables = knowledge.get("loot_tables", [])
        self.assertTrue(
            any("skeleton" in str(t.get("path", "")) for t in loot_tables),
            "Skeleton loot table should be retrieved."
        )
        self.assertFalse(
            any("creeper" in str(t.get("path", "")) for t in loot_tables),
            "Should not retrieve creeper loot table for skeleton request."
        )

        # Validate generated datapack
        self.assertTrue(result.validation.is_valid)
        self.assertIsNotNone(result.final_zip_path)
        self.assertTrue(Path(result.final_zip_path).exists())
        print("[OK] Test 2 passed: Skeleton drops iron generated generically.")

    def test_3_ambiguous_request_stops_at_clarification(self):
        """
        TEST 3:
        Ambiguous request: 'Make the zombie stronger.'
        Expected:
        - pipeline stops at understanding/planning clarification
        - generator is NOT called
        """
        print("\n" + "=" * 70)
        print("TEST 3: Ambiguous Request Stops at Clarification")
        print("=" * 70)

        result = run_minecraft_pipeline(
            request="Make the zombie stronger.",
            minecraft_version="1.21.11",
            provider="ollama",
            create_zip=True,
            output_dir=self.test_dir,
            verbose=True
        )

        self.assertEqual(result.status, "needs_clarification")
        self.assertFalse(result.is_success)
        self.assertTrue(bool(result.clarification), "Clarification message must be provided.")
        self.assertIsNone(result.generation, "Generator must NOT be called for ambiguous requests.")
        self.assertIsNone(result.final_datapack_path, "No datapack path should be set.")
        self.assertIsNone(result.final_zip_path, "No ZIP path should be set.")
        print(f"[OK] Test 3 passed: Stopped at clarification: '{result.clarification}'")

    def test_4_invalid_generated_datapack_triggers_repair(self):
        """
        TEST 4:
        Invalid generated datapack:
        Expected:
        - validator fails
        - repair loop is invoked
        - repaired output is regenerated
        - validator runs again and succeeds
        """
        print("\n" + "=" * 70)
        print("TEST 4: Invalid Datapack Triggers Repair Loop & Re-validates")
        print("=" * 70)

        corrupt_generator = CorruptFirstRunGenerator(
            output_dir=self.test_dir,
            version="1.21.11"
        )
        pipeline = MinecraftPipeline(
            provider="ollama",
            version="1.21.11",
            output_dir=self.test_dir,
            generator=corrupt_generator,
            verbose=True
        )

        result = pipeline.run("Make every creeper drop diamonds.")

        self.assertEqual(result.status, "success")
        self.assertTrue(result.is_success)
        self.assertIsNotNone(result.repair, "Repair loop must have been invoked.")
        self.assertTrue(result.repair.is_success, "Repair loop must succeed.")
        self.assertGreaterEqual(result.repair.total_attempts, 1)
        self.assertTrue(result.validation.is_valid, "Final validation must be valid.")
        self.assertTrue(Path(result.final_datapack_path).exists())
        self.assertTrue(Path(result.final_zip_path).exists())
        print(f"[OK] Test 4 passed: Repair loop invoked and healed datapack in {result.repair.total_attempts} attempt(s).")

    def test_5_unrepairable_datapack_returns_failure(self):
        """
        TEST 5:
        Repair cannot fix the datapack:
        Expected:
        - pipeline returns failure
        - no invalid datapack is reported as successful
        - repair history is preserved
        """
        print("\n" + "=" * 70)
        print("TEST 5: Unrepairable Datapack Returns Clean Failure with History")
        print("=" * 70)

        perm_corrupt_generator = PermanentlyCorruptGenerator(
            output_dir=self.test_dir,
            version="1.21.11"
        )
        pipeline = MinecraftPipeline(
            provider="ollama",
            version="1.21.11",
            output_dir=self.test_dir,
            max_repair_attempts=2,
            generator=perm_corrupt_generator,
            verbose=True
        )

        result = pipeline.run("Make every creeper drop diamonds.")

        self.assertEqual(result.status, "failed")
        self.assertFalse(result.is_success)
        self.assertIsNotNone(result.repair, "Repair result should be recorded.")
        self.assertFalse(result.repair.is_success, "Repair should report failure.")
        self.assertEqual(len(result.repair.attempts), 2, "Both repair attempts must be recorded in history.")
        self.assertIsNone(result.final_datapack_path, "Must NEVER return an invalid datapack as successful.")
        self.assertIsNone(result.final_zip_path, "Must NEVER return an invalid ZIP as successful.")
        self.assertGreater(len(result.errors), 0, "Errors must be populated.")
        print("[OK] Test 5 passed: Unrepairable datapack halted cleanly and preserved 2 repair attempts in history.")

    def test_6_arbitrary_mob_item_combination(self):
        """
        TEST 6:
        Completely arbitrary mob/item combination:
        Example: 'Make spiders drop iron ingots.'
        Expected:
        - generic pipeline behavior
        - no spider-specific implementation
        - final datapack validates
        """
        print("\n" + "=" * 70)
        print("TEST 6: Arbitrary Mob/Item (Spiders -> Iron Ingots)")
        print("=" * 70)

        result = run_minecraft_pipeline(
            request="Make spiders drop iron ingots.",
            minecraft_version="1.21.11",
            provider="ollama",
            create_zip=True,
            output_dir=self.test_dir,
            verbose=True
        )

        self.assertEqual(result.status, "success", f"Pipeline failed: {result.errors}")
        self.assertTrue(result.is_success)

        knowledge = result.context.get("knowledge", {})
        loot_tables = knowledge.get("loot_tables", [])
        self.assertTrue(
            any("spider" in str(t.get("path", "")) for t in loot_tables),
            "Spider loot table should be retrieved."
        )
        items = knowledge.get("items", [])
        self.assertTrue(
            any("iron_ingot" in str(i.get("name", "")) for i in items),
            "Iron ingot item should be retrieved."
        )

        self.assertTrue(result.validation.is_valid)
        self.assertIsNotNone(result.final_zip_path)
        self.assertTrue(Path(result.final_zip_path).exists())
        print("[OK] Test 6 passed: Spiders drop iron ingots generated generically.")

    def test_7_zip_validation(self):
        """
        TEST 7:
        ZIP validation:
        Expected:
        - final ZIP itself is validated before pipeline reports success.
        - pipeline rejects invalid/tampered ZIP files.
        """
        print("\n" + "=" * 70)
        print("TEST 7: ZIP Validation & Verification")
        print("=" * 70)

        # 1. Normal run produces valid ZIP
        result = run_minecraft_pipeline(
            request="Make every creeper drop diamonds.",
            minecraft_version="1.21.11",
            create_zip=True,
            output_dir=self.test_dir,
            verbose=False
        )
        self.assertEqual(result.status, "success")
        self.assertIsNotNone(result.final_zip_path)

        zip_val = DatapackValidator(version="1.21.11").validate(result.final_zip_path)
        self.assertTrue(zip_val.is_valid, f"Generated ZIP was not valid: {zip_val.errors}")

        # 2. Corrupt the zip file and verify validator detects it
        corrupt_zip = Path(result.final_zip_path)
        with open(corrupt_zip, "wb") as f:
            f.write(b"NOT_A_VALID_ZIP_ARCHIVE_DATA")

        corrupt_val = DatapackValidator(version="1.21.11").validate(corrupt_zip)
        self.assertFalse(corrupt_val.is_valid, "Validator should detect corrupted ZIP file.")
        print("[OK] Test 7 passed: ZIP validation and corruption detection verified.")

    def test_8_regression_all_suites(self):
        """
        TEST 8:
        Regression: Run all existing suites:
        - test_retrieval.py
        - test_generator.py
        - test_validator.py
        - test_repair_loop.py
        All must pass.
        """
        print("\n" + "=" * 70)
        print("TEST 8: Regression Test Across All Existing Suites")
        print("=" * 70)

        suites = [
            "test_retrieval.py",
            "test_generator.py",
            "test_validator.py",
            "test_repair_loop.py"
        ]

        for suite in suites:
            print(f"--> Running {suite}...")
            proc = subprocess.run(
                [sys.executable, suite],
                capture_output=True,
                text=True,
                timeout=120
            )
            self.assertEqual(
                proc.returncode, 0,
                f"Regression suite {suite} failed with code {proc.returncode}.\nStdout: {proc.stdout}\nStderr: {proc.stderr}"
            )
            print(f"    [PASS] {suite}")

        print("[OK] Test 8 passed: All 4 regression test suites passed cleanly.")


if __name__ == "__main__":
    unittest.main()
