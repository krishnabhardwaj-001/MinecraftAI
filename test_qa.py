import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

from generator.datapack_generator import DatapackGenerator
from generator.models import MechanismSpecification
from pipeline.minecraft_pipeline import MinecraftPipeline
from pipeline.models import PipelineResult, PipelineStage
from qa.analyzer import StaticSemanticAnalyzer
from qa.models import (
    IntentVerificationResult,
    QACategory,
    QAFinding,
    QARepairPlan,
    QAResult,
    QASeverity,
)
from qa.repair import QARepairEngine
from qa.reviewer import AutonomousQAReviewer
from qa.runtime import RuntimeTestMode, RuntimeTestResult, RuntimeTestRunner
from validator.datapack_validator import DatapackValidator


class TestAutonomousQA(unittest.TestCase):
    """
    Step 14 Test Suite: Autonomous Datapack QA, Verification & Auto-Repair.
    Covers all 14 required verification points.
    """

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="minecraft_qa_test_"))
        self.validator = DatapackValidator(version="1.21.11")
        self.analyzer = StaticSemanticAnalyzer(version="1.21.11")
        self.reviewer = AutonomousQAReviewer(version="1.21.11")
        self.repair_engine = QARepairEngine(version="1.21.11")
        self.runtime_runner = RuntimeTestRunner(version="1.21.11")

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_minimal_pack(self, name: str) -> Path:
        pack_dir = self.test_dir / name
        pack_dir.mkdir(parents=True, exist_ok=True)
        mcmeta = {
            "pack": {
                "pack_format": 94,
                "min_format": [94, 0],
                "max_format": [94, 1],
                "description": "QA Test Pack"
            }
        }
        with open(pack_dir / "pack.mcmeta", "w", encoding="utf-8") as f:
            json.dump(mcmeta, f)
        return pack_dir

    # -------------------------------------------------------------------------
    # 1. QA Schema Validation
    # -------------------------------------------------------------------------
    def test_1_qa_schema_validation(self):
        finding = QAFinding(
            id="FIND-TEST-001",
            severity=QASeverity.ERROR,
            category=QACategory.EXECUTION_CONTEXT,
            file="data/minecraft_ai/function/tick.mcfunction",
            line_or_reference="Line 1",
            problem="Missing entity execution context.",
            explanation="Detailed explanation.",
            expected_behavior="Expected behavior."
        )
        intent = IntentVerificationResult(
            matches_intent=False,
            confidence=0.5,
            reasoning="Intent reasoning.",
            missing_aspects=["Missing feature"],
            unwanted_aspects=[]
        )
        result = QAResult(
            status="failed",
            summary="Review failed.",
            findings=[finding],
            intent_verification=intent
        )

        self.assertFalse(result.is_pass)
        self.assertEqual(len(result.error_findings), 1)
        self.assertEqual(result.error_findings[0].id, "FIND-TEST-001")

        # Test JSON round-trip
        data = result.model_dump()
        reconstructed = QAResult(**data)
        self.assertFalse(reconstructed.is_pass)
        self.assertEqual(reconstructed.findings[0].category, QACategory.EXECUTION_CONTEXT)

    # -------------------------------------------------------------------------
    # 2. Complete Datapack Review (Clean Valid Pack)
    # -------------------------------------------------------------------------
    def test_2_complete_datapack_review_clean(self):
        pack_dir = self._create_minimal_pack("clean_pack")
        fn_dir = pack_dir / "data" / "minecraft_ai" / "function"
        fn_dir.mkdir(parents=True, exist_ok=True)
        with open(fn_dir / "load.mcfunction", "w", encoding="utf-8") as f:
            f.write("# Clean load\nscoreboard objectives add test_obj dummy\nscoreboard players set #global test_obj 0\n")

        res = self.reviewer.review(
            datapack_dir=pack_dir,
            original_request="Initialize test objective."
        )
        self.assertTrue(res.is_pass)
        self.assertEqual(res.status, "passed")
        self.assertEqual(len(res.error_findings), 0)

    # -------------------------------------------------------------------------
    # 3. Missing Cross-File Reference Detection
    # -------------------------------------------------------------------------
    def test_3_missing_cross_file_reference_detection(self):
        pack_dir = self._create_minimal_pack("broken_refs_pack")
        tag_dir = pack_dir / "data" / "minecraft" / "tags" / "function"
        tag_dir.mkdir(parents=True, exist_ok=True)
        with open(tag_dir / "tick.json", "w", encoding="utf-8") as f:
            json.dump({"values": ["minecraft_ai:nonexistent_tick"]}, f)

        fn_dir = pack_dir / "data" / "minecraft_ai" / "function"
        fn_dir.mkdir(parents=True, exist_ok=True)
        with open(fn_dir / "caller.mcfunction", "w", encoding="utf-8") as f:
            f.write("execute if predicate minecraft_ai:nonexistent_pred run function minecraft_ai:missing_fn\n")
            f.write("scoreboard players set #global missing_objective 1\n")

        findings = self.analyzer.analyze(datapack_dir=pack_dir)
        finding_ids = [f.id for f in findings]

        # Should catch: missing function in tag, missing predicate call, missing function call, undeclared objective
        self.assertTrue(any("FIND-REF-TAG-MISSING-FN" in fid for fid in finding_ids))
        self.assertTrue(any("FIND-REF-MISSING-PRED-CALL" in fid for fid in finding_ids))
        self.assertTrue(any("FIND-REF-MISSING-FN-CALL" in fid for fid in finding_ids))
        self.assertTrue(any("FIND-REF-UNDECLARED-OBJ" in fid for fid in finding_ids))

    # -------------------------------------------------------------------------
    # 4. Invalid Execution Context Detection
    # -------------------------------------------------------------------------
    def test_4_invalid_execution_context_detection(self):
        pack_dir = self._create_minimal_pack("context_pack")
        fn_dir = pack_dir / "data" / "minecraft_ai" / "function"
        fn_dir.mkdir(parents=True, exist_ok=True)
        with open(fn_dir / "test.mcfunction", "w", encoding="utf-8") as f:
            # give @s without preceding 'as <selector>'
            f.write("give @s minecraft:diamond 1\n")
            # spatial command with as @a but missing at @s
            f.write("execute as @a run setblock ~ ~ ~ minecraft:stone\n")

        findings = self.analyzer.analyze(datapack_dir=pack_dir)
        cats = [f.category for f in findings]
        self.assertIn(QACategory.EXECUTION_CONTEXT, cats)
        self.assertTrue(any("FIND-CTX-MISSING-AS" in f.id for f in findings))
        self.assertTrue(any("FIND-CTX-MISSING-AT" in f.id for f in findings))

    # -------------------------------------------------------------------------
    # 5. State Initialization on Load Problems
    # -------------------------------------------------------------------------
    def test_5_state_initialization_problems(self):
        pack_dir = self._create_minimal_pack("load_init_pack")
        fn_dir = pack_dir / "data" / "minecraft_ai" / "function"
        fn_dir.mkdir(parents=True, exist_ok=True)
        with open(fn_dir / "load.mcfunction", "w", encoding="utf-8") as f:
            f.write("scoreboard objectives add rain_state dummy\n")
            f.write("scoreboard players set @a rain_state 0\n")

        tag_dir = pack_dir / "data" / "minecraft" / "tags" / "function"
        tag_dir.mkdir(parents=True, exist_ok=True)
        with open(tag_dir / "load.json", "w", encoding="utf-8") as f:
            json.dump({"values": ["minecraft_ai:load"]}, f)

        findings = self.analyzer.analyze(datapack_dir=pack_dir)
        self.assertTrue(any("FIND-CTX-LOAD-EMPTY-SEL" in f.id for f in findings))
        error_find = next(f for f in findings if "FIND-CTX-LOAD-EMPTY-SEL" in f.id)
        self.assertEqual(error_find.severity, QASeverity.ERROR)

    # -------------------------------------------------------------------------
    # 6. Temporal / State-Machine Reasoning (Ordering & Missing Reset)
    # -------------------------------------------------------------------------
    def test_6_temporal_state_machine_reasoning(self):
        pack_dir = self._create_minimal_pack("temporal_pack")
        fn_dir = pack_dir / "data" / "minecraft_ai" / "function"
        fn_dir.mkdir(parents=True, exist_ok=True)

        # tick function with ordering race condition and missing reset
        with open(fn_dir / "tick.mcfunction", "w", encoding="utf-8") as f:
            # Line 1 sets state to 1 BEFORE checking matches 0 on Line 2!
            f.write("execute if predicate minecraft_ai:is_active run scoreboard players set #global event_state 1\n")
            f.write("execute if score #global event_state matches 0 if predicate minecraft_ai:is_active as @a at @s run give @s minecraft:diamond 1\n")

        tag_dir = pack_dir / "data" / "minecraft" / "tags" / "function"
        tag_dir.mkdir(parents=True, exist_ok=True)
        with open(tag_dir / "tick.json", "w", encoding="utf-8") as f:
            json.dump({"values": ["minecraft_ai:tick"]}, f)

        findings = self.analyzer.analyze(datapack_dir=pack_dir)
        self.assertTrue(any("FIND-SM-ORDERING-INVERSION" in f.id for f in findings))
        self.assertTrue(any("FIND-SM-MISSING-RESET" in f.id for f in findings))

    # -------------------------------------------------------------------------
    # 7. Intent Mismatch Detection
    # -------------------------------------------------------------------------
    def test_7_intent_mismatch(self):
        pack_dir = self._create_minimal_pack("intent_pack")
        fn_dir = pack_dir / "data" / "minecraft_ai" / "function"
        fn_dir.mkdir(parents=True, exist_ok=True)
        with open(fn_dir / "tick.mcfunction", "w", encoding="utf-8") as f:
            # Missing transition state machine latch when user asked for "only once"
            f.write("execute if predicate minecraft_ai:is_raining as @a at @s run give @s minecraft:diamond 1\n")

        res = self.reviewer.review(
            datapack_dir=pack_dir,
            original_request="When it is raining, give me a diamond specifically only once when the rain starts."
        )
        self.assertFalse(res.is_pass)
        self.assertIsNotNone(res.intent_verification)
        self.assertFalse(res.intent_verification.matches_intent)
        self.assertIn("Continuous execution", str(res.intent_verification.unwanted_aspects))

    # -------------------------------------------------------------------------
    # 8. Structured Repair Plans (Updates MechanismSpecification, Not Raw Patch)
    # -------------------------------------------------------------------------
    def test_8_structured_repair_plans(self):
        plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "Original flawed plan",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Give diamond on rain",
                    "mechanisms": [
                        {
                            "type": "predicate",
                            "path": "is_raining",
                            "namespace": "minecraft_ai",
                            "condition_type": "minecraft:weather_check",
                            "condition_params": {"raining": True}
                        },
                        {
                            "type": "function",
                            "path": "load",
                            "namespace": "minecraft_ai",
                            "commands": [
                                "scoreboard objectives add rain_state dummy",
                                "scoreboard players set @a rain_state 0"
                            ]
                        },
                        {
                            "type": "function",
                            "path": "tick",
                            "namespace": "minecraft_ai",
                            "commands": [
                                "execute as @a if score @s rain_state matches 0 if predicate minecraft_ai:is_raining run give @s minecraft:diamond 1",
                                "execute as @a if predicate minecraft_ai:is_raining run scoreboard players set @s rain_state 1",
                                "execute as @a unless predicate minecraft_ai:is_raining run scoreboard players set @s rain_state 0"
                            ]
                        }
                    ]
                }
            ]
        }

        # Mock QA failure with LOAD-EMPTY-SEL
        finding = QAFinding(
            id="FIND-CTX-LOAD-EMPTY-SEL-2",
            severity=QASeverity.ERROR,
            category=QACategory.EXECUTION_CONTEXT,
            file="data/minecraft_ai/function/load.mcfunction",
            problem="Selector @a mutates state during load.",
            explanation="Explanation",
            expected_behavior="Expected"
        )
        qa_res = QAResult(
            status="failed",
            summary="QA failed",
            findings=[finding],
            intent_verification=IntentVerificationResult(
                matches_intent=True, reasoning="Matches", missing_aspects=[], unwanted_aspects=[]
            )
        )

        repair_plan, repaired_plan = self.repair_engine.diagnose_and_repair(
            qa_result=qa_res,
            plan=plan
        )

        self.assertTrue(repair_plan.regenerate)
        self.assertIn("#global", repair_plan.diagnosis)

        # Check repaired mechanisms: load commands must use #global
        load_cmds = repaired_plan["implementation_plan"][0]["mechanisms"][1]["commands"]
        self.assertIn("scoreboard players set #global rain_state 0", load_cmds)
        self.assertNotIn("scoreboard players set @a rain_state 0", load_cmds)

    # -------------------------------------------------------------------------
    # 9. Repair-Loop Retry Behavior (Enforces max_attempts)
    # -------------------------------------------------------------------------
    def test_9_repair_loop_retry_behavior(self):
        pipeline = MinecraftPipeline(
            max_repair_attempts=2,
            max_qa_repair_attempts=2,
            output_dir=self.test_dir
        )
        self.assertEqual(pipeline.max_qa_repair_attempts, 2)

    # -------------------------------------------------------------------------
    # 10. Repeated Identical Failure Detection
    # -------------------------------------------------------------------------
    def test_10_repeated_identical_failure_detection(self):
        finding = QAFinding(
            id="FIND-STUCK-ERROR-1",
            severity=QASeverity.ERROR,
            category=QACategory.COMMAND_SEMANTICS,
            problem="Persistent unresolvable error.",
            explanation="Explanation",
            expected_behavior="Expected"
        )
        qa_res = QAResult(
            status="failed",
            summary="Stuck error",
            findings=[finding],
            intent_verification=IntentVerificationResult(
                matches_intent=False, reasoning="Stuck", missing_aspects=["Stuck"], unwanted_aspects=[]
            )
        )

        # Attempt history showing identical finding in previous attempt
        prev_attempts = [
            {"attempt": 1, "error_finding_ids": ["FIND-STUCK-ERROR-1"]}
        ]

        repair_plan, _ = self.repair_engine.diagnose_and_repair(
            qa_result=qa_res,
            plan={"summary": "plan"},
            previous_attempts=prev_attempts
        )

        self.assertFalse(repair_plan.regenerate)
        self.assertIn("Repeated identical QA failure", repair_plan.diagnosis)

    # -------------------------------------------------------------------------
    # 11. Final READY Gate
    # -------------------------------------------------------------------------
    def test_11_final_ready_gate(self):
        # A PipelineResult with status="verified" and final_datapack_path is success
        res = PipelineResult(
            status="verified",
            original_request="Test request",
            final_datapack_path=str(self.test_dir)
        )
        self.assertTrue(res.is_success)

        # A PipelineResult with status="verification_failed" is NOT success
        fail_res = PipelineResult(
            status="verification_failed",
            original_request="Test request",
            final_datapack_path=str(self.test_dir)
        )
        self.assertFalse(fail_res.is_success)

    # -------------------------------------------------------------------------
    # 12. verification_failed Behavior
    # -------------------------------------------------------------------------
    def test_12_verification_failed_behavior(self):
        res = PipelineResult(
            status="verification_failed",
            original_request="Test",
            errors=["QA verification failed: Unresolved error findings."]
        )
        self.assertEqual(res.status, "verification_failed")
        self.assertFalse(res.is_success)

    # -------------------------------------------------------------------------
    # 13. Rain Regression Test (Generic Stateful Event Auto-Repair)
    # -------------------------------------------------------------------------
    def test_13_rain_regression_generic_auto_repair(self):
        generator = DatapackGenerator(output_dir=self.test_dir, version="1.21.11")

        # Flawed Step 13 plan with @a in load and per-player state in tick
        flawed_plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "When it is raining, give me a diamond only once when the rain starts",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Give diamond on rain start",
                    "mechanisms": [
                        MechanismSpecification(
                            type="predicate",
                            path="is_raining",
                            namespace="minecraft_ai",
                            condition_type="minecraft:weather_check",
                            condition_params={"raining": True}
                        ),
                        MechanismSpecification(
                            type="function",
                            path="load",
                            namespace="minecraft_ai",
                            commands=[
                                "scoreboard objectives add rain_state dummy",
                                "scoreboard players set @a rain_state 0"
                            ]
                        ),
                        MechanismSpecification(
                            type="function",
                            path="tick",
                            namespace="minecraft_ai",
                            commands=[
                                "execute as @a if score @s rain_state matches 0 if predicate minecraft_ai:is_raining run give @s minecraft:diamond 1",
                                "execute as @a if predicate minecraft_ai:is_raining run scoreboard players set @s rain_state 1",
                                "execute as @a unless predicate minecraft_ai:is_raining run scoreboard players set @s rain_state 0"
                            ]
                        ),
                        MechanismSpecification(
                            type="function_tag",
                            tag_name="load",
                            namespace="minecraft",
                            values=["minecraft_ai:load"]
                        ),
                        MechanismSpecification(
                            type="function_tag",
                            tag_name="tick",
                            namespace="minecraft",
                            values=["minecraft_ai:tick"]
                        )
                    ]
                }
            ]
        }

        gen_res = generator.generate(
            plan=flawed_plan,
            datapack_name="rain_regression_pack",
            create_zip=False
        )
        self.assertEqual(gen_res.status, "success")

        # 1. QA Review must FAIL on the flawed pack
        qa_res = self.reviewer.review(
            datapack_dir=gen_res.datapack_path,
            original_request="When it is raining, give me a diamond specifically only once when the rain starts."
        )
        self.assertFalse(qa_res.is_pass)
        error_cats = [f.category for f in qa_res.error_findings]
        self.assertIn(QACategory.EXECUTION_CONTEXT, error_cats)

        # 2. Repair Engine diagnoses and generates corrected plan
        repair_plan, repaired_plan = self.repair_engine.diagnose_and_repair(
            qa_result=qa_res,
            plan=flawed_plan
        )
        self.assertTrue(repair_plan.regenerate)

        # 3. Regenerate deterministically from repaired plan
        repaired_gen = generator.generate(
            plan=repaired_plan,
            datapack_name="rain_repaired_pack",
            create_zip=True
        )
        self.assertEqual(repaired_gen.status, "success")

        # 4. Re-run QA Review on repaired pack -> MUST PASS!
        qa_repaired = self.reviewer.review(
            datapack_dir=repaired_gen.datapack_path,
            original_request="When it is raining, give me a diamond specifically only once when the rain starts."
        )
        self.assertTrue(qa_repaired.is_pass, f"Repaired pack failed QA: {[f.problem for f in qa_repaired.error_findings]}")
        self.assertEqual(len(qa_repaired.error_findings), 0)

        # 5. Run runtime static simulation on repaired pack -> MUST PASS!
        sim_res = self.runtime_runner.run(
            datapack_dir=repaired_gen.datapack_path,
            mode=RuntimeTestMode.STATIC_SIMULATION
        )
        self.assertTrue(sim_res.passed, f"Runtime simulation failed: {sim_res.details}")
        self.assertEqual(sim_res.ticks_simulated, 10)

    # -------------------------------------------------------------------------
    # 14. Unrelated Semantic Regression (Night Event Context & Undeclared Obj)
    # -------------------------------------------------------------------------
    def test_14_unrelated_semantic_regression_generic_auto_repair(self):
        generator = DatapackGenerator(output_dir=self.test_dir, version="1.21.11")

        # Unrelated scenario: Night event with undeclared objective and unanchored give @s
        unrelated_flawed_plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "When night falls give an apple",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Give apple at night",
                    "mechanisms": [
                        MechanismSpecification(
                            type="predicate",
                            path="is_night",
                            namespace="minecraft_ai",
                            condition_type="minecraft:time_check",
                            condition_params={"value": {"min": 13000, "max": 24000}}
                        ),
                        MechanismSpecification(
                            type="function",
                            path="tick",
                            namespace="minecraft_ai",
                            commands=[
                                # Uses undeclared objective 'night_cycle' and unanchored 'give @s'
                                "execute if score #global night_cycle matches 0 if predicate minecraft_ai:is_night run give @s minecraft:apple 1",
                                "execute if predicate minecraft_ai:is_night run scoreboard players set #global night_cycle 1",
                                "execute unless predicate minecraft_ai:is_night run scoreboard players set #global night_cycle 0"
                            ]
                        ),
                        MechanismSpecification(
                            type="function_tag",
                            tag_name="tick",
                            namespace="minecraft",
                            values=["minecraft_ai:tick"]
                        )
                    ]
                }
            ]
        }

        gen_res = generator.generate(
            plan=unrelated_flawed_plan,
            datapack_name="night_event_pack",
            create_zip=False
        )

        # 1. QA must catch undeclared objective and missing @s context
        qa_res = self.reviewer.review(
            datapack_dir=gen_res.datapack_path,
            original_request="When night falls give me an apple."
        )
        self.assertFalse(qa_res.is_pass)
        finding_ids = [f.id for f in qa_res.error_findings]
        self.assertTrue(any("UNDECLARED-OBJ" in fid for fid in finding_ids))
        self.assertTrue(any("MISSING-AS" in fid for fid in finding_ids))

        # 2. Repair Engine repairs plan
        repair_plan, repaired_plan = self.repair_engine.diagnose_and_repair(
            qa_result=qa_res,
            plan=unrelated_flawed_plan
        )
        self.assertTrue(repair_plan.regenerate)

        # 3. Regenerate
        repaired_gen = generator.generate(
            plan=repaired_plan,
            datapack_name="night_event_repaired_pack",
            create_zip=True
        )

        # 4. Re-review -> MUST PASS!
        qa_repaired = self.reviewer.review(
            datapack_dir=repaired_gen.datapack_path,
            original_request="When night falls give me an apple."
        )
        self.assertTrue(qa_repaired.is_pass, f"Repaired pack failed QA: {[f.problem for f in qa_repaired.error_findings]}")
        self.assertEqual(len(qa_repaired.error_findings), 0)


if __name__ == "__main__":
    unittest.main()
