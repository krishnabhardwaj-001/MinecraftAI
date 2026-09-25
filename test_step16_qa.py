"""
test_step16_qa.py - Step 16.5 QA Semantic Analysis & Runtime Simulation for Scoreboards
Authoritative target: Minecraft Java Edition 1.21.11

Tests all 28 required QA semantic analysis & simulation capabilities:
 1. set score
 2. add score
 3. remove score
 4. reset score
 5. all nine score operations (=, +=, -=, *=, /=, %=, <, >, ><)
 6. score range TRUE
 7. score range FALSE
 8. unknown score condition
 9. score-to-score comparison
10. score initialization
11. use-before-initialization
12. division by known zero
13. modulo by known zero
14. state transition FALSE -> TRUE
15. state transition TRUE -> FALSE
16. once-only event
17. repeated event detection
18. latch reset
19. latch never reset
20. unreachable event
21. lifecycle load initialization
22. lifecycle tick behavior
23. multiple mechanisms writing same score
24. deterministic findings
25. rain-start regression
26. night-start regression
27. existing Step 15 QA regression
28. existing Step 16 validator/generator compatibility
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

from generator.datapack_generator import DatapackGenerator
from generator.models import (
    ActionSpecification,
    MechanismSpecification,
    ScoreboardObjectiveDefinition,
)
from qa.analyzer import StaticSemanticAnalyzer
from qa.models import QACategory, QAFinding, QASeverity
from qa.reviewer import AutonomousQAReviewer
from qa.scoreboard_semantics import (
    AbstractScoreboardState,
    ScoreboardSemanticSimulator,
    TriState,
    java_int_div,
    java_int_rem,
    to_int32,
)
from validator.datapack_validator import DatapackValidator


class TestStep16QASemantics(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("generated") / "test_s16_qa"
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.simulator = ScoreboardSemanticSimulator(version="1.21.11")
        self.analyzer = StaticSemanticAnalyzer(version="1.21.11")
        self.reviewer = AutonomousQAReviewer(version="1.21.11")
        self.validator = DatapackValidator(version="1.21.11")

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def _create_synthetic_pack(
        self,
        pack_name: str,
        functions: Dict[str, str],
        tags: Optional[Dict[str, Any]] = None,
        predicates: Optional[Dict[str, Any]] = None,
        pack_format: int = 94,
        description: str = "QA Test Datapack"
    ) -> Path:
        pack_dir = self.test_dir / pack_name
        if pack_dir.exists():
            shutil.rmtree(pack_dir)
        pack_dir.mkdir(parents=True, exist_ok=True)

        mcmeta = pack_dir / "pack.mcmeta"
        mcmeta_data = {
            "pack": {
                "pack_format": pack_format,
                "description": description
            }
        }
        with open(mcmeta, "w", encoding="utf-8") as f:
            json.dump(mcmeta_data, f, indent=2)

        for fn_id, content in functions.items():
            if ":" in fn_id:
                ns, fn_path = fn_id.split(":", 1)
            else:
                ns, fn_path = "minecraft_ai", fn_id
            fn_file = pack_dir / "data" / ns / "function" / f"{fn_path}.mcfunction"
            fn_file.parent.mkdir(parents=True, exist_ok=True)
            with open(fn_file, "w", encoding="utf-8") as f:
                f.write(content)

        if predicates:
            for pred_id, pred_data in predicates.items():
                if ":" in pred_id:
                    ns, pred_path = pred_id.split(":", 1)
                else:
                    ns, pred_path = "minecraft_ai", pred_id
                pred_file = pack_dir / "data" / ns / "predicate" / f"{pred_path}.json"
                pred_file.parent.mkdir(parents=True, exist_ok=True)
                with open(pred_file, "w", encoding="utf-8") as f:
                    json.dump(pred_data, f, indent=2)

        if tags:
            for tag_id, tag_val in tags.items():
                if ":" in tag_id:
                    ns, tag_path = tag_id.split(":", 1)
                else:
                    ns, tag_path = "minecraft", tag_id
                tag_file = pack_dir / "data" / ns / "tags" / "function" / f"{tag_path}.json"
                tag_file.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(tag_val, list):
                    tag_content = {"values": tag_val}
                elif isinstance(tag_val, dict):
                    tag_content = tag_val
                else:
                    tag_content = {"values": [str(tag_val)]}
                with open(tag_file, "w", encoding="utf-8") as f:
                    json.dump(tag_content, f, indent=2)

        return pack_dir

    # --------------------------------------------------------------------------
    # 1. set score
    # --------------------------------------------------------------------------
    def test_01_set_score(self):
        state = AbstractScoreboardState()
        state.declare_objective("score", "dummy")
        self.assertFalse(state.is_initialized("#global", "score"))

        state.set_score("#global", "score", 42)
        self.assertTrue(state.is_initialized("#global", "score"))
        self.assertEqual(state.get_score("#global", "score"), 42)

        # 32-bit signed wrapping
        state.set_score("#global", "score", 2147483648)  # 2^31 wraps to -2147483648
        self.assertEqual(state.get_score("#global", "score"), -2147483648)

    # --------------------------------------------------------------------------
    # 2. add score
    # --------------------------------------------------------------------------
    def test_02_add_score(self):
        state = AbstractScoreboardState()
        state.set_score("#global", "score", 10)
        state.add_score("#global", "score", 5)
        self.assertEqual(state.get_score("#global", "score"), 15)

        # Adding to uninitialized score initializes it starting from 0
        state.add_score("#global", "fresh", 7)
        self.assertTrue(state.is_initialized("#global", "fresh"))
        self.assertEqual(state.get_score("#global", "fresh"), 7)

    # --------------------------------------------------------------------------
    # 3. remove score
    # --------------------------------------------------------------------------
    def test_03_remove_score(self):
        state = AbstractScoreboardState()
        state.set_score("#global", "score", 10)
        state.remove_score("#global", "score", 4)
        self.assertEqual(state.get_score("#global", "score"), 6)

    # --------------------------------------------------------------------------
    # 4. reset score
    # --------------------------------------------------------------------------
    def test_04_reset_score(self):
        state = AbstractScoreboardState()
        state.set_score("#global", "score1", 10)
        state.set_score("#global", "score2", 20)

        # Reset specific objective
        state.reset_score("#global", "score1")
        self.assertFalse(state.is_initialized("#global", "score1"))
        self.assertIsNone(state.get_score("#global", "score1"))
        self.assertTrue(state.is_initialized("#global", "score2"))

        # Reset all objectives for holder
        state.reset_score("#global")
        self.assertFalse(state.is_initialized("#global", "score2"))
        self.assertIsNone(state.get_score("#global", "score2"))

    # --------------------------------------------------------------------------
    # 5. All Nine Score Operations (=, +=, -=, *=, /=, %=, <, >, ><)
    # --------------------------------------------------------------------------
    def test_05_all_nine_score_operations(self):
        ops = ["=", "+=", "-=", "*=", "/=", "%=", "<", ">", "><"]
        for op in ops:
            state = AbstractScoreboardState()
            state.set_score("#t", "obj", 10)
            state.set_score("#s", "obj", 4)
            err = state.apply_operation("#t", "obj", op, "#s", "obj")
            self.assertIsNone(err, f"Operation {op} returned unexpected error: {err}")

            t_val = state.get_score("#t", "obj")
            if op == "=":
                self.assertEqual(t_val, 4)
            elif op == "+=":
                self.assertEqual(t_val, 14)
            elif op == "-=":
                self.assertEqual(t_val, 6)
            elif op == "*=":
                self.assertEqual(t_val, 40)
            elif op == "/=":
                self.assertEqual(t_val, 2)  # 10 / 4 = 2 (truncated)
            elif op == "%=":
                self.assertEqual(t_val, 2)  # 10 % 4 = 2
            elif op == "<":
                self.assertEqual(t_val, 4)  # min(10, 4)
            elif op == ">":
                self.assertEqual(t_val, 10) # max(10, 4)
            elif op == "><":
                self.assertEqual(t_val, 4)
                self.assertEqual(state.get_score("#s", "obj"), 10)

    # --------------------------------------------------------------------------
    # 6. score range TRUE
    # --------------------------------------------------------------------------
    def test_06_score_range_true(self):
        state = AbstractScoreboardState()
        state.set_score("#global", "timer", 5)

        self.assertEqual(state.eval_range("#global", "timer", "5"), TriState.TRUE)
        self.assertEqual(state.eval_range("#global", "timer", "1..10"), TriState.TRUE)
        self.assertEqual(state.eval_range("#global", "timer", "5..10"), TriState.TRUE)
        self.assertEqual(state.eval_range("#global", "timer", "1..5"), TriState.TRUE)
        self.assertEqual(state.eval_range("#global", "timer", "0.."), TriState.TRUE)
        self.assertEqual(state.eval_range("#global", "timer", "..10"), TriState.TRUE)

    # --------------------------------------------------------------------------
    # 7. score range FALSE
    # --------------------------------------------------------------------------
    def test_07_score_range_false(self):
        state = AbstractScoreboardState()
        state.set_score("#global", "timer", 15)

        self.assertEqual(state.eval_range("#global", "timer", "5"), TriState.FALSE)
        self.assertEqual(state.eval_range("#global", "timer", "1..10"), TriState.FALSE)
        self.assertEqual(state.eval_range("#global", "timer", "20.."), TriState.FALSE)
        self.assertEqual(state.eval_range("#global", "timer", "..10"), TriState.FALSE)

    # --------------------------------------------------------------------------
    # 8. unknown score condition
    # --------------------------------------------------------------------------
    def test_08_unknown_score_condition(self):
        state = AbstractScoreboardState()
        # Uninitialized holder / objective
        self.assertEqual(state.eval_range("#global", "uninit", "0"), TriState.UNKNOWN)
        self.assertEqual(state.eval_range("@a", "points", "1..5"), TriState.UNKNOWN)

    # --------------------------------------------------------------------------
    # 9. score-to-score comparison
    # --------------------------------------------------------------------------
    def test_09_score_to_score_comparison(self):
        state = AbstractScoreboardState()
        state.set_score("#t", "score", 10)
        state.set_score("#s", "score", 20)

        self.assertEqual(state.eval_comparison("#t", "score", "<", "#s", "score"), TriState.TRUE)
        self.assertEqual(state.eval_comparison("#t", "score", "<=", "#s", "score"), TriState.TRUE)
        self.assertEqual(state.eval_comparison("#t", "score", "=", "#s", "score"), TriState.FALSE)
        self.assertEqual(state.eval_comparison("#t", "score", ">=", "#s", "score"), TriState.FALSE)
        self.assertEqual(state.eval_comparison("#t", "score", ">", "#s", "score"), TriState.FALSE)

        # Uninitialized comparison
        self.assertEqual(state.eval_comparison("#t", "score", "<", "#uninit", "score"), TriState.UNKNOWN)

    # --------------------------------------------------------------------------
    # 10. score initialization
    # --------------------------------------------------------------------------
    def test_10_score_initialization(self):
        state = AbstractScoreboardState()
        self.assertFalse(state.is_initialized("#global", "score"))
        state.set_score("#global", "score", 0)
        self.assertTrue(state.is_initialized("#global", "score"))
        state.reset_score("#global", "score")
        self.assertFalse(state.is_initialized("#global", "score"))

    # --------------------------------------------------------------------------
    # 11. use-before-initialization
    # --------------------------------------------------------------------------
    def test_11_use_before_initialization(self):
        pack = self._create_synthetic_pack(
            "p11_uninit",
            functions={
                "minecraft_ai:tick": "execute if score #global uninit_state matches 0 run say uninit\n"
            }
        )
        findings = self.simulator.analyze_datapack(pack)
        self.assertTrue(any(f.id == "SCORE_USE_BEFORE_INITIALIZATION" for f in findings))

    # --------------------------------------------------------------------------
    # 12. division by known zero
    # --------------------------------------------------------------------------
    def test_12_division_by_known_zero(self):
        pack = self._create_synthetic_pack(
            "p12_div_zero",
            functions={
                "minecraft_ai:load": (
                    "scoreboard objectives add math dummy\n"
                    "scoreboard players set #global total 100\n"
                    "scoreboard players set #global div 0\n"
                ),
                "minecraft_ai:tick": (
                    "scoreboard players operation #global total /= #global div\n"
                )
            }
        )
        findings = self.simulator.analyze_datapack(pack)
        self.assertTrue(any(f.id == "SCORE_OPERATION_DIVIDE_BY_ZERO" for f in findings))

    # --------------------------------------------------------------------------
    # 13. modulo by known zero
    # --------------------------------------------------------------------------
    def test_13_modulo_by_known_zero(self):
        pack = self._create_synthetic_pack(
            "p13_mod_zero",
            functions={
                "minecraft_ai:load": (
                    "scoreboard objectives add math dummy\n"
                    "scoreboard players set #global total 100\n"
                    "scoreboard players set #global mod 0\n"
                ),
                "minecraft_ai:tick": (
                    "scoreboard players operation #global total %= #global mod\n"
                )
            }
        )
        findings = self.simulator.analyze_datapack(pack)
        self.assertTrue(any(f.id == "SCORE_OPERATION_MODULO_BY_ZERO" for f in findings))

    # --------------------------------------------------------------------------
    # 14. state transition FALSE -> TRUE (Rising Edge)
    # --------------------------------------------------------------------------
    def test_14_state_transition_false_to_true(self):
        state = AbstractScoreboardState()
        state.set_score("#global", "state", 0)

        cmd = self.simulator.parse_line(
            "execute if score #global state matches 0 if predicate is_active run give @a diamond 1",
            1, "test.mcfunction"
        )
        # Inactive phase
        res_false = self.simulator.evaluate_conditions(cmd, state, {"is_active": False})
        self.assertEqual(res_false, TriState.FALSE)

        # Rising edge
        res_true = self.simulator.evaluate_conditions(cmd, state, {"is_active": True})
        self.assertEqual(res_true, TriState.TRUE)

    # --------------------------------------------------------------------------
    # 15. state transition TRUE -> FALSE (Falling Edge)
    # --------------------------------------------------------------------------
    def test_15_state_transition_true_to_false(self):
        state = AbstractScoreboardState()
        state.set_score("#global", "state", 1)

        cmd_reset = self.simulator.parse_line(
            "execute unless predicate is_active run scoreboard players set #global state 0",
            1, "test.mcfunction"
        )
        # While condition is active, reset does not trigger
        res_active = self.simulator.evaluate_conditions(cmd_reset, state, {"is_active": True})
        self.assertEqual(res_active, TriState.FALSE)

        # When condition ceases (falling edge), reset triggers!
        res_cease = self.simulator.evaluate_conditions(cmd_reset, state, {"is_active": False})
        self.assertEqual(res_cease, TriState.TRUE)

    # --------------------------------------------------------------------------
    # 16. once-only event
    # --------------------------------------------------------------------------
    def test_16_once_only_event(self):
        pack = self._create_synthetic_pack(
            "p16_once_only",
            functions={
                "minecraft_ai:load": (
                    "scoreboard objectives add rain_state dummy\n"
                    "scoreboard players set #global rain_state 0\n"
                ),
                "minecraft_ai:tick": (
                    "execute if score #global rain_state matches 0 if predicate minecraft_ai:is_raining run give @s diamond 1\n"
                    "execute if predicate minecraft_ai:is_raining run scoreboard players set #global rain_state 1\n"
                    "execute unless predicate minecraft_ai:is_raining run scoreboard players set #global rain_state 0\n"
                )
            }
        )
        findings = self.simulator.analyze_datapack(pack)
        # Canonical once-only state machine must NOT have repeated event or unreachable findings
        self.assertFalse(any(f.id == "STATE_EVENT_REPEATS" for f in findings))
        self.assertFalse(any(f.id == "STATE_EVENT_UNREACHABLE" for f in findings))
        self.assertFalse(any(f.id == "STATE_LATCH_NEVER_RESETS" for f in findings))

    # --------------------------------------------------------------------------
    # 17. repeated event detection
    # --------------------------------------------------------------------------
    def test_17_repeated_event_detection(self):
        # Missing state latching causes action to fire repeatedly every tick
        pack = self._create_synthetic_pack(
            "p17_repeats",
            functions={
                "minecraft_ai:load": (
                    "scoreboard objectives add rain_state dummy\n"
                    "scoreboard players set #global rain_state 0\n"
                ),
                "minecraft_ai:tick": (
                    "execute if score #global rain_state matches 0 if predicate minecraft_ai:is_raining run give @s diamond 1\n"
                    "# Missing latch to 1!\n"
                    "execute unless predicate minecraft_ai:is_raining run scoreboard players set #global rain_state 0\n"
                )
            }
        )
        findings = self.simulator.analyze_datapack(pack)
        self.assertTrue(any(f.id == "STATE_EVENT_REPEATS" for f in findings))

    # --------------------------------------------------------------------------
    # 18. latch reset
    # --------------------------------------------------------------------------
    def test_18_latch_reset(self):
        pack = self._create_synthetic_pack(
            "p18_latch_resets",
            functions={
                "minecraft_ai:load": (
                    "scoreboard objectives add event_state dummy\n"
                    "scoreboard players set #global event_state 0\n"
                ),
                "minecraft_ai:tick": (
                    "execute if score #global event_state matches 0 if predicate cond run give @s diamond 1\n"
                    "execute if predicate cond run scoreboard players set #global event_state 1\n"
                    "execute unless predicate cond run scoreboard players set #global event_state 0\n"
                )
            }
        )
        findings = self.simulator.analyze_datapack(pack)
        self.assertFalse(any(f.id == "STATE_LATCH_NEVER_RESETS" for f in findings))

    # --------------------------------------------------------------------------
    # 19. latch never reset
    # --------------------------------------------------------------------------
    def test_19_latch_never_reset(self):
        pack = self._create_synthetic_pack(
            "p19_never_resets",
            functions={
                "minecraft_ai:load": (
                    "scoreboard objectives add event_state dummy\n"
                    "scoreboard players set #global event_state 0\n"
                ),
                "minecraft_ai:tick": (
                    "execute if score #global event_state matches 0 if predicate cond run give @s diamond 1\n"
                    "execute if predicate cond run scoreboard players set #global event_state 1\n"
                    "# Missing reset command!\n"
                )
            }
        )
        findings = self.simulator.analyze_datapack(pack)
        self.assertTrue(any(f.id == "STATE_LATCH_NEVER_RESETS" for f in findings))

    # --------------------------------------------------------------------------
    # 20. unreachable event
    # --------------------------------------------------------------------------
    def test_20_unreachable_event(self):
        # Initial state is 1, action requires matches 0, no transition sets state to 0
        pack = self._create_synthetic_pack(
            "p20_unreachable",
            functions={
                "minecraft_ai:load": (
                    "scoreboard objectives add event_state dummy\n"
                    "scoreboard players set #global event_state 1\n"
                ),
                "minecraft_ai:tick": (
                    "execute if score #global event_state matches 0 if predicate cond run give @s diamond 1\n"
                    "execute if predicate cond run scoreboard players set #global event_state 1\n"
                )
            }
        )
        findings = self.simulator.analyze_datapack(pack)
        self.assertTrue(any(f.id == "STATE_EVENT_UNREACHABLE" for f in findings))

    # --------------------------------------------------------------------------
    # 21. lifecycle load initialization
    # --------------------------------------------------------------------------
    def test_21_lifecycle_load_initialization(self):
        pack = self._create_synthetic_pack(
            "p21_load_init",
            functions={
                "minecraft_ai:load": (
                    "scoreboard objectives add points dummy\n"
                    "scoreboard players set #global points 100\n"
                ),
                "minecraft_ai:tick": (
                    "execute if score #global points matches 100 run say ready\n"
                )
            }
        )
        findings = self.simulator.analyze_datapack(pack)
        self.assertFalse(any(f.id == "SCORE_USE_BEFORE_INITIALIZATION" for f in findings))

    # --------------------------------------------------------------------------
    # 22. lifecycle tick behavior
    # --------------------------------------------------------------------------
    def test_22_lifecycle_tick_behavior(self):
        pack = self._create_synthetic_pack(
            "p22_tick_behavior",
            functions={
                "minecraft_ai:load": (
                    "scoreboard objectives add counter dummy\n"
                    "scoreboard players set #global counter 0\n"
                ),
                "minecraft_ai:tick": (
                    "scoreboard players add #global counter 1\n"
                )
            }
        )
        findings = self.simulator.analyze_datapack(pack)
        # Normal counter tick addition should not trigger errors
        self.assertEqual(len(findings), 0)

    # --------------------------------------------------------------------------
    # 23. multiple mechanisms writing same score
    # --------------------------------------------------------------------------
    def test_23_multiple_mechanisms_writing_same_score(self):
        pack = self._create_synthetic_pack(
            "p23_write_conflict",
            functions={
                "minecraft_ai:tick": (
                    "scoreboard players add #global points 1\n"
                    "scoreboard players set #global points 0\n"
                )
            }
        )
        findings = self.simulator.analyze_datapack(pack)
        self.assertTrue(any(f.id == "SCORE_WRITE_CONFLICT" for f in findings))

    # --------------------------------------------------------------------------
    # 24. deterministic findings
    # --------------------------------------------------------------------------
    def test_24_deterministic_findings(self):
        pack = self._create_synthetic_pack(
            "p24_deterministic",
            functions={
                "minecraft_ai:tick": (
                    "execute if score #global uninit matches 0 run say hi\n"
                    "scoreboard players add #global points 1\n"
                    "scoreboard players set #global points 0\n"
                )
            }
        )
        f1 = self.simulator.analyze_datapack(pack)
        f2 = self.simulator.analyze_datapack(pack)
        self.assertEqual(len(f1), len(f2))
        for item1, item2 in zip(f1, f2):
            self.assertEqual(item1.id, item2.id)
            self.assertEqual(item1.file, item2.file)
            self.assertEqual(item1.severity, item2.severity)
            self.assertEqual(item1.line_or_reference, item2.line_or_reference)

    # --------------------------------------------------------------------------
    # 25. rain-start regression
    # --------------------------------------------------------------------------
    def test_25_rain_start_regression(self):
        pack = self._create_synthetic_pack(
            "p25_rain_start",
            functions={
                "minecraft_ai:load": (
                    "scoreboard objectives add rain_state dummy\n"
                    "scoreboard players set #global rain_state 0\n"
                ),
                "minecraft_ai:tick": (
                    "execute if score #global rain_state matches 0 if predicate minecraft_ai:is_raining as @a at @s run give @s minecraft:diamond 1\n"
                    "execute if predicate minecraft_ai:is_raining run scoreboard players set #global rain_state 1\n"
                    "execute unless predicate minecraft_ai:is_raining run scoreboard players set #global rain_state 0\n"
                )
            },
            predicates={
                "minecraft_ai:is_raining": {
                    "condition": "minecraft:weather_check",
                    "raining": True
                }
            },
            tags={
                "minecraft:load": ["minecraft_ai:load"],
                "minecraft:tick": ["minecraft_ai:tick"]
            }
        )
        res = self.reviewer.review(
            datapack_dir=pack,
            original_request="When it starts raining, give every player one diamond."
        )
        self.assertTrue(res.is_pass)
        self.assertEqual(len(res.error_findings), 0)

    # --------------------------------------------------------------------------
    # 26. night-start regression
    # --------------------------------------------------------------------------
    def test_26_night_start_regression(self):
        pack = self._create_synthetic_pack(
            "p26_night_start",
            functions={
                "minecraft_ai:load": (
                    "scoreboard objectives add night_state dummy\n"
                    "scoreboard players set #global night_state 0\n"
                ),
                "minecraft_ai:tick": (
                    "execute if score #global night_state matches 0 if predicate minecraft_ai:is_night as @a at @s run effect give @s minecraft:night_vision 30 0 true\n"
                    "execute if predicate minecraft_ai:is_night run scoreboard players set #global night_state 1\n"
                    "execute unless predicate minecraft_ai:is_night run scoreboard players set #global night_state 0\n"
                )
            },
            predicates={
                "minecraft_ai:is_night": {
                    "condition": "minecraft:time_check",
                    "value": {
                        "min": 13000,
                        "max": 23000
                    }
                }
            },
            tags={
                "minecraft:load": ["minecraft_ai:load"],
                "minecraft:tick": ["minecraft_ai:tick"]
            }
        )
        res = self.reviewer.review(
            datapack_dir=pack,
            original_request="When it becomes night, give every player night vision once."
        )
        self.assertTrue(res.is_pass)
        self.assertEqual(len(res.error_findings), 0)

    # --------------------------------------------------------------------------
    # 27. existing Step 15 QA regression
    # --------------------------------------------------------------------------
    def test_27_existing_step15_qa_regression(self):
        pred_mech = MechanismSpecification(
            type="predicate",
            path="is_raining",
            namespace="minecraft_ai",
            condition_type="minecraft:weather_check",
            condition_params={"raining": True}
        )
        mech_spec = MechanismSpecification(
            type="state_machine",
            objective="rain_state",
            state_scope="global",
            condition_predicate="minecraft_ai:is_raining",
            on_enter=[
                ActionSpecification(
                    action_type="give_item",
                    target="@a",
                    item="minecraft:diamond",
                    count=1
                )
            ]
        )
        plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "State machine diamond on rain",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Give diamond when rain starts",
                    "mechanisms": [pred_mech.model_dump(), mech_spec.model_dump()]
                }
            ]
        }
        gen = DatapackGenerator(output_dir=self.test_dir / "gen_s15")
        res = gen.generate(plan=plan, datapack_name="s15_sm_pack")

        review_res = self.reviewer.review(
            datapack_dir=res.datapack_path,
            original_request="When rain starts, give every player one diamond.",
            plan=plan
        )
        self.assertTrue(review_res.is_pass)
        self.assertEqual(len(review_res.error_findings), 0)

    # --------------------------------------------------------------------------
    # 28. existing Step 16 validator/generator compatibility
    # --------------------------------------------------------------------------
    def test_28_step16_validator_generator_compatibility(self):
        # Create a pack with Step 16 scoreboard actions and objectives
        pack = self._create_synthetic_pack(
            "p28_s16_compat",
            functions={
                "minecraft_ai:load": (
                    "scoreboard objectives add deaths deathCount\n"
                    "scoreboard objectives add points dummy\n"
                    "scoreboard objectives setdisplay sidebar points\n"
                    "scoreboard players set #global points 0\n"
                ),
                "minecraft_ai:tick": (
                    "scoreboard players add #global points 1\n"
                    "execute if score @s deaths matches 1.. run scoreboard players add @s points 10\n"
                )
            },
            tags={
                "minecraft:load": ["minecraft_ai:load"],
                "minecraft:tick": ["minecraft_ai:tick"]
            }
        )
        # Step 16.4 static validator
        val_res = self.validator.validate(pack)
        self.assertTrue(val_res.is_valid, f"Validator failed: {val_res.errors}")

        # Step 16.5 semantic QA analyzer
        qa_findings = self.analyzer.analyze(pack)
        error_findings = [f for f in qa_findings if f.severity == QASeverity.ERROR]
        self.assertEqual(len(error_findings), 0, f"QA reported unexpected errors: {error_findings}")


if __name__ == "__main__":
    unittest.main()
