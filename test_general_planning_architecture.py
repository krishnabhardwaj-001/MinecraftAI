"""
test_general_planning_architecture.py - Regression & Generalization Tests for
MinecraftAI General Planning, Lifecycle Reconciliation, and Semantic QA Architecture.

Validates the 10 core architectural properties:
1. Related requirements describing one lifecycle are reconciled coherently.
2. Independent lifecycles retain independent state.
3. Multiple environmental predicates are simulated consistently without blind spots.
4. Conflicting state mutations are detected before generation.
5. Unreachable-logic findings trigger meaningful diagnosis and repair.
6. A previously unseen compound lifecycle request is handled generically.
7. The rain-reward regression case no longer generates competing state machines.
8. Unknown or ambiguous predicate relationships are handled conservatively.
9. Unrelated mechanism composition and existing generator behavior remain intact.
10. Repeated failed repairs terminate safely without endless regeneration.
"""
import copy
from pathlib import Path
import pytest

from ai.lifecycle_reconciler import (
    DEFAULT_LIFECYCLE_RECONCILER,
    are_predicates_complementary,
    is_explicit_latch_reset_action,
)
from generator.datapack_generator import DatapackGenerator
from generator.models import MechanismSpecification, ActionSpecification
from qa.models import QACategory, QAFinding, QAResult, QASeverity
from qa.repair import QARepairEngine
from qa.scoreboard_semantics import ScoreboardSemanticSimulator, AbstractScoreboardState, TriState


def test_1_related_requirements_reconciled_coherently():
    """
    1. Related requirements describing one lifecycle (trigger + explicit reset)
    are reconciled into a single coherent state machine.
    """
    pred_info = {
        "is_submerged": {"condition": "minecraft:entity_properties", "predicate": {"flags": {"is_swimming": True}}},
        "is_surfaced": {
            "condition": "minecraft:inverted",
            "term": {"condition": "minecraft:entity_properties", "predicate": {"flags": {"is_swimming": True}}}
        }
    }

    # Two mechanisms for water breathing: one triggers speed, one resets score
    mechs = [
        {
            "type": "state_machine",
            "objective": "swim_state",
            "condition_predicate": "custom:is_submerged",
            "on_enter": [{"action_type": "apply_effect", "target": "@s", "effect": "minecraft:speed", "duration": 10}]
        },
        {
            "type": "state_machine",
            "objective": "swim_state",
            "condition_predicate": "custom:is_surfaced",
            "on_enter": [{"action_type": "set_score", "target": "#global", "objective": "swim_state", "score_value": 0}]
        }
    ]

    reconciled = DEFAULT_LIFECYCLE_RECONCILER.reconcile(mechs, pred_info)
    sms = [m for m in reconciled if m.get("type") == "state_machine"]

    # Must be reconciled into exactly 1 state machine
    assert len(sms) == 1
    assert sms[0]["objective"] == "swim_state"
    assert sms[0]["condition_predicate"] == "custom:is_submerged"
    # Action preserved in on_enter
    assert len(sms[0]["on_enter"]) == 1
    assert sms[0]["on_enter"][0]["effect"] == "minecraft:speed"


def test_2_independent_lifecycles_retain_independent_state():
    """
    2. Independent lifecycles that accidentally share an objective name
    have their state variables disambiguated so they never collide.
    """
    pred_info = {
        "is_raining": {"condition": "minecraft:weather_check", "raining": True},
        "is_night": {"condition": "minecraft:time_check", "value": {"min": 13000, "max": 24000}}
    }

    mechs = [
        {
            "type": "state_machine",
            "objective": "event_state",
            "condition_predicate": "custom:is_raining",
            "on_enter": [{"action_type": "give_item", "target": "@a", "item": "minecraft:diamond", "count": 1}]
        },
        {
            "type": "state_machine",
            "objective": "event_state",
            "condition_predicate": "custom:is_night",
            "on_enter": [{"action_type": "apply_effect", "target": "@a", "effect": "minecraft:night_vision", "duration": 60}]
        }
    ]

    reconciled = DEFAULT_LIFECYCLE_RECONCILER.reconcile(mechs, pred_info)
    sms = [m for m in reconciled if m.get("type") == "state_machine"]

    # Both independent lifecycles must be preserved
    assert len(sms) == 2
    objs = [s["objective"] for s in sms]
    # Objectives must be distinct to prevent cross-lifecycle state flapping
    assert len(set(objs)) == 2
    assert "event_state" in objs
    assert any("is_night" in o or "2" in o for o in objs)


def test_3_multi_predicate_simulation_evaluates_all_predicates(tmp_path: Path):
    """
    3. ScoreboardSemanticSimulator evaluates all environmental predicates in tick.mcfunction,
    not just the first one discovered.
    """
    pack_dir = tmp_path / "test_multi_pred"
    func_dir = pack_dir / "data" / "demo" / "function"
    pred_dir = pack_dir / "data" / "demo" / "predicate"
    func_dir.mkdir(parents=True)
    pred_dir.mkdir(parents=True)

    # Two predicates: pred_a and pred_b (independent)
    (pred_dir / "pred_a.json").write_text('{"condition": "minecraft:weather_check", "raining": true}', encoding="utf-8")
    (pred_dir / "pred_b.json").write_text('{"condition": "minecraft:time_check", "value": 18000}', encoding="utf-8")

    (func_dir / "load.mcfunction").write_text(
        "scoreboard objectives add state_a dummy\n"
        "scoreboard players set #global state_a 0\n"
        "scoreboard objectives add state_b dummy\n"
        "scoreboard players set #global state_b 0\n",
        encoding="utf-8"
    )

    # Function with two latched state machines using different predicates
    (func_dir / "tick.mcfunction").write_text(
        "execute if score #global state_a matches 0 if predicate demo:pred_a run give @a minecraft:diamond 1\n"
        "execute if predicate demo:pred_a run scoreboard players set #global state_a 1\n"
        "execute unless predicate demo:pred_a run scoreboard players set #global state_a 0\n"
        "execute if score #global state_b matches 0 if predicate demo:pred_b run give @a minecraft:emerald 1\n"
        "execute if predicate demo:pred_b run scoreboard players set #global state_b 1\n"
        "execute unless predicate demo:pred_b run scoreboard players set #global state_b 0\n",
        encoding="utf-8"
    )

    sim = ScoreboardSemanticSimulator()
    findings = sim.analyze_datapack(pack_dir)

    # Neither state machine should be falsely flagged as unreachable
    unreachable_findings = [f for f in findings if f.id == "STATE_EVENT_UNREACHABLE"]
    assert len(unreachable_findings) == 0, f"Expected 0 unreachable findings, got: {unreachable_findings}"


def test_4_conflicting_state_mutation_prevention(tmp_path: Path):
    """
    4. Generator reconciles redundant reset state machines before writing tick.mcfunction,
    preventing contradictory latch overwrites in the same tick.
    """
    gen = DatapackGenerator(output_dir=tmp_path)
    plan = {
        "status": "ready",
        "implementation_plan": [
            {
                "requirement_index": 0,
                "objective": "trigger",
                "mechanisms": [
                    {
                        "type": "state_machine",
                        "objective": "weather_state",
                        "condition_predicate": "demo:is_raining",
                        "on_enter": [{"action_type": "give_item", "target": "@a", "item": "minecraft:diamond", "count": 1}]
                    },
                    {
                        "type": "state_machine",
                        "objective": "weather_state",
                        "condition_predicate": "demo:is_clear",
                        "on_enter": [{"action_type": "set_score", "target": "#global", "objective": "weather_state", "score_value": 0}]
                    },
                    {
                        "type": "predicate",
                        "path": "is_raining",
                        "condition_type": "minecraft:weather_check",
                        "condition_params": {"raining": True}
                    },
                    {
                        "type": "predicate",
                        "path": "is_clear",
                        "condition_type": "minecraft:inverted",
                        "condition_params": {"term": {"condition": "minecraft:weather_check", "raining": True}}
                    }
                ]
            }
        ]
    }

    res = gen.generate(plan=plan, datapack_name="test_conflict_prevention", clean=True)
    tick_file = Path(res.datapack_path) / "data" / "minecraft_ai" / "function" / "tick.mcfunction"
    assert tick_file.exists()
    content = tick_file.read_text(encoding="utf-8")

    # Contradictory competing reset 'unless predicate demo:is_clear' must NOT exist
    assert "unless predicate demo:is_clear run scoreboard players set #global weather_state 0" not in content
    # The primary clean latch must exist
    assert "if score #global weather_state matches 0 if predicate demo:is_raining" in content


def test_5_unreachable_logic_triggers_meaningful_repair():
    """
    5. When a STATE_EVENT_UNREACHABLE finding occurs, QARepairEngine produces
    a reconciled plan with regenerate=True rather than an unchanged plan.
    """
    finding = QAFinding(
        id="STATE_EVENT_UNREACHABLE",
        severity=QASeverity.ERROR,
        category=QACategory.UNREACHABLE_LOGIC,
        file="data/demo/function/tick.mcfunction",
        line_or_reference="Line 11: execute if score #global rain_state matches 0 if predicate demo:is_clear ...",
        problem="State machine on_enter action is unreachable and never fires.",
        explanation="Action never fired during simulation.",
        expected_behavior="Action should fire on rising edge.",
        repair_required="Reconcile state machine."
    )
    qa_result = QAResult(
        status="failed",
        summary="State machine unreachable error",
        findings=[finding]
    )

    plan = {
        "status": "ready",
        "implementation_plan": [
            {
                "requirement_index": 0,
                "mechanisms": [
                    {
                        "type": "state_machine",
                        "objective": "rain_state",
                        "condition_predicate": "demo:is_raining",
                        "on_enter": [{"action_type": "give_item", "target": "@a", "item": "minecraft:diamond", "count": 1}]
                    },
                    {
                        "type": "state_machine",
                        "objective": "rain_state",
                        "condition_predicate": "demo:is_clear",
                        "on_enter": [{"action_type": "set_score", "target": "#global", "objective": "rain_state", "score_value": 0}]
                    }
                ]
            }
        ]
    }

    engine = QARepairEngine(ai_provider=object())
    repair_plan, corrected_plan = engine.diagnose_and_repair(qa_result, plan)

    # Must produce actionable repair
    assert repair_plan.regenerate is True
    assert "lifecycle reconciliation" in repair_plan.diagnosis
    # Reconciled plan must have only 1 unified state machine
    mechs = corrected_plan["implementation_plan"][0]["mechanisms"]
    sms = [m for m in mechs if m.get("type") == "state_machine"]
    assert len(sms) == 1
    assert sms[0]["condition_predicate"] == "demo:is_raining"


def test_6_unseen_compound_lifecycle_request(tmp_path: Path):
    """
    6. A previously unseen compound lifecycle request (sneak charging with un-sneak reset)
    is handled generically without request-specific production code.
    """
    gen = DatapackGenerator(output_dir=tmp_path)
    plan = {
        "status": "ready",
        "implementation_plan": [
            {
                "requirement_index": 0,
                "mechanisms": [
                    {
                        "type": "state_machine",
                        "objective": "sneak_latch",
                        "condition_predicate": "custom:is_sneaking",
                        "state_scope": "global",
                        "on_enter": [{"action_type": "apply_effect", "target": "@a", "effect": "minecraft:strength", "duration": 5}]
                    },
                    {
                        "type": "state_machine",
                        "objective": "sneak_latch",
                        "condition_predicate": "custom:not_sneaking",
                        "state_scope": "global",
                        "on_enter": [{"action_type": "set_score", "target": "#global", "objective": "sneak_latch", "score_value": 0}]
                    },
                    {
                        "type": "predicate",
                        "path": "is_sneaking",
                        "condition_type": "minecraft:entity_properties",
                        "condition_params": {"entity": "this", "predicate": {"flags": {"is_sneaking": True}}}
                    },
                    {
                        "type": "predicate",
                        "path": "not_sneaking",
                        "condition_type": "minecraft:inverted",
                        "condition_params": {"term": {"condition": "minecraft:entity_properties", "predicate": {"flags": {"is_sneaking": True}}}}
                    }
                ]
            }
        ]
    }

    res = gen.generate(plan=plan, datapack_name="test_sneak_compound", clean=True)
    sim = ScoreboardSemanticSimulator()
    findings = sim.analyze_datapack(Path(res.datapack_path))

    # Clean generation without unlatched repetitions or unreachable logic
    error_findings = [f for f in findings if f.severity == QASeverity.ERROR]
    assert len(error_findings) == 0, f"Expected 0 error findings, got: {error_findings}"


def test_7_rain_reward_regression_reconciles_cleanly(tmp_path: Path):
    """
    7. The exact rain-reward scenario that previously failed QA now reconciles
    cleanly into a single state machine and passes semantic simulation.
    """
    gen = DatapackGenerator(output_dir=tmp_path)
    plan = {
        "status": "ready",
        "implementation_plan": [
            {
                "requirement_index": 0,
                "mechanisms": [
                    {
                        "type": "state_machine",
                        "objective": "rain_state",
                        "condition_predicate": "rain_reward:is_raining",
                        "state_scope": "global",
                        "on_enter": [{"action_type": "give_item", "target": "@a", "item": "minecraft:diamond", "count": 1}]
                    },
                    {
                        "type": "state_machine",
                        "objective": "rain_state",
                        "condition_predicate": "rain_reward:is_clear",
                        "state_scope": "global",
                        "on_enter": [{"action_type": "set_score", "target": "#global", "objective": "rain_state", "score_value": 0}]
                    },
                    {
                        "type": "predicate",
                        "path": "is_raining",
                        "condition_type": "minecraft:weather_check",
                        "condition_params": {"raining": True}
                    },
                    {
                        "type": "predicate",
                        "path": "is_clear",
                        "condition_type": "minecraft:inverted",
                        "condition_params": {"term": {"condition": "minecraft:weather_check", "raining": True}}
                    }
                ]
            }
        ]
    }

    res = gen.generate(plan=plan, datapack_name="test_rain_regression", clean=True)
    sim = ScoreboardSemanticSimulator()
    findings = sim.analyze_datapack(Path(res.datapack_path))

    error_findings = [f for f in findings if f.severity == QASeverity.ERROR]
    assert len(error_findings) == 0, f"Expected clean QA, got findings: {error_findings}"


def test_8_unknown_predicate_relationships_handled_conservatively():
    """
    8. Unknown predicate relationships are not guessed from names alone;
    they are treated conservatively as independent unless defined.
    """
    # Name has 'opposite' words, but no JSON definition
    is_comp = are_predicates_complementary("demo:light", "demo:dark", None)
    assert is_comp is False, "Predicates without definitions must not be guessed from arbitrary strings"


def test_9_unrelated_mechanisms_remain_intact(tmp_path: Path):
    """
    9. Recipes, loot tables, and standard functions are unaffected by lifecycle reconciliation.
    """
    gen = DatapackGenerator(output_dir=tmp_path)
    plan = {
        "status": "ready",
        "implementation_plan": [
            {
                "requirement_index": 0,
                "mechanisms": [
                    {
                        "type": "recipe",
                        "recipe_type": "crafting_shapeless",
                        "path": "dirt_to_diamond",
                        "result_item": "minecraft:diamond",
                        "result_count": 1,
                        "ingredients": ["minecraft:dirt"]
                    },
                    {
                        "type": "loot_table",
                        "target": "entities/creeper.json",
                        "item": "minecraft:diamond",
                        "count": 1,
                        "operation": "add_pool"
                    }
                ]
            }
        ]
    }

    res = gen.generate(plan=plan, datapack_name="test_unrelated_mechanisms", clean=True)
    recipe_path = Path(res.datapack_path) / "data" / "minecraft_ai" / "recipe" / "dirt_to_diamond.json"
    loot_path = Path(res.datapack_path) / "data" / "minecraft" / "loot_table" / "entities" / "creeper.json"
    assert recipe_path.exists()
    assert loot_path.exists()


def test_10_repeated_failed_repairs_halt_safely():
    """
    10. When no deterministic repair is applicable, QARepairEngine sets regenerate=False
    and stops safely without looping.
    """
    finding = QAFinding(
        id="UNKNOWN_UNSUPPORTED_ERROR",
        severity=QASeverity.ERROR,
        category=QACategory.COMMAND_SEMANTICS,
        file="data/demo/function/tick.mcfunction",
        line_or_reference="Line 1: unknown",
        problem="Completely unrepairable semantic failure.",
        explanation="Unrecognized error",
        expected_behavior="Valid commands",
        repair_required="Manual inspection"
    )
    qa_result = QAResult(
        status="failed",
        summary="Unrepairable error",
        findings=[finding]
    )

    plan = {
        "status": "ready",
        "implementation_plan": [{"requirement_index": 0, "mechanisms": []}]
    }

    engine = QARepairEngine(ai_provider=object())
    repair_plan, _ = engine.diagnose_and_repair(qa_result, plan)

    # Must abort cleanly without regenerate=True
    assert repair_plan.regenerate is False
    assert "no deterministic repair available" in repair_plan.summary.lower()
