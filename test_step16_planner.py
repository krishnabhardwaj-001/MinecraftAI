"""
Step 16.6 — Planner / AI Instruction Alignment Tests

Verifies that the Planner and its prompt/context handling/normalization are aligned
with the structured scoreboard architecture (Steps 16.1-16.5).

Tests verify:
1. Objective creation.
2. Display configuration.
3. Score set.
4. Score add.
5. Score remove.
6. Score reset.
7. Score operation (all 9 operations: '=', '+=', '-=', '*=', '/=', '%=', '<', '>', '><').
8. Score range condition.
9. Score-to-score comparison.
10. State-machine + scoreboard interaction.
11. Load-vs-tick planning.
12. Ambiguous scoreboard request -> clarification.
13. Missing score value -> clarification.
14. Missing comparison operand -> clarification.
15. Arbitrary wording variations.
16. Existing rain request remains correctly planned.
17. Existing night-vision request remains correctly planned.
18. Existing ambiguous "make the zombie stronger" behavior remains clarification.
"""

import json
import unittest
import pytest
from typing import Any, Dict, List, Optional

from ai.planner import MinecraftPlanner, create_plan, validate_plan_mechanisms
from generator.models import (
    ActionSpecification,
    MechanismSpecification,
    ScoreCompareCondition,
    ScoreboardObjectiveDefinition,
    validate_mechanism_specification,
)
from pipeline import run_minecraft_pipeline


class MockAIProvider:
    """
    Mock AI Provider for deterministic unit testing of the Planner without network or Ollama calls.
    """
    def __init__(self, response_factory=None):
        self.call_count = 0
        self.recorded_calls = []
        self.response_factory = response_factory

    def generate_structured(self, system_prompt: str, user_prompt: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        self.call_count += 1
        self.recorded_calls.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "schema": schema
        })
        if self.response_factory:
            return self.response_factory(self.call_count, system_prompt, user_prompt, schema)
        return {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "Mock plan",
            "implementation_plan": [],
            "missing_knowledge": [],
            "clarifications": []
        }


class TestStep16Planner(unittest.TestCase):
    """
    Step 16.6 comprehensive test suite for AI Planner scoreboard alignment.
    """

    def setUp(self):
        self.planner = MinecraftPlanner(version="1.21.11")

    # =========================================================================
    # PROMPT & KNOWLEDGE VERIFICATION
    # =========================================================================

    def test_planner_system_prompt_scoreboard_rules(self):
        """Verify that _system_prompt includes Rules 26-30 and Section 9 mechanism specs."""
        prompt = self.planner._system_prompt()
        self.assertIn("26. For scoreboard objective requests", prompt)
        self.assertIn("27. For score actions", prompt)
        self.assertIn("28. For score conditions", prompt)
        self.assertIn("29. Lifecycle Separation (Load vs Tick vs State Machine)", prompt)
        self.assertIn("30. Scoreboard Ambiguity & Clarification", prompt)
        self.assertIn("Scoreboard Objective Mechanism", prompt)
        self.assertIn("deathCount", prompt)
        self.assertIn("sidebar", prompt)
        self.assertIn("below_name", prompt)
        self.assertIn("operation_score", prompt)
        self.assertIn("score_compare", prompt)
        self.assertIn("Do NOT output raw", prompt)

    def test_planner_build_user_prompt_includes_retrieved_knowledge(self):
        """Verify that retrieved scoreboard knowledge reaches the user prompt."""
        understanding = {
            "status": "understood",
            "minecraft_version": "1.21.11",
            "edition": "Java",
            "understood_request": "Track deaths on sidebar",
            "requirements": [{"intent": "track deaths"}]
        }
        context = {
            "minecraft": {"version": "1.21.11", "edition": "Java"},
            "user_request": "Track deaths on sidebar",
            "requirements": [{"intent": "track deaths"}],
            "knowledge": {
                "scoreboards": [
                    {"topic": "objectives", "content": "scoreboard objectives add <name> <criteria>"},
                    {"topic": "display", "content": "scoreboard objectives setdisplay sidebar <name>"}
                ]
            }
        }
        user_prompt = self.planner._build_user_prompt(understanding, context)
        self.assertIn("RETRIEVED MINECRAFT KNOWLEDGE:", user_prompt)
        self.assertIn("scoreboards", user_prompt)
        self.assertIn("sidebar", user_prompt)

    # =========================================================================
    # 1. OBJECTIVE CREATION
    # =========================================================================

    def test_1_objective_creation(self):
        """Planner normalizes and validates structured scoreboard_objective mechanism."""
        raw_result = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "Track player deaths",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Track deaths",
                    "mechanisms": [
                        {
                            "type": "scoreboard_objective",
                            "objective": "deaths",
                            "criteria": "deathCount",
                            "display_name": "Deaths"
                        }
                    ]
                }
            ],
            "missing_knowledge": [],
            "clarifications": []
        }
        normalized = self.planner._normalize_result(raw_result, {"understood_request": "Track player deaths"})
        self.assertEqual(normalized["status"], "ready")
        mech = normalized["implementation_plan"][0]["mechanisms"][0]
        self.assertEqual(mech["type"], "scoreboard_objective")
        self.assertEqual(mech["objective"], "deaths")
        self.assertEqual(mech["criteria"], "deathCount")
        self.assertEqual(mech["display_name"], "Deaths")
        # Validate mechanism specification
        validate_plan_mechanisms(normalized)
        # Ensure no raw commands
        self.assertFalse(mech.get("commands"))

    # =========================================================================
    # 2. DISPLAY CONFIGURATION
    # =========================================================================

    def test_2_display_configuration(self):
        """Planner correctly validates display slots: sidebar, below_name, list, team sidebar."""
        slots = ["sidebar", "below_name", "list", "sidebar.team.red"]
        for slot in slots:
            raw = {
                "status": "ready",
                "summary": f"Display on {slot}",
                "implementation_plan": [
                    {
                        "requirement_index": 0,
                        "objective": f"Show {slot}",
                        "mechanisms": [
                            {
                                "type": "scoreboard_objective",
                                "objective": "myscore",
                                "criteria": "dummy",
                                "display_slot": slot
                            }
                        ]
                    }
                ]
            }
            norm = self.planner._normalize_result(raw, {})
            mech = norm["implementation_plan"][0]["mechanisms"][0]
            self.assertEqual(mech["display_slot"], slot)
            validate_plan_mechanisms(norm)

    # =========================================================================
    # 3. SCORE SET
    # =========================================================================

    def test_3_score_set(self):
        """Planner correctly models set_score action for #global or player holder."""
        raw = {
            "status": "ready",
            "summary": "Initialize global counter to 0",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Init counter",
                    "mechanisms": [
                        {
                            "type": "function",
                            "namespace": "minecraft_ai",
                            "path": "load",
                            "actions": [
                                {
                                    "action_type": "set_score",
                                    "target": "#global",
                                    "objective": "counter",
                                    "score_value": 0
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        norm = self.planner._normalize_result(raw, {})
        action = norm["implementation_plan"][0]["mechanisms"][0]["actions"][0]
        self.assertEqual(action["action_type"], "set_score")
        self.assertEqual(action["target"], "#global")
        self.assertEqual(action["objective"], "counter")
        self.assertEqual(action["score_value"], 0)
        validate_plan_mechanisms(norm)
        # Ensure no raw commands
        self.assertIsNone(action.get("raw_command"))

    # =========================================================================
    # 4. SCORE ADD
    # =========================================================================

    def test_4_score_add(self):
        """Planner correctly models add_score action for players."""
        raw = {
            "status": "ready",
            "summary": "Give players 10 points",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Add points",
                    "mechanisms": [
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
            ]
        }
        norm = self.planner._normalize_result(raw, {})
        action = norm["implementation_plan"][0]["mechanisms"][0]["actions"][0]
        self.assertEqual(action["action_type"], "add_score")
        self.assertEqual(action["target"], "@a")
        self.assertEqual(action["objective"], "points")
        self.assertEqual(action["score_value"], 10)
        validate_plan_mechanisms(norm)

    # =========================================================================
    # 5. SCORE REMOVE
    # =========================================================================

    def test_5_score_remove(self):
        """Planner correctly models remove_score action."""
        raw = {
            "status": "ready",
            "summary": "Remove 5 points from player",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Deduct points",
                    "mechanisms": [
                        {
                            "type": "function",
                            "namespace": "minecraft_ai",
                            "path": "penalty",
                            "actions": [
                                {
                                    "action_type": "remove_score",
                                    "target": "@p",
                                    "objective": "points",
                                    "score_value": 5
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        norm = self.planner._normalize_result(raw, {})
        action = norm["implementation_plan"][0]["mechanisms"][0]["actions"][0]
        self.assertEqual(action["action_type"], "remove_score")
        self.assertEqual(action["target"], "@p")
        self.assertEqual(action["objective"], "points")
        self.assertEqual(action["score_value"], 5)
        validate_plan_mechanisms(norm)

    # =========================================================================
    # 6. SCORE RESET
    # =========================================================================

    def test_6_score_reset(self):
        """Planner correctly models reset_score action."""
        raw = {
            "status": "ready",
            "summary": "Reset temporary score",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Reset temp",
                    "mechanisms": [
                        {
                            "type": "function",
                            "namespace": "minecraft_ai",
                            "path": "reset",
                            "actions": [
                                {
                                    "action_type": "reset_score",
                                    "target": "@a",
                                    "objective": "temp"
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        norm = self.planner._normalize_result(raw, {})
        action = norm["implementation_plan"][0]["mechanisms"][0]["actions"][0]
        self.assertEqual(action["action_type"], "reset_score")
        self.assertEqual(action["target"], "@a")
        self.assertEqual(action["objective"], "temp")
        validate_plan_mechanisms(norm)

    # =========================================================================
    # 7. SCORE OPERATION (ALL 9 OPERATIONS)
    # =========================================================================

    def test_7_score_operation_all_nine_operators(self):
        """Planner supports all 9 Minecraft scoreboard operations: =, +=, -=, *=, /=, %=, <, >, ><."""
        operations = ["=", "+=", "-=", "*=", "/=", "%=", "<", ">", "><"]
        for op in operations:
            raw = {
                "status": "ready",
                "summary": f"Perform score op {op}",
                "implementation_plan": [
                    {
                        "requirement_index": 0,
                        "objective": f"Op {op}",
                        "mechanisms": [
                            {
                                "type": "function",
                                "namespace": "minecraft_ai",
                                "path": "calc",
                                "actions": [
                                    {
                                        "action_type": "operation_score",
                                        "target": "@s",
                                        "objective": "score_a",
                                        "operation": op,
                                        "source_holder": "@s",
                                        "source_objective": "score_b"
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
            norm = self.planner._normalize_result(raw, {})
            action = norm["implementation_plan"][0]["mechanisms"][0]["actions"][0]
            self.assertEqual(action["action_type"], "operation_score")
            self.assertEqual(action["operation"], op)
            self.assertEqual(action["source_holder"], "@s")
            self.assertEqual(action["source_objective"], "score_b")
            validate_plan_mechanisms(norm)

    # =========================================================================
    # 8. SCORE RANGE CONDITION
    # =========================================================================

    def test_8_score_range_condition(self):
        """Planner models structured score range conditions on actions."""
        ranges = ["10", "1..10", "5..", "..0"]
        for rng in ranges:
            raw = {
                "status": "ready",
                "summary": f"Reward if score in {rng}",
                "implementation_plan": [
                    {
                        "requirement_index": 0,
                        "objective": f"Check {rng}",
                        "mechanisms": [
                            {
                                "type": "function",
                                "namespace": "minecraft_ai",
                                "path": "check",
                                "actions": [
                                    {
                                        "action_type": "give_item",
                                        "target": "@s",
                                        "item": "minecraft:diamond",
                                        "count": 1,
                                        "conditions": [
                                            {
                                                "type": "score",
                                                "holder": "@s",
                                                "objective": "points",
                                                "range": rng
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
            norm = self.planner._normalize_result(raw, {})
            action = norm["implementation_plan"][0]["mechanisms"][0]["actions"][0]
            self.assertEqual(len(action["conditions"]), 1)
            cond = action["conditions"][0]
            self.assertEqual(cond["type"], "score")
            self.assertEqual(cond["holder"], "@s")
            self.assertEqual(cond["range"], rng)
            validate_plan_mechanisms(norm)

    # =========================================================================
    # 9. SCORE-TO-SCORE COMPARISON
    # =========================================================================

    def test_9_score_to_score_comparison(self):
        """Planner models structured score_compare conditions with valid operators."""
        operators = ["<", "<=", "=", ">=", ">"]
        for op in operators:
            raw = {
                "status": "ready",
                "summary": f"Check score {op} highscore",
                "implementation_plan": [
                    {
                        "requirement_index": 0,
                        "objective": f"Compare {op}",
                        "mechanisms": [
                            {
                                "type": "function",
                                "namespace": "minecraft_ai",
                                "path": "highscore",
                                "actions": [
                                    {
                                        "action_type": "give_item",
                                        "target": "@s",
                                        "item": "minecraft:emerald",
                                        "count": 1,
                                        "conditions": [
                                            {
                                                "type": "score_compare",
                                                "target": "@s",
                                                "target_objective": "current_score",
                                                "operator": op,
                                                "source": "@s",
                                                "source_objective": "high_score"
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
            norm = self.planner._normalize_result(raw, {})
            action = norm["implementation_plan"][0]["mechanisms"][0]["actions"][0]
            self.assertEqual(len(action["conditions"]), 1)
            cond = action["conditions"][0]
            self.assertEqual(cond["type"], "score_compare")
            self.assertEqual(cond["operator"], op)
            validate_plan_mechanisms(norm)

    # =========================================================================
    # 10. STATE-MACHINE + SCOREBOARD INTERACTION
    # =========================================================================

    def test_10_state_machine_scoreboard_interaction(self):
        """Edge-triggered event (e.g. rain start) uses state_machine mechanism with scoreboard state tracking."""
        raw = {
            "status": "ready",
            "summary": "Give every player a diamond once when it starts raining",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Give diamond on rain start",
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
            ]
        }
        norm = self.planner._normalize_result(raw, {})
        mechs = norm["implementation_plan"][0]["mechanisms"]
        self.assertEqual(len(mechs), 2)
        sm_mech = mechs[1]
        self.assertEqual(sm_mech["type"], "state_machine")
        self.assertEqual(sm_mech["objective"], "rain_state")
        self.assertEqual(sm_mech["state_scope"], "global")
        self.assertEqual(sm_mech["on_enter"][0]["action_type"], "give_item")
        validate_plan_mechanisms(norm)

    # =========================================================================
    # 11. LOAD VS TICK PLANNING
    # =========================================================================

    def test_11_load_vs_tick_planning(self):
        """One-time objective creation belongs in load; continuous updates belong in continuous_action / tick."""
        raw = {
            "status": "ready",
            "summary": "Create objective in load and increment counter on tick",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Register counter and increment",
                    "mechanisms": [
                        # Load: objective creation
                        {
                            "type": "scoreboard_objective",
                            "objective": "tick_count",
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
                                    "objective": "tick_count",
                                    "score_value": 1
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        norm = self.planner._normalize_result(raw, {})
        mechs = norm["implementation_plan"][0]["mechanisms"]
        self.assertEqual(mechs[0]["type"], "scoreboard_objective")
        self.assertEqual(mechs[1]["type"], "continuous_action")
        self.assertEqual(mechs[1]["actions"][0]["action_type"], "add_score")
        validate_plan_mechanisms(norm)

    # =========================================================================
    # 12. AMBIGUOUS SCOREBOARD REQUEST -> CLARIFICATION
    # =========================================================================

    def test_12_ambiguous_scoreboard_request_clarification(self):
        """When objective purpose/criteria is unknown, Planner outputs needs_clarification."""
        raw = {
            "status": "needs_clarification",
            "summary": "User wants a scoreboard but did not specify what to track",
            "implementation_plan": [],
            "clarifications": [
                "What should the scoreboard track (e.g. deaths, kills, custom dummy points)?"
            ]
        }
        norm = self.planner._normalize_result(raw, {})
        self.assertEqual(norm["status"], "needs_clarification")
        self.assertGreater(len(norm["clarifications"]), 0)

    # =========================================================================
    # 13. MISSING SCORE VALUE -> CLARIFICATION
    # =========================================================================

    def test_13_missing_score_value_clarification(self):
        """When score value is missing, Planner outputs needs_clarification."""
        raw = {
            "status": "needs_clarification",
            "summary": "User requested giving points without specifying count or objective",
            "implementation_plan": [],
            "clarifications": [
                "How many points should be given, and which scoreboard objective should receive them?"
            ]
        }
        norm = self.planner._normalize_result(raw, {})
        self.assertEqual(norm["status"], "needs_clarification")
        self.assertIn("How many points", norm["clarifications"][0])

    # =========================================================================
    # 14. MISSING COMPARISON OPERAND -> CLARIFICATION
    # =========================================================================

    def test_14_missing_comparison_operand_clarification(self):
        """When comparison operands are missing, Planner asks for clarification."""
        raw = {
            "status": "needs_clarification",
            "summary": "User asked to compare score without specifying operands",
            "implementation_plan": [],
            "clarifications": [
                "Which score or player should be compared, and against what value or second score?"
            ]
        }
        norm = self.planner._normalize_result(raw, {})
        self.assertEqual(norm["status"], "needs_clarification")
        self.assertIn("compared", norm["clarifications"][0])

    # =========================================================================
    # 15. ARBITRARY WORDING VARIATIONS
    # =========================================================================

    def test_15_arbitrary_wording_variations(self):
        """Test multiple arbitrary wording variations normalize into valid structured specifications."""
        scenarios = [
            # "Track deaths for every player"
            {
                "raw": {
                    "status": "ready",
                    "summary": "Track deaths for every player",
                    "implementation_plan": [{
                        "requirement_index": 0,
                        "objective": "Track deaths",
                        "mechanisms": [{"type": "scoreboard_objective", "objective": "deaths", "criteria": "deathCount"}]
                    }]
                },
                "expected_type": "scoreboard_objective",
                "expected_obj": "deaths"
            },
            # "Show player deaths on the sidebar"
            {
                "raw": {
                    "status": "ready",
                    "summary": "Show player deaths on the sidebar",
                    "implementation_plan": [{
                        "requirement_index": 0,
                        "objective": "Sidebar deaths",
                        "mechanisms": [{"type": "scoreboard_objective", "objective": "deaths", "criteria": "deathCount", "display_slot": "sidebar"}]
                    }]
                },
                "expected_type": "scoreboard_objective",
                "expected_obj": "deaths"
            },
            # "Display health below the player's name"
            {
                "raw": {
                    "status": "ready",
                    "summary": "Display health below player name",
                    "implementation_plan": [{
                        "requirement_index": 0,
                        "objective": "Health below name",
                        "mechanisms": [{"type": "scoreboard_objective", "objective": "health", "criteria": "health", "display_slot": "below_name"}]
                    }]
                },
                "expected_type": "scoreboard_objective",
                "expected_obj": "health"
            },
            # "Reset everyone's temporary score"
            {
                "raw": {
                    "status": "ready",
                    "summary": "Reset temporary score",
                    "implementation_plan": [{
                        "requirement_index": 0,
                        "objective": "Reset temp score",
                        "mechanisms": [{
                            "type": "function",
                            "namespace": "minecraft_ai",
                            "path": "reset_temp",
                            "actions": [{"action_type": "reset_score", "target": "@a", "objective": "temp"}]
                        }]
                    }]
                },
                "expected_type": "function",
                "expected_obj": None
            }
        ]

        for s in scenarios:
            norm = self.planner._normalize_result(s["raw"], {})
            mech = norm["implementation_plan"][0]["mechanisms"][0]
            self.assertEqual(mech["type"], s["expected_type"])
            if s["expected_obj"]:
                self.assertEqual(mech["objective"], s["expected_obj"])
            validate_plan_mechanisms(norm)

    # =========================================================================
    # 16. EXISTING RAIN REQUEST REMAINS CORRECTLY PLANNED
    # =========================================================================

    def test_16_existing_rain_request_remains_correctly_planned(self):
        """Rain reward plan remains structured state-machine with on_enter action."""
        raw = {
            "status": "ready",
            "summary": "Give every player a diamond when it starts raining",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Diamond on rain start",
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
            ]
        }
        norm = self.planner._normalize_result(raw, {})
        self.assertEqual(norm["status"], "ready")
        sm = norm["implementation_plan"][0]["mechanisms"][1]
        self.assertEqual(sm["type"], "state_machine")
        self.assertEqual(sm["on_enter"][0]["action_type"], "give_item")
        validate_plan_mechanisms(norm)

    # =========================================================================
    # 17. EXISTING NIGHT-VISION REQUEST REMAINS CORRECTLY PLANNED
    # =========================================================================

    def test_17_existing_night_vision_request_remains_correctly_planned(self):
        """Night vision on night start remains structured state-machine plan."""
        raw = {
            "status": "ready",
            "summary": "Give players night vision when night starts",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Night vision at night",
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
            ]
        }
        norm = self.planner._normalize_result(raw, {})
        self.assertEqual(norm["status"], "ready")
        sm = norm["implementation_plan"][0]["mechanisms"][1]
        self.assertEqual(sm["type"], "state_machine")
        self.assertEqual(sm["on_enter"][0]["action_type"], "apply_effect")
        self.assertEqual(sm["on_enter"][0]["effect"], "minecraft:night_vision")
        validate_plan_mechanisms(norm)

    # =========================================================================
    # 18. EXISTING AMBIGUOUS "MAKE THE ZOMBIE STRONGER" REMAINS CLARIFICATION
    # =========================================================================

    @pytest.mark.live
    def test_18_ambiguous_zombie_request_remains_clarification(self):
        """Verify 'Make the zombie stronger' halts at clarification."""
        res = run_minecraft_pipeline("Make the zombie stronger.")
        self.assertEqual(res.status, "needs_clarification")
        self.assertIsNotNone(res.clarification)
        self.assertGreater(len(res.clarification), 0)

    # =========================================================================
    # END-TO-END MOCK AI PLANNER EXECUTION
    # =========================================================================

    def test_end_to_end_mock_planner_execution(self):
        """Verify create_plan works end-to-end with mock AI provider."""
        mock_response = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "Track deaths on sidebar",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Track deaths",
                    "mechanisms": [
                        {
                            "type": "scoreboard_objective",
                            "objective": "player_deaths",
                            "criteria": "deathCount",
                            "display_slot": "sidebar"
                        }
                    ]
                }
            ],
            "missing_knowledge": [],
            "clarifications": []
        }
        mock_ai = MockAIProvider(response_factory=lambda *args: mock_response)
        understanding = {
            "status": "understood",
            "minecraft_version": "1.21.11",
            "edition": "Java",
            "understood_request": "Track deaths on sidebar",
            "requirements": [{"intent": "track deaths on sidebar"}]
        }
        plan = create_plan(understanding, ai_provider=mock_ai)
        self.assertEqual(plan["status"], "ready")
        self.assertEqual(len(plan["implementation_plan"]), 1)
        mech = plan["implementation_plan"][0]["mechanisms"][0]
        self.assertEqual(mech["type"], "scoreboard_objective")
        self.assertEqual(mech["objective"], "player_deaths")
        self.assertEqual(mech["criteria"], "deathCount")
        self.assertEqual(mech["display_slot"], "sidebar")
        validate_plan_mechanisms(plan)


if __name__ == "__main__":
    unittest.main()
