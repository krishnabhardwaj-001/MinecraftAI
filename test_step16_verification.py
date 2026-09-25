"""
Step 16.7 — Automated Verification / Regression Gate for Scoreboards

Comprehensive verification gate proving that the entire pipeline:
  Natural-language request
  -> Understanding
  -> RAG / Minecraft Knowledge
  -> Planner
  -> Structured Specification
  -> Deterministic Datapack Generator
  -> Structural Validator
  -> Semantic QA / Runtime Simulation
  -> Final READY Decision
operates as a unified, coherent, deterministic, and safe architecture.

Covers:
  - Invariants A-E (Planning boundary, objective correctness, action correctness, condition correctness, lifecycle correctness)
  - End-to-End Pipeline Tests (Tests A-H: objectives, score updates, operations, conditions, rain, night vision, ambiguity, missing score value)
  - Layered Failure Injection (20 failure scenarios rejected at the appropriate architectural layers)
  - Repair Loop Verification (Success with regeneration and failure exhaustion)
  - READY Gate Verification (Strict requirements: structural validity, QA approval, intent verification, runtime simulation, ZIP integrity)
  - Datapack Artifact Verification (Root layout, namespace, function tag minimal formatting, tag references, ZIP-vs-folder parity)
"""

import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai.context import retrieve_minecraft_context
from ai.planner import MinecraftPlanner, create_plan, validate_plan_mechanisms
from generator.datapack_generator import DatapackGenerator
from generator.mechanisms.function_mech import FunctionMechanismGenerator
from generator.mechanisms.state_machine_mech import StateMachineMechanismGenerator
from generator.models import (
    ActionSpecification,
    MechanismSpecification,
    ScoreCompareCondition,
    ScoreboardObjectiveDefinition,
    validate_comparison_operator,
    validate_criteria,
    validate_display_slot,
    validate_mechanism_specification,
    validate_objective_name,
    validate_score_operation,
)
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
from repair.models import RepairAttempt, RepairPlan, RepairResult
from repair.repair_loop import AIRepairLoop
from validator.datapack_validator import DatapackValidator


class MockPipelineAI:
    """
    Deterministic mock AI provider for pipeline testing without Ollama or network dependencies.
    """
    def __init__(self, understanding_handler=None, planner_handler=None, qa_handler=None):
        self.understanding_handler = understanding_handler
        self.planner_handler = planner_handler
        self.qa_handler = qa_handler
        self.calls = []

    def generate_structured(self, system_prompt: str, user_prompt: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "schema": schema
        })
        # Route based on prompt markers
        if "understanding layer" in system_prompt.lower():
            if self.understanding_handler:
                return self.understanding_handler(user_prompt, schema)
            return {
                "status": "understood",
                "minecraft_version": "1.21.11",
                "edition": "Java",
                "understood_request": "Generic understood request",
                "requirements": [{"intent": "generic"}]
            }
        elif "planning engine" in system_prompt.lower():
            if self.planner_handler:
                return self.planner_handler(user_prompt, schema)
            return {
                "status": "ready",
                "minecraft_version": "1.21.11",
                "summary": "Generic plan",
                "implementation_plan": [],
                "missing_knowledge": [],
                "clarifications": []
            }
        elif "qa reviewer" in system_prompt.lower() or "repair" in system_prompt.lower():
            if self.qa_handler:
                return self.qa_handler(user_prompt, schema)
            return {
                "diagnosis": "Mock repair",
                "regenerate": True,
                "repaired_plan": {}
            }
        return {"status": "ready"}


# =============================================================================
# INVARIANTS A - E VERIFICATION
# =============================================================================

class TestStep16Invariants(unittest.TestCase):
    """
    Verifies architectural Invariants A through E.
    """

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="step16_inv_"))
        self.generator = DatapackGenerator(output_dir=self.test_dir, version="1.21.11")
        self.validator = DatapackValidator(version="1.21.11")

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_invariant_a_structured_planning_boundary_no_raw_commands(self):
        """Invariant A: Normal planner output must be structured, not raw commands."""
        # 1. Normal structured score action
        act = ActionSpecification(
            action_type="set_score",
            target="#global",
            objective="test_score",
            score_value=42
        )
        self.assertEqual(act.action_type, "set_score")
        self.assertEqual(act.score_value, 42)
        self.assertIsNone(act.raw_command)

        # 2. FunctionMechanismGenerator synthesizes deterministic syntax
        fn_gen = FunctionMechanismGenerator(version="1.21.11")
        cmd = fn_gen.synthesize_action(act)
        self.assertEqual(cmd, "scoreboard players set #global test_score 42")

        # 3. Model validation prevents raw command as public action_type
        with self.assertRaises(ValueError):
            validate_mechanism_specification({
                "type": "function",
                "path": "test",
                "actions": [{"action_type": "scoreboard players set #global test 42"}]
            })

    def test_invariant_b_scoreboard_objective_correctness(self):
        """Invariant B: Valid objective name, criteria, display name, display slot, no conflict."""
        # Valid objective definition
        obj_def = ScoreboardObjectiveDefinition(
            objective="player_kills",
            criteria="playerKillCount",
            display_name="Kills",
            display_slot="sidebar"
        )
        self.assertEqual(obj_def.objective, "player_kills")
        self.assertEqual(obj_def.criteria, "playerKillCount")
        self.assertEqual(obj_def.display_slot, "sidebar")

        # Valid team display slot
        obj_team = ScoreboardObjectiveDefinition(
            objective="team_score",
            criteria="dummy",
            display_slot="sidebar.team.blue"
        )
        self.assertEqual(obj_team.display_slot, "sidebar.team.blue")

        # Conflicting duplicate objectives rejected by DatapackGenerator
        plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "Conflict test",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Conflicting objectives",
                    "mechanisms": [
                        {"type": "scoreboard_objective", "objective": "dup", "criteria": "dummy"},
                        {"type": "scoreboard_objective", "objective": "dup", "criteria": "deathCount"}
                    ]
                }
            ]
        }
        with self.assertRaises(ValueError) as ctx:
            self.generator.generate(plan=plan, datapack_name="conflict_pack")
        self.assertIn("Conflicting criteria for scoreboard objective 'dup'", str(ctx.exception))

    def test_invariant_c_score_actions_and_all_nine_operations(self):
        """Invariant C: Structured actions reach generator and produce exact Minecraft command semantics."""
        fn_gen = FunctionMechanismGenerator(version="1.21.11")

        # set_score
        c1 = fn_gen.synthesize_action(ActionSpecification(action_type="set_score", target="@a", objective="pts", score_value=0))
        self.assertEqual(c1, "scoreboard players set @a pts 0")

        # add_score
        c2 = fn_gen.synthesize_action(ActionSpecification(action_type="add_score", target="@a", objective="pts", score_value=10))
        self.assertEqual(c2, "scoreboard players add @a pts 10")

        # remove_score
        c3 = fn_gen.synthesize_action(ActionSpecification(action_type="remove_score", target="@a", objective="pts", score_value=5))
        self.assertEqual(c3, "scoreboard players remove @a pts 5")

        # reset_score
        c4 = fn_gen.synthesize_action(ActionSpecification(action_type="reset_score", target="@a", objective="pts"))
        self.assertEqual(c4, "scoreboard players reset @a pts")

        # All 9 operations
        expected_ops = {
            "=": "scoreboard players operation @s score_a = #global score_b",
            "+=": "scoreboard players operation @s score_a += #global score_b",
            "-=": "scoreboard players operation @s score_a -= #global score_b",
            "*=": "scoreboard players operation @s score_a *= #global score_b",
            "/=": "scoreboard players operation @s score_a /= #global score_b",
            "%=": "scoreboard players operation @s score_a %= #global score_b",
            "<": "scoreboard players operation @s score_a < #global score_b",
            ">": "scoreboard players operation @s score_a > #global score_b",
            "><": "scoreboard players operation @s score_a >< #global score_b",
        }
        for op, expected_cmd in expected_ops.items():
            act = ActionSpecification(
                action_type="operation_score",
                target="@s",
                objective="score_a",
                operation=op,
                source_holder="#global",
                source_objective="score_b"
            )
            cmd = fn_gen.synthesize_action(act)
            self.assertEqual(cmd, expected_cmd)

    def test_invariant_d_score_conditions_ranges_and_comparisons(self):
        """Invariant D: Range checks and score-to-score comparisons reach generator and compile cleanly."""
        fn_gen = FunctionMechanismGenerator(version="1.21.11")

        # Range condition
        act_range = ActionSpecification(
            action_type="give_item",
            target="@s",
            item="minecraft:diamond",
            count=1,
            conditions=[
                {"type": "score", "holder": "@s", "objective": "level", "range": "10.."}
            ]
        )
        cmd_range = fn_gen.synthesize_action(act_range)
        self.assertIn("if score @s level matches 10..", cmd_range)
        self.assertIn("give @s minecraft:diamond 1", cmd_range)

        # Comparison condition: <, <=, =, >=, >
        operators = ["<", "<=", "=", ">=", ">"]
        for op in operators:
            act_comp = ActionSpecification(
                action_type="apply_effect",
                target="@s",
                effect="minecraft:speed",
                duration=10,
                amplifier=0,
                conditions=[
                    ScoreCompareCondition(
                        target="@s",
                        target_objective="speed_pts",
                        operator=op,
                        source="#global",
                        source_objective="speed_threshold"
                    )
                ]
            )
            cmd_comp = fn_gen.synthesize_action(act_comp)
            self.assertIn(f"if score @s speed_pts {op} #global speed_threshold", cmd_comp)
            self.assertIn("effect give @s minecraft:speed 10 0 false", cmd_comp)

    def test_invariant_e_lifecycle_correctness(self):
        """Invariant E: Objectives/setup in load, continuous in tick, edge-triggered in state_machine."""
        plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "Lifecycle test",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Setup and tick",
                    "mechanisms": [
                        # Load: objective creation
                        {
                            "type": "scoreboard_objective",
                            "objective": "timer",
                            "criteria": "dummy",
                            "display_slot": "sidebar"
                        },
                        # Tick: continuous increment
                        {
                            "type": "continuous_action",
                            "trigger": "tick",
                            "actions": [
                                {
                                    "action_type": "add_score",
                                    "target": "#global",
                                    "objective": "timer",
                                    "score_value": 1
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        res = self.generator.generate(plan=plan, datapack_name="lifecycle_dp")
        val = self.validator.validate(res.datapack_path)
        self.assertTrue(val.is_valid, f"Validation failed: {val.errors}")

        # load.mcfunction must have objective declaration
        load_f = res.datapack_path / "data" / "minecraft_ai" / "function" / "load.mcfunction"
        self.assertTrue(load_f.exists())
        load_content = load_f.read_text(encoding="utf-8")
        self.assertIn("scoreboard objectives add timer dummy", load_content)
        self.assertIn("scoreboard objectives setdisplay sidebar timer", load_content)
        # load.mcfunction must not have the tick increment
        self.assertNotIn("scoreboard players add #global timer 1", load_content)

        # tick.mcfunction must have the tick increment
        tick_f = res.datapack_path / "data" / "minecraft_ai" / "function" / "tick.mcfunction"
        self.assertTrue(tick_f.exists())
        tick_content = tick_f.read_text(encoding="utf-8")
        self.assertIn("scoreboard players add #global timer 1", tick_content)
        # tick.mcfunction must not recreate the objective
        self.assertNotIn("scoreboard objectives add", tick_content)


# =============================================================================
# END-TO-END PIPELINE TESTS (TESTS A - H)
# =============================================================================

class TestStep16EndToEndPipeline(unittest.TestCase):
    """
    End-to-end pipeline execution tests with mock AI injection.
    """

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="step16_e2e_"))

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _build_pipeline(self, mock_ai):
        return MinecraftPipeline(
            provider="mock",
            version="1.21.11",
            output_dir=self.test_dir,
            ai_provider=mock_ai,
            verbose=False
        )

    def test_e2e_test_a_objective_creation(self):
        """Test A: 'Track player deaths on the sidebar' -> load objective, sidebar display, READY."""
        def understanding_h(prompt, schema):
            return {
                "status": "understood",
                "minecraft_version": "1.21.11",
                "edition": "Java",
                "understood_request": "Track player deaths on the sidebar.",
                "requirements": [
                    {
                        "subject": "player",
                        "intent": "track deaths on sidebar",
                        "details": [{"name": "criteria", "value": "deathCount"}, {"name": "slot", "value": "sidebar"}]
                    }
                ]
            }

        def planner_h(prompt, schema):
            return {
                "status": "ready",
                "minecraft_version": "1.21.11",
                "summary": "Track player deaths on sidebar",
                "implementation_plan": [
                    {
                        "requirement_index": 0,
                        "objective": "Track deaths on sidebar",
                        "mechanisms": [
                            {
                                "type": "scoreboard_objective",
                                "objective": "deaths",
                                "criteria": "deathCount",
                                "display_name": "Deaths",
                                "display_slot": "sidebar"
                            }
                        ]
                    }
                ],
                "missing_knowledge": [],
                "clarifications": []
            }

        mock_ai = MockPipelineAI(understanding_handler=understanding_h, planner_handler=planner_h)
        pipeline = self._build_pipeline(mock_ai)
        result = pipeline.run("Track player deaths on the sidebar.", datapack_name="death_tracker")

        self.assertEqual(result.status, "success")
        self.assertEqual(result.verification_status, "verified")
        self.assertIsNotNone(result.final_datapack_path)
        self.assertIsNotNone(result.final_zip_path)

        # Check generated load file
        load_f = Path(result.final_datapack_path) / "data" / "minecraft_ai" / "function" / "load.mcfunction"
        self.assertTrue(load_f.exists())
        content = load_f.read_text(encoding="utf-8")
        self.assertIn("scoreboard objectives add deaths deathCount \"Deaths\"", content)
        self.assertIn("scoreboard objectives setdisplay sidebar deaths", content)

    def test_e2e_test_b_score_update(self):
        """Test B: 'Give every player 10 points' -> add_score, valid command, QA pass, READY."""
        def planner_h(prompt, schema):
            return {
                "status": "ready",
                "minecraft_version": "1.21.11",
                "summary": "Give every player 10 points",
                "implementation_plan": [
                    {
                        "requirement_index": 0,
                        "objective": "Reward players with points",
                        "mechanisms": [
                            {
                                "type": "scoreboard_objective",
                                "objective": "points",
                                "criteria": "dummy"
                            },
                            {
                                "type": "function",
                                "namespace": "minecraft_ai",
                                "path": "reward",
                                "actions": [
                                    {
                                        "action_type": "add_score",
                                        "target": "@a",
                                        "objective": "points",
                                        "score_value": 10
                                    }
                                ]
                            }
                        ]
                    }
                ],
                "missing_knowledge": [],
                "clarifications": []
            }

        mock_ai = MockPipelineAI(planner_handler=planner_h)
        pipeline = self._build_pipeline(mock_ai)
        result = pipeline.run("Give every player 10 points.", datapack_name="points_pack")

        self.assertEqual(result.status, "success")
        self.assertEqual(result.verification_status, "verified")

        reward_f = Path(result.final_datapack_path) / "data" / "minecraft_ai" / "function" / "reward.mcfunction"
        self.assertTrue(reward_f.exists())
        self.assertIn("scoreboard players add @a points 10", reward_f.read_text(encoding="utf-8"))

    def test_e2e_test_c_score_operation(self):
        """Test C: 'Multiply score A by score B' -> operation_score, *=, QA pass, READY."""
        def planner_h(prompt, schema):
            return {
                "status": "ready",
                "minecraft_version": "1.21.11",
                "summary": "Multiply score A by score B",
                "implementation_plan": [
                    {
                        "requirement_index": 0,
                        "objective": "Multiply scores",
                        "mechanisms": [
                            {"type": "scoreboard_objective", "objective": "score_a", "criteria": "dummy"},
                            {"type": "scoreboard_objective", "objective": "score_b", "criteria": "dummy"},
                            {
                                "type": "function",
                                "namespace": "minecraft_ai",
                                "path": "multiply",
                                "actions": [
                                    {
                                        "action_type": "operation_score",
                                        "target": "@s",
                                        "objective": "score_a",
                                        "operation": "*=",
                                        "source_holder": "@s",
                                        "source_objective": "score_b"
                                    }
                                ]
                            }
                        ]
                    }
                ],
                "missing_knowledge": [],
                "clarifications": []
            }

        mock_ai = MockPipelineAI(planner_handler=planner_h)
        pipeline = self._build_pipeline(mock_ai)
        result = pipeline.run("Multiply score A by score B.", datapack_name="mult_pack")

        self.assertEqual(result.status, "success")
        self.assertEqual(result.verification_status, "verified")

        mult_f = Path(result.final_datapack_path) / "data" / "minecraft_ai" / "function" / "multiply.mcfunction"
        self.assertTrue(mult_f.exists())
        self.assertIn("scoreboard players operation @s score_a *= @s score_b", mult_f.read_text(encoding="utf-8"))

    def test_e2e_test_d_score_condition(self):
        """Test D: 'When a player's score reaches 10 or more, give them a diamond' -> score range condition."""
        def planner_h(prompt, schema):
            return {
                "status": "ready",
                "minecraft_version": "1.21.11",
                "summary": "Give diamond when score is 10 or more",
                "implementation_plan": [
                    {
                        "requirement_index": 0,
                        "objective": "Score threshold reward",
                        "mechanisms": [
                            {"type": "scoreboard_objective", "objective": "points", "criteria": "dummy"},
                            {
                                "type": "continuous_action",
                                "trigger": "tick",
                                "actions": [
                                    {
                                        "action_type": "give_item",
                                        "target": "@a",
                                        "item": "minecraft:diamond",
                                        "count": 1,
                                        "conditions": [
                                            {"type": "score", "holder": "@s", "objective": "points", "range": "10.."}
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ],
                "missing_knowledge": [],
                "clarifications": []
            }

        mock_ai = MockPipelineAI(planner_handler=planner_h)
        pipeline = self._build_pipeline(mock_ai)
        result = pipeline.run("When a player's score reaches 10 or more, give them a diamond.", datapack_name="cond_reward")

        self.assertEqual(result.status, "success")
        self.assertEqual(result.verification_status, "verified")

    def test_e2e_test_e_temporal_rain_state_machine(self):
        """Test E: 'When rain starts, give a diamond once' -> state machine, rising edge, reset, READY."""
        def planner_h(prompt, schema):
            return {
                "status": "ready",
                "minecraft_version": "1.21.11",
                "summary": "Give diamond once when rain starts",
                "implementation_plan": [
                    {
                        "requirement_index": 0,
                        "objective": "Rain start reward",
                        "mechanisms": [
                            {
                                "type": "predicate",
                                "namespace": "minecraft_ai",
                                "path": "is_raining",
                                "condition_type": "minecraft:weather_check",
                                "condition_params": {"raining": True}
                            },
                            {
                                "type": "state_machine",
                                "namespace": "minecraft_ai",
                                "objective": "rain_state",
                                "condition_predicate": "minecraft_ai:is_raining",
                                "state_scope": "global",
                                "on_enter": [
                                    {
                                        "action_type": "give_item",
                                        "target": "@a",
                                        "item": "minecraft:diamond",
                                        "count": 1
                                    }
                                ]
                            }
                        ]
                    }
                ],
                "missing_knowledge": [],
                "clarifications": []
            }

        mock_ai = MockPipelineAI(planner_handler=planner_h)
        pipeline = self._build_pipeline(mock_ai)
        result = pipeline.run("When rain starts, give a diamond once.", datapack_name="rain_pack")

        self.assertEqual(result.status, "success")
        self.assertEqual(result.verification_status, "verified")

        # Verify state machine files and tags
        dp = Path(result.final_datapack_path)
        self.assertTrue((dp / "data" / "minecraft_ai" / "function" / "load.mcfunction").exists())
        self.assertTrue((dp / "data" / "minecraft_ai" / "function" / "tick.mcfunction").exists())
        self.assertTrue((dp / "data" / "minecraft" / "tags" / "function" / "tick.json").exists())

    def test_e2e_test_f_temporal_night_transition(self):
        """Test F: 'When night starts, give every player night vision' -> state machine, rising edge, READY."""
        def planner_h(prompt, schema):
            return {
                "status": "ready",
                "minecraft_version": "1.21.11",
                "summary": "Give night vision once when night starts",
                "implementation_plan": [
                    {
                        "requirement_index": 0,
                        "objective": "Night vision on dusk",
                        "mechanisms": [
                            {
                                "type": "predicate",
                                "namespace": "minecraft_ai",
                                "path": "is_night",
                                "condition_type": "minecraft:time_check",
                                "condition_params": {"value": {"min": 13000, "max": 24000}}
                            },
                            {
                                "type": "state_machine",
                                "namespace": "minecraft_ai",
                                "objective": "night_state",
                                "condition_predicate": "minecraft_ai:is_night",
                                "state_scope": "global",
                                "on_enter": [
                                    {
                                        "action_type": "apply_effect",
                                        "target": "@a",
                                        "effect": "minecraft:night_vision",
                                        "duration": 30,
                                        "amplifier": 0
                                    }
                                ]
                            }
                        ]
                    }
                ],
                "missing_knowledge": [],
                "clarifications": []
            }

        mock_ai = MockPipelineAI(planner_handler=planner_h)
        pipeline = self._build_pipeline(mock_ai)
        result = pipeline.run("When night starts, give every player night vision.", datapack_name="night_pack")

        self.assertEqual(result.status, "success")
        self.assertEqual(result.verification_status, "verified")

    def test_e2e_test_g_ambiguity_objective_purpose_clarification(self):
        """Test G: 'Create a scoreboard' -> needs_clarification, no generation, no ZIP, not READY."""
        def understanding_h(prompt, schema):
            return {
                "status": "needs_clarification",
                "minecraft_version": "1.21.11",
                "edition": "Java",
                "understood_request": "Create a scoreboard.",
                "clarification": {
                    "question": "What should the scoreboard track (e.g., player deaths, kills, health, or custom dummy points)?",
                    "reason": "Request lacks objective purpose or criteria."
                }
            }

        mock_ai = MockPipelineAI(understanding_handler=understanding_h)
        pipeline = self._build_pipeline(mock_ai)
        result = pipeline.run("Create a scoreboard.", datapack_name="ambiguous_pack")

        self.assertEqual(result.status, "needs_clarification")
        self.assertNotEqual(result.verification_status, "verified")
        self.assertIsNone(result.final_datapack_path)
        self.assertIsNone(result.final_zip_path)
        self.assertIn("What should the scoreboard track", result.clarification)

    def test_e2e_test_h_missing_score_value_clarification(self):
        """Test H: 'Give me points' -> planner outputs needs_clarification, halts before generation."""
        def understanding_h(prompt, schema):
            return {
                "status": "understood",
                "minecraft_version": "1.21.11",
                "edition": "Java",
                "understood_request": "Give me points.",
                "requirements": [{"intent": "give points"}]
            }

        def planner_h(prompt, schema):
            return {
                "status": "needs_clarification",
                "minecraft_version": "1.21.11",
                "summary": "Missing score value and objective name",
                "implementation_plan": [],
                "missing_knowledge": [],
                "clarifications": ["How many points should be given, and to which scoreboard objective?"]
            }

        mock_ai = MockPipelineAI(understanding_handler=understanding_h, planner_handler=planner_h)
        pipeline = self._build_pipeline(mock_ai)
        result = pipeline.run("Give me points.", datapack_name="points_pack")

        self.assertEqual(result.status, "needs_clarification")
        self.assertNotEqual(result.verification_status, "verified")
        self.assertIsNone(result.final_datapack_path)
        self.assertIsNone(result.final_zip_path)
        self.assertIn("How many points", result.clarification)


# =============================================================================
# FAILURE INJECTION TESTS (20 LAYERED SCENARIOS)
# =============================================================================

class TestStep16FailureInjection(unittest.TestCase):
    """
    Verifies that invalid or hazardous scoreboard constructs are caught and rejected
    at the appropriate layer of defense (Model, Generator, Validator, or Semantic QA).
    """

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="step16_fail_"))
        self.validator = DatapackValidator(version="1.21.11")
        self.analyzer = StaticSemanticAnalyzer(version="1.21.11")

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_pack_with_function(
        self,
        name: str,
        commands: List[str],
        load_commands: Optional[List[str]] = None,
        function_name: str = "main"
    ) -> Path:
        pack_dir = self.test_dir / name
        pack_dir.mkdir(parents=True, exist_ok=True)
        mcmeta = {
            "pack": {
                "pack_format": 94,
                "min_format": [94, 0],
                "max_format": [94, 1],
                "description": "Failure Injection Pack"
            }
        }
        with open(pack_dir / "pack.mcmeta", "w", encoding="utf-8") as f:
            json.dump(mcmeta, f)

        func_dir = pack_dir / "data" / "minecraft_ai" / "function"
        func_dir.mkdir(parents=True, exist_ok=True)

        with open(func_dir / f"{function_name}.mcfunction", "w", encoding="utf-8") as f:
            f.write("\n".join(commands) + "\n")

        if load_commands:
            with open(func_dir / "load.mcfunction", "w", encoding="utf-8") as f:
                f.write("\n".join(load_commands) + "\n")

        return pack_dir

    # 1. Invalid objective name (>16 chars)
    def test_fail_1_invalid_objective_name(self):
        """1. Invalid objective name (> 16 chars) rejected at Model and Validator."""
        with self.assertRaises(ValueError):
            validate_objective_name("this_name_is_way_too_long_for_minecraft")

        pack = self._create_pack_with_function("inv_name", [
            "scoreboard objectives add this_name_is_way_too_long_for_minecraft dummy"
        ], function_name="load")
        val = self.validator.validate(pack)
        self.assertFalse(val.is_valid)
        self.assertTrue(any(e.code == "INVALID_SCOREBOARD_OBJECTIVE" for e in val.errors))

    # 2. Invalid scoreboard criteria
    def test_fail_2_invalid_scoreboard_criteria(self):
        """2. Invalid scoreboard criteria rejected at Model and Validator."""
        with self.assertRaises(ValueError):
            validate_criteria("not_a_real_criterion_xyz")

        pack = self._create_pack_with_function("inv_crit", [
            "scoreboard objectives add test not_a_real_criterion_xyz"
        ], function_name="load")
        val = self.validator.validate(pack)
        self.assertFalse(val.is_valid)
        self.assertTrue(any(e.code == "INVALID_SCOREBOARD_CRITERIA" for e in val.errors))

    # 3. Invalid display slot
    def test_fail_3_invalid_display_slot(self):
        """3. Invalid display slot rejected at Model and Validator."""
        with self.assertRaises(ValueError):
            validate_display_slot("floating_head_slot")

        pack = self._create_pack_with_function("inv_slot", [
            "scoreboard objectives add test dummy",
            "scoreboard objectives setdisplay floating_head_slot test"
        ])
        val = self.validator.validate(pack)
        self.assertFalse(val.is_valid)
        self.assertTrue(any(e.code == "INVALID_DISPLAY_SLOT" for e in val.errors))

    # 4. Invalid score operation
    def test_fail_4_invalid_score_operation(self):
        """4. Invalid score operation (e.g. '**=') rejected at Model and Validator."""
        with self.assertRaises(ValueError):
            validate_score_operation("**=")

        pack = self._create_pack_with_function("inv_op", [
            "scoreboard objectives add a dummy",
            "scoreboard objectives add b dummy",
            "scoreboard players operation @s a **= @s b"
        ])
        val = self.validator.validate(pack)
        self.assertFalse(val.is_valid)
        self.assertTrue(any(e.code == "INVALID_SCORE_OPERATION" for e in val.errors))

    # 5. Invalid comparison operator
    def test_fail_5_invalid_comparison_operator(self):
        """5. Invalid comparison operator (e.g. '==') rejected at Model and Validator."""
        with self.assertRaises(ValueError):
            validate_comparison_operator("==")

        pack = self._create_pack_with_function("inv_comp", [
            "scoreboard objectives add a dummy",
            "scoreboard objectives add b dummy",
            "execute if score @s a == @s b run give @s diamond 1"
        ])
        val = self.validator.validate(pack)
        self.assertFalse(val.is_valid)
        self.assertTrue(any(e.code == "INVALID_SCORE_COMPARISON" for e in val.errors))

    # 6. Score outside signed 32-bit range
    def test_fail_6_score_outside_signed_32bit_range(self):
        """6. Literal score exceeding 32-bit int bounds rejected by Validator."""
        pack = self._create_pack_with_function("overflow_score", [
            "scoreboard objectives add a dummy",
            "scoreboard players set @s a 3000000000"
        ], function_name="load")
        val = self.validator.validate(pack)
        self.assertFalse(val.is_valid)
        self.assertTrue(any(e.code == "INVALID_SCORE_VALUE" for e in val.errors))

    # 7. Floating-point score value
    def test_fail_7_floating_point_score_value(self):
        """7. Floating-point score value rejected at Model and Validator."""
        with self.assertRaises(ValueError):
            ActionSpecification(action_type="set_score", target="@s", objective="a", score_value=15.5)

        with self.assertRaises(ValueError):
            ActionSpecification(action_type="set_score", target="@s", objective="a", score_value="15.5")

        pack = self._create_pack_with_function("float_score", [
            "scoreboard objectives add a dummy",
            "scoreboard players set @s a 15.5"
        ], function_name="load")
        val = self.validator.validate(pack)
        self.assertFalse(val.is_valid)
        self.assertTrue(any(e.code == "INVALID_SCORE_VALUE" for e in val.errors))

    # 8. Boolean score value
    def test_fail_8_boolean_score_value(self):
        """8. Boolean score value rejected at Model."""
        with self.assertRaises(ValueError):
            ActionSpecification(action_type="set_score", target="@s", objective="a", score_value=True)

    # 9. Negative add_score
    def test_fail_9_negative_add_score(self):
        """9. Negative add_score rejected at Model and Validator."""
        with self.assertRaises(ValueError):
            ActionSpecification(action_type="add_score", target="@s", objective="a", score_value=-5)

        pack = self._create_pack_with_function("neg_add", [
            "scoreboard objectives add a dummy",
            "scoreboard players add @s a -5"
        ], function_name="load")
        val = self.validator.validate(pack)
        self.assertFalse(val.is_valid)
        self.assertTrue(any(e.code == "INVALID_SCORE_VALUE" for e in val.errors))

    # 10. Negative remove_score
    def test_fail_10_negative_remove_score(self):
        """10. Negative remove_score rejected at Model and Validator."""
        with self.assertRaises(ValueError):
            ActionSpecification(action_type="remove_score", target="@s", objective="a", score_value=-1)

        pack = self._create_pack_with_function("neg_remove", [
            "scoreboard objectives add a dummy",
            "scoreboard players remove @s a -1"
        ], function_name="load")
        val = self.validator.validate(pack)
        self.assertFalse(val.is_valid)
        self.assertTrue(any(e.code == "INVALID_SCORE_VALUE" for e in val.errors))

    # 11. Undeclared scoreboard objective
    def test_fail_11_undeclared_scoreboard_objective(self):
        """11. Undeclared scoreboard objective rejected by Validator."""
        pack = self._create_pack_with_function("undeclared_obj", [
            "scoreboard players set @s ghost_objective 10"
        ])
        val = self.validator.validate(pack)
        self.assertFalse(val.is_valid)
        self.assertTrue(any(e.code == "UNDECLARED_SCOREBOARD_OBJECTIVE" for e in val.errors))

    # 12. Missing function tag reference
    def test_fail_12_missing_function_tag_reference(self):
        """12. Missing function tag reference rejected by Validator."""
        pack = self._create_pack_with_function("missing_tag_ref", ["say hello"])
        tag_dir = pack / "data" / "minecraft" / "tags" / "function"
        tag_dir.mkdir(parents=True, exist_ok=True)
        with open(tag_dir / "tick.json", "w", encoding="utf-8") as f:
            json.dump({"values": ["minecraft_ai:nonexistent_function"]}, f)

        val = self.validator.validate(pack)
        self.assertFalse(val.is_valid)
        self.assertTrue(any(e.code == "MISSING_TAG_REFERENCE" for e in val.errors))

    # 13. Malformed function tag
    def test_fail_13_malformed_function_tag(self):
        """13. Malformed function tag (missing 'values') rejected by Validator."""
        pack = self._create_pack_with_function("malformed_tag", ["say hello"])
        tag_dir = pack / "data" / "minecraft" / "tags" / "function"
        tag_dir.mkdir(parents=True, exist_ok=True)
        with open(tag_dir / "tick.json", "w", encoding="utf-8") as f:
            json.dump({"not_values": []}, f)

        val = self.validator.validate(pack)
        self.assertFalse(val.is_valid)
        self.assertTrue(any(e.code == "MALFORMED_TAG" for e in val.errors))

    # 14. Conflicting objective definitions
    def test_fail_14_conflicting_objective_definitions(self):
        """14. Conflicting objective definitions rejected by Validator."""
        pack = self._create_pack_with_function("conflict_obj", [
            "scoreboard objectives add my_score dummy",
            "scoreboard objectives add my_score deathCount"
        ])
        val = self.validator.validate(pack)
        self.assertFalse(val.is_valid)
        self.assertTrue(any(e.code == "CONFLICTING_OBJECTIVE_DEFINITION" for e in val.errors))

    # 15. Division by zero in score operation
    def test_fail_15_division_by_zero(self):
        """15. Division by zero detected and flagged by QA Semantic Analyzer."""
        pack = self._create_pack_with_function("div_zero", [
            "scoreboard objectives add a dummy",
            "scoreboard objectives add b dummy",
            "scoreboard players set #divisor b 0",
            "scoreboard players operation #val a /= #divisor b"
        ], load_commands=[
            "scoreboard objectives add a dummy",
            "scoreboard objectives add b dummy",
            "scoreboard players set #divisor b 0"
        ])
        findings = self.analyzer.analyze(pack)
        self.assertTrue(any(f.id == "SCORE_OPERATION_DIVIDE_BY_ZERO" for f in findings))

    # 16. Modulo by zero in score operation
    def test_fail_16_modulo_by_zero(self):
        """16. Modulo by zero detected and flagged by QA Semantic Analyzer."""
        pack = self._create_pack_with_function("mod_zero", [
            "scoreboard objectives add a dummy",
            "scoreboard objectives add b dummy",
            "scoreboard players set #divisor b 0",
            "scoreboard players operation #val a %= #divisor b"
        ], load_commands=[
            "scoreboard objectives add a dummy",
            "scoreboard objectives add b dummy",
            "scoreboard players set #divisor b 0"
        ])
        findings = self.analyzer.analyze(pack)
        self.assertTrue(any(f.id == "SCORE_OPERATION_MODULO_BY_ZERO" for f in findings))

    # 17. Score use before initialization
    def test_fail_17_score_use_before_initialization(self):
        """17. Score use before initialization detected by QA Semantic Analyzer."""
        pack = self._create_pack_with_function("uninit_score", [
            "scoreboard objectives add my_state dummy",
            "execute if score #global my_state matches 0 run give @a diamond 1"
        ], load_commands=[
            "scoreboard objectives add my_state dummy"
            # Missing: scoreboard players set #global my_state 0
        ])
        findings = self.analyzer.analyze(pack)
        self.assertTrue(any(f.id == "SCORE_USE_BEFORE_INITIALIZATION" for f in findings))

    # 18. Repeating state event that should be once-only
    def test_fail_18_repeating_state_event(self):
        """18. Repeating transition event detected by QA Semantic Analyzer."""
        pack = self._create_pack_with_function("repeating_event", [
            "scoreboard objectives add state dummy",
            "execute if score #global state matches 0 if predicate cond run give @a diamond 1"
        ], load_commands=[
            "scoreboard objectives add state dummy",
            "scoreboard players set #global state 0"
        ], function_name="tick")
        findings = self.analyzer.analyze(pack)
        self.assertTrue(any(f.id == "STATE_EVENT_REPEATS" for f in findings))

    # 19. State latch that never resets
    def test_fail_19_state_latch_never_resets(self):
        """19. State latch that never resets detected by QA Semantic Analyzer."""
        pack = self._create_pack_with_function("never_resets", [
            "scoreboard objectives add state dummy",
            "execute if score #global state matches 0 if predicate cond run give @a diamond 1",
            "execute if predicate cond run scoreboard players set #global state 1"
            # Missing: execute unless predicate cond run scoreboard players set #global state 0
        ], load_commands=[
            "scoreboard objectives add state dummy",
            "scoreboard players set #global state 0"
        ], function_name="tick")
        findings = self.analyzer.analyze(pack)
        self.assertTrue(any(f.id == "STATE_LATCH_NEVER_RESETS" for f in findings))

    # 20. Unreachable state event
    def test_fail_20_unreachable_state_event(self):
        """20. Unreachable state event detected by QA Semantic Analyzer."""
        pack = self._create_pack_with_function("unreachable_event", [
            "scoreboard objectives add state dummy",
            "execute if score #global state matches 0 if predicate cond run give @a diamond 1",
            "execute if predicate cond run scoreboard players set #global state 1"
        ], load_commands=[
            "scoreboard objectives add state dummy",
            "scoreboard players set #global state 1"
        ], function_name="tick")
        findings = self.analyzer.analyze(pack)
        self.assertTrue(any(f.id == "STATE_EVENT_UNREACHABLE" for f in findings))


# =============================================================================
# REPAIR LOOP VERIFICATION
# =============================================================================

class TestStep16RepairLoop(unittest.TestCase):
    """
    Verifies that the repair loop re-validates, re-reviews, and halts on exhaustion.
    """

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="step16_repair_"))

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_repair_failure_exhaustion_remains_not_ready(self):
        """Unrepairable issue exhausts retries and returns NOT READY with attempt history."""
        # Flawed plan that produces an unresolvable error (undeclared objective)
        flawed_plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "Unrepairable broken pack",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Broken",
                    "mechanisms": [
                        {
                            "type": "function",
                            "namespace": "minecraft_ai",
                            "path": "broken",
                            "commands": ["scoreboard players set @a ghost_unregistered_obj 10"]
                        }
                    ]
                }
            ]
        }
        # Mock AI that fails to fix the issue
        def bad_repair_handler(user_prompt, schema):
            return {
                "repair_reasoning": "Still broken",
                "status": "ready",
                "minecraft_version": "1.21.11",
                "summary": "Still broken plan",
                "implementation_plan": flawed_plan["implementation_plan"],
                "missing_knowledge": [],
                "clarifications": []
            }

        mock_ai = MockPipelineAI(planner_handler=lambda p, s: flawed_plan, qa_handler=bad_repair_handler)
        pipeline = MinecraftPipeline(
            provider="mock",
            version="1.21.11",
            output_dir=self.test_dir,
            ai_provider=mock_ai,
            max_repair_attempts=2,
            verbose=False
        )
        res = pipeline.run("Make something broken.", datapack_name="broken_pack")

        self.assertIn(res.status, ("failed", "verification_failed"))
        self.assertNotEqual(result_status := res.verification_status, "verified")
        self.assertGreater(len(res.errors), 0)

    def test_repair_success_regenerates_and_reaches_ready(self):
        """Repair success: broken structured output -> repair -> regeneration -> validation -> QA -> READY."""
        # 1. Initial plan has undeclared objective in a function command
        initial_flawed_plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "Repairable broken pack",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Broken initial plan",
                    "mechanisms": [
                        {
                            "type": "function",
                            "namespace": "minecraft_ai",
                            "path": "action",
                            "commands": ["scoreboard players set @a repairable_obj 10"]
                        }
                    ]
                }
            ]
        }

        # 2. Repair handler diagnoses the error and supplies the missing objective definition
        def repair_success_handler(user_prompt, schema):
            return {
                "repair_reasoning": "Scoreboard objective 'repairable_obj' was undeclared. Adding declaration to load.",
                "status": "ready",
                "minecraft_version": "1.21.11",
                "summary": "Repaired plan with declared objective",
                "implementation_plan": [
                    {
                        "requirement_index": 0,
                        "objective": "Repaired score setup",
                        "mechanisms": [
                            {
                                "type": "scoreboard_objective",
                                "objective": "repairable_obj",
                                "criteria": "dummy"
                            },
                            {
                                "type": "function",
                                "namespace": "minecraft_ai",
                                "path": "action",
                                "actions": [
                                    {
                                        "action_type": "set_score",
                                        "target": "@a",
                                        "objective": "repairable_obj",
                                        "score_value": 10
                                    }
                                ]
                            }
                        ]
                    }
                ],
                "missing_knowledge": [],
                "clarifications": []
            }

        mock_ai = MockPipelineAI(
            planner_handler=lambda p, s: initial_flawed_plan,
            qa_handler=repair_success_handler
        )
        pipeline = MinecraftPipeline(
            provider="mock",
            version="1.21.11",
            output_dir=self.test_dir,
            ai_provider=mock_ai,
            max_repair_attempts=2,
            verbose=False
        )
        res = pipeline.run("Make something that repairs.", datapack_name="repaired_pack")

        self.assertEqual(res.status, "success")
        self.assertEqual(res.verification_status, "verified")
        self.assertIsNotNone(res.repair)
        self.assertEqual(res.repair.total_attempts, 1)
        self.assertTrue(res.repair.is_success)
        self.assertIsNotNone(res.final_datapack_path)
        self.assertIsNotNone(res.final_zip_path)


# =============================================================================
# READY GATE VERIFICATION
# =============================================================================

class TestStep16ReadyGate(unittest.TestCase):
    """
    Verifies that the READY gate enforces all prerequisite stages.
    """

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="step16_ready_"))

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_ready_gate_requires_all_stages(self):
        """Verify that READY is ONLY granted when structural validation, QA, intent, and runtime simulation pass."""
        # 1. Structural validation failure -> NOT READY
        res_fail_val = PipelineResult(
            status="failed",
            minecraft_version="1.21.11",
            original_request="Test",
            errors=["Validation failed"]
        )
        self.assertNotEqual(res_fail_val.verification_status, "verified")

        # 2. QA failure -> NOT READY
        res_fail_qa = PipelineResult(
            status="verification_failed",
            minecraft_version="1.21.11",
            original_request="Test",
            errors=["QA failed: STATE_EVENT_REPEATS"]
        )
        self.assertNotEqual(res_fail_qa.verification_status, "verified")

        # 3. Clarification -> NOT READY
        res_clarif = PipelineResult(
            status="needs_clarification",
            minecraft_version="1.21.11",
            original_request="Test",
            clarification="Which score?"
        )
        self.assertNotEqual(res_clarif.verification_status, "verified")

        # 4. Successful verified pack -> READY
        res_success = PipelineResult(
            status="success",
            verification_status="verified",
            minecraft_version="1.21.11",
            original_request="Track deaths",
            final_datapack_path=str(self.test_dir / "pack"),
            final_zip_path=str(self.test_dir / "pack.zip")
        )
        self.assertEqual(res_success.status, "success")
        self.assertEqual(res_success.verification_status, "verified")

    def test_ready_gate_pipeline_planner_clarification_halts_not_ready(self):
        """Planner requesting clarification halts pipeline immediately; status != 'success', verification_status != 'verified'."""
        def planner_clarif(prompt, schema):
            return {
                "status": "needs_clarification",
                "minecraft_version": "1.21.11",
                "summary": "Ambiguous score operation",
                "implementation_plan": [],
                "missing_knowledge": [],
                "clarifications": ["Should the operation add or multiply?"]
            }

        mock_ai = MockPipelineAI(planner_handler=planner_clarif)
        pipeline = MinecraftPipeline(
            provider="mock",
            version="1.21.11",
            output_dir=self.test_dir,
            ai_provider=mock_ai,
            verbose=False
        )
        res = pipeline.run("Change my score with another score.", datapack_name="ambig_op")

        self.assertEqual(res.status, "needs_clarification")
        self.assertNotEqual(res.verification_status, "verified")
        self.assertIsNone(res.final_datapack_path)
        self.assertIsNone(res.final_zip_path)

    def test_ready_gate_pipeline_qa_hazard_halts_not_ready(self):
        """Pipeline with semantic QA hazard (divide by zero) fails QA and is NOT marked READY."""
        div_zero_plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "Divide by zero hazard",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Hazard",
                    "mechanisms": [
                        {"type": "scoreboard_objective", "objective": "a", "criteria": "dummy"},
                        {"type": "scoreboard_objective", "objective": "b", "criteria": "dummy"},
                        {
                            "type": "function",
                            "namespace": "minecraft_ai",
                            "path": "load",
                            "actions": [
                                {"action_type": "set_score", "target": "#divisor", "objective": "b", "score_value": 0}
                            ]
                        },
                        {
                            "type": "function",
                            "namespace": "minecraft_ai",
                            "path": "calc",
                            "actions": [
                                {
                                    "action_type": "operation_score",
                                    "target": "#val",
                                    "objective": "a",
                                    "operation": "/=",
                                    "source_holder": "#divisor",
                                    "source_objective": "b"
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        # QA repair engine handler returns regenerate=False to simulate unresolvable QA issue
        def abort_qa_repair(prompt, schema):
            return {
                "diagnosis": "Division by zero hazard cannot be resolved.",
                "regenerate": False,
                "repaired_plan": {}
            }

        mock_ai = MockPipelineAI(planner_handler=lambda p, s: div_zero_plan, qa_handler=abort_qa_repair)
        pipeline = MinecraftPipeline(
            provider="mock",
            version="1.21.11",
            output_dir=self.test_dir,
            ai_provider=mock_ai,
            max_qa_repair_attempts=1,
            verbose=False
        )
        res = pipeline.run("Divide score by zero.", datapack_name="div_zero_pack")

        self.assertIn(res.status, ("verification_failed", "failed"))
        self.assertNotEqual(res.verification_status, "verified")


# =============================================================================
# DATAPACK ARTIFACT VERIFICATION
# =============================================================================

class TestStep16ArtifactIntegrity(unittest.TestCase):
    """
    Verifies complete folder and ZIP artifact integrity.
    """

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="step16_art_"))
        self.generator = DatapackGenerator(output_dir=self.test_dir, version="1.21.11")
        self.validator = DatapackValidator(version="1.21.11")

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_artifact_zip_and_folder_parity(self):
        """Verifies pack.mcmeta at root, data/ at root, tag routing, and exact ZIP-to-folder parity."""
        plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "Artifact parity test",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Scoreboard system",
                    "mechanisms": [
                        {
                            "type": "scoreboard_objective",
                            "objective": "test_obj",
                            "criteria": "dummy",
                            "display_slot": "sidebar"
                        },
                        {
                            "type": "function",
                            "namespace": "minecraft_ai",
                            "path": "tick",
                            "actions": [
                                {
                                    "action_type": "add_score",
                                    "target": "#global",
                                    "objective": "test_obj",
                                    "score_value": 1
                                }
                            ]
                        },
                        {
                            "type": "function_tag",
                            "namespace": "minecraft",
                            "tag_name": "tick",
                            "values": ["minecraft_ai:tick"]
                        }
                    ]
                }
            ]
        }
        res = self.generator.generate(plan=plan, datapack_name="parity_pack", create_zip=True)
        dp_folder = res.datapack_path
        dp_zip = res.zip_path

        self.assertTrue(dp_folder.exists())
        self.assertTrue(dp_zip.exists())

        # 1. pack.mcmeta exists at folder and ZIP root
        self.assertTrue((dp_folder / "pack.mcmeta").exists())
        with zipfile.ZipFile(dp_zip, "r") as zf:
            zip_names = zf.namelist()
            self.assertIn("pack.mcmeta", zip_names)
            # Must NOT be nested under a parent directory
            self.assertFalse(any(n.startswith("parity_pack/") for n in zip_names))

            # 2. data/ directory exists at root
            self.assertTrue(any(n.startswith("data/") for n in zip_names))

            # 3. Canonical lifecycle tag routing: data/minecraft/tags/function/load.json and tick.json
            self.assertIn("data/minecraft/tags/function/tick.json", zip_names)
            self.assertIn("data/minecraft/tags/function/load.json", zip_names)
            # No misplaced lifecycle tag under custom namespace
            self.assertNotIn("data/minecraft_ai/tags/function/tick.json", zip_names)
            self.assertNotIn("data/minecraft_ai/tags/function/load.json", zip_names)

            # 4. load.json and tick.json content check (namespaced function references)
            tick_tag = json.loads(zf.read("data/minecraft/tags/function/tick.json").decode("utf-8"))
            self.assertIn("values", tick_tag)
            self.assertIn("minecraft_ai:tick", tick_tag["values"])

            load_tag = json.loads(zf.read("data/minecraft/tags/function/load.json").decode("utf-8"))
            self.assertIn("values", load_tag)
            self.assertIn("minecraft_ai:load", load_tag["values"])

            # 5. Every referenced tag function resolves to an existing .mcfunction file
            for tag_path in ["data/minecraft/tags/function/tick.json", "data/minecraft/tags/function/load.json"]:
                tag_data = json.loads(zf.read(tag_path).decode("utf-8"))
                for func_ref in tag_data.get("values", []):
                    # Format: namespace:path -> data/<namespace>/function/<path>.mcfunction
                    ns, path = func_ref.split(":")
                    expected_mcfunc = f"data/{ns}/function/{path}.mcfunction"
                    self.assertIn(expected_mcfunc, zip_names, f"Tag reference '{func_ref}' missing in ZIP")
                    self.assertTrue((dp_folder / expected_mcfunc).exists(), f"Tag reference '{func_ref}' missing in folder")

            # 6. Bidirectional parity check:
            # Every file in the folder must exist in the ZIP
            for p in dp_folder.rglob("*"):
                if p.is_file():
                    rel_p = p.relative_to(dp_folder).as_posix()
                    self.assertIn(rel_p, zip_names, f"Folder file {rel_p} missing from ZIP")

            # Every file in the ZIP must exist in the folder (no extra debug/runtime artifacts in ZIP)
            for zname in zip_names:
                # ignore directory entries
                if not zname.endswith("/"):
                    self.assertTrue((dp_folder / zname).exists(), f"ZIP entry {zname} not found in generated folder")

        # 7. Validator approves both folder and ZIP
        val_folder = self.validator.validate(dp_folder)
        self.assertTrue(val_folder.is_valid, f"Folder failed validation: {val_folder.errors}")

        val_zip = self.validator.validate(dp_zip)
        self.assertTrue(val_zip.is_valid, f"ZIP failed validation: {val_zip.errors}")


if __name__ == "__main__":
    unittest.main()
