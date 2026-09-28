"""
test_step17_planner.py - Step 17.3 Planner Integration Test Suite

Validates that the Planner consumes the structured semantic property-modification
contract (PropertyModification, SemanticNumericValue, SemanticValue) and converts it
into appropriate structured planning representations without command syntax or amplifier
calculations.

Covers all 15 required scenarios + backward compatibility:
1. 10 times faster
2. 10x faster
3. increase speed by 5
4. increase speed by 25%
5. set attack damage to 10
6. increase attack damage by 5
7. make the zombie's attack damage 2x
8. qualitative make me faster
9. missing property make the zombie stronger
10. missing value increase speed
11. ambiguous make me faster by 10
12. compound request containing numeric modification + unrelated action
13. semantic information is not flattened/lost
14. multiplier does not become effect amplifier 9
15. Planner does not emit raw Minecraft commands from the semantic layer
16. Backward compatibility with existing Step 16 planner behavior
"""

import unittest
from ai.planner import MinecraftPlanner, create_plan, validate_plan_mechanisms
from ai.numeric_interpreter import NumericSemanticInterpreter
from ai.semantic_models import (
    PropertyModification,
    SemanticNumericValue,
    SemanticValue,
)
from generator.models import (
    ActionSpecification,
    MechanismSpecification,
    ScoreboardObjectiveDefinition,
    validate_mechanism_specification,
)


class TestStep17Planner(unittest.TestCase):
    """
    Step 17.3 Comprehensive Test Suite for Planner Semantic Property Modification Integration.
    """

    def setUp(self):
        self.planner = MinecraftPlanner(version="1.21.11")
        self.interpreter = NumericSemanticInterpreter()

    # 1. 10 times faster
    def test_01_ten_times_faster(self):
        mod = self.interpreter.interpret("make me 10 times faster")
        plan = self.planner.plan_property_modification(mod)

        self.assertIsNotNone(plan.property_modification)
        self.assertEqual(plan.property_modification.property, "speed")
        self.assertEqual(plan.property_modification.operation, "multiply")
        self.assertEqual(plan.property_modification.value.kind, "multiplier")
        self.assertEqual(plan.property_modification.value.value, 10)

        # Mechanism and action checks
        self.assertEqual(len(plan.mechanisms), 1)
        mech = plan.mechanisms[0]
        self.assertEqual(mech.type, "property_modification")
        self.assertEqual(mech.implementation, "attribute")
        self.assertEqual(len(mech.actions), 1)
        act = mech.actions[0]
        self.assertEqual(act.action_type, "modify_property")
        self.assertEqual(act.implementation, "attribute")
        validate_mechanism_specification(mech)

        # End-to-end plan via understanding
        full_plan = self.planner.plan({"understood_request": "make me 10 times faster", "status": "understood"})
        self.assertEqual(full_plan["status"], "ready")
        self.assertEqual(len(full_plan["implementation_plan"]), 1)
        validate_plan_mechanisms(full_plan)

    # 2. 10x faster
    def test_02_ten_x_faster(self):
        mod = self.interpreter.interpret("make me 10x faster")
        plan = self.planner.plan_property_modification(mod)
        self.assertEqual(plan.property_modification.value.kind, "multiplier")
        self.assertEqual(plan.property_modification.value.value, 10)
        self.assertEqual(plan.mechanisms[0].implementation, "attribute")

    # 3. increase speed by 5
    def test_03_increase_speed_by_5(self):
        mod = self.interpreter.interpret("increase speed by 5")
        plan = self.planner.plan_property_modification(mod)
        self.assertEqual(plan.property_modification.property, "speed")
        self.assertEqual(plan.property_modification.operation, "add")
        self.assertEqual(plan.property_modification.value.kind, "relative")
        self.assertEqual(plan.property_modification.value.value, 5)
        self.assertEqual(plan.mechanisms[0].implementation, "attribute")

    # 4. increase speed by 25%
    def test_04_increase_speed_by_25_percent(self):
        mod = self.interpreter.interpret("increase speed by 25%")
        plan = self.planner.plan_property_modification(mod)
        self.assertEqual(plan.property_modification.property, "speed")
        self.assertEqual(plan.property_modification.operation, "add")
        self.assertEqual(plan.property_modification.value.kind, "percentage")
        self.assertEqual(plan.property_modification.value.value, 25)
        self.assertEqual(plan.property_modification.value.unit, "%")

    # 5. set attack damage to 10
    def test_05_set_attack_damage_to_10(self):
        mod = self.interpreter.interpret("set attack damage to 10")
        plan = self.planner.plan_property_modification(mod)
        self.assertEqual(plan.property_modification.property, "attack_damage")
        self.assertEqual(plan.property_modification.operation, "set")
        self.assertEqual(plan.property_modification.value.kind, "absolute")
        self.assertEqual(plan.property_modification.value.value, 10)
        self.assertEqual(plan.mechanisms[0].implementation, "attribute")

    # 6. increase attack damage by 5
    def test_06_increase_attack_damage_by_5(self):
        mod = self.interpreter.interpret("increase attack damage by 5")
        plan = self.planner.plan_property_modification(mod)
        self.assertEqual(plan.property_modification.property, "attack_damage")
        self.assertEqual(plan.property_modification.operation, "add")
        self.assertEqual(plan.property_modification.value.kind, "relative")
        self.assertEqual(plan.property_modification.value.value, 5)
        self.assertEqual(plan.mechanisms[0].implementation, "attribute")

    # 7. make the zombie's attack damage 2x
    def test_07_zombie_attack_damage_2x(self):
        mod = self.interpreter.interpret("make zombie attack damage 2x")
        plan = self.planner.plan_property_modification(mod)
        self.assertEqual(plan.property_modification.property, "attack_damage")
        self.assertEqual(plan.property_modification.operation, "multiply")
        self.assertEqual(plan.property_modification.value.kind, "multiplier")
        self.assertEqual(plan.property_modification.value.value, 2)
        self.assertEqual(plan.mechanisms[0].target, "@e[type=zombie]")
        self.assertEqual(plan.mechanisms[0].implementation, "attribute")

    # 8. qualitative make me faster
    def test_08_qualitative_make_me_faster(self):
        mod = self.interpreter.interpret("make me faster")
        plan = self.planner.plan_property_modification(mod)
        self.assertEqual(plan.property_modification.property, "speed")
        self.assertEqual(plan.property_modification.value.kind, "qualitative")
        self.assertEqual(plan.property_modification.value.value, "faster")
        self.assertIsNone(plan.mechanisms[0].implementation)

    # 9. missing property make the zombie stronger
    def test_09_missing_property_make_zombie_stronger(self):
        mod = self.interpreter.interpret("make the zombie stronger")
        self.assertIn("property", mod.missing)
        self.assertIsNone(mod.property)

        plan_entry = self.planner.plan_property_modification(mod)
        self.assertIsNone(plan_entry.mechanisms[0].implementation)

        # Full planner execution should identify missing property and set needs_clarification
        result = self.planner.plan({"understood_request": "make the zombie stronger", "status": "understood"})
        self.assertEqual(result["status"], "needs_clarification")
        self.assertTrue(len(result["clarifications"]) > 0)
        self.assertTrue(any("property" in c.lower() or "zombie" in c.lower() for c in result["clarifications"]))

    # 10. missing value increase speed
    def test_10_missing_value_increase_speed(self):
        mod = self.interpreter.interpret("increase speed")
        self.assertIn("value", mod.missing)
        self.assertIsNone(mod.value)

        plan_entry = self.planner.plan_property_modification(mod)
        self.assertIsNone(plan_entry.mechanisms[0].implementation)

        result = self.planner.plan({"understood_request": "increase speed", "status": "understood"})
        self.assertEqual(result["status"], "needs_clarification")
        self.assertTrue(len(result["clarifications"]) > 0)
        self.assertTrue(any("speed" in c.lower() or "amount" in c.lower() for c in result["clarifications"]))

    # 11. ambiguous make me faster by 10
    def test_11_ambiguous_make_me_faster_by_10(self):
        mod = self.interpreter.interpret("make me faster by 10")
        self.assertTrue(mod.extra_metadata.get("ambiguous"))
        self.assertIn("value", mod.missing)

        result = self.planner.plan({"understood_request": "make me faster by 10", "status": "understood"})
        self.assertEqual(result["status"], "needs_clarification")
        self.assertTrue(any("ambiguous" in c.lower() for c in result["clarifications"]))

    # 12. compound request containing numeric modification + unrelated action
    def test_12_compound_request_preserves_both(self):
        req = "make me 10 times faster and give me a netherite sword"
        result = self.planner.plan({"understood_request": req, "status": "understood"})

        self.assertEqual(result["status"], "ready")
        self.assertEqual(len(result["implementation_plan"]), 2)

        # Requirement 0: property modification
        plan_0 = result["implementation_plan"][0]
        self.assertIn("property_modification", plan_0)
        pm = plan_0["property_modification"]
        self.assertEqual(pm["property"], "speed")
        self.assertEqual(pm["operation"], "multiply")
        self.assertEqual(pm["value"]["value"], 10)

        # Requirement 1: unrelated action
        plan_1 = result["implementation_plan"][1]
        self.assertTrue(len(plan_1["mechanisms"]) > 0)
        self.assertTrue(
            any("sword" in str(m) for m in plan_1["mechanisms"])
            or "sword" in plan_1["objective"].lower()
        )

    # 13. semantic information is not flattened/lost
    def test_13_semantic_information_structured_not_flattened(self):
        mod = PropertyModification(
            property="attack_damage",
            operation="multiply",
            value=SemanticNumericValue(kind="multiplier", value=3),
            source_text="triple attack damage",
            extra_metadata={"target": "zombie", "custom_tag": "boss_mob"},
        )
        plan = self.planner.plan_property_modification(mod)

        # Check structured integrity
        pm = plan.property_modification
        self.assertEqual(pm.property, "attack_damage")
        self.assertEqual(pm.operation, "multiply")
        self.assertEqual(pm.value.kind, "multiplier")
        self.assertEqual(pm.value.value, 3)
        self.assertEqual(pm.source_text, "triple attack damage")
        self.assertEqual(pm.extra_metadata["custom_tag"], "boss_mob")

        # Mechanism also holds structured object
        mech_pm = plan.mechanisms[0].property_modification
        self.assertEqual(mech_pm.property, "attack_damage")
        self.assertEqual(mech_pm.value.value, 3)

    # 14. multiplier does not become effect amplifier 9
    def test_14_multiplier_not_converted_to_amplifier_9(self):
        mod = self.interpreter.interpret("make me 10 times faster")
        plan = self.planner.plan_property_modification(mod)

        # Value must remain 10
        self.assertEqual(plan.property_modification.value.value, 10)

        # Mechanism action must not have amplifier 9
        action = plan.mechanisms[0].actions[0]
        self.assertNotEqual(action.amplifier, 9)
        self.assertEqual(action.property_modification.value.value, 10)

        # Complete dictionary dump must not have amplifier=9
        plan_dict = plan.model_dump()
        self.assertNotIn("amplifier", str(plan_dict.get("property_modification", {})))

    # 15. Planner does not emit raw Minecraft commands from the semantic layer
    def test_15_planner_does_not_emit_raw_commands(self):
        mod = self.interpreter.interpret("make me 10 times faster")
        plan = self.planner.plan_property_modification(mod)

        # Ensure mechanisms and actions have no raw commands
        mech = plan.mechanisms[0]
        self.assertEqual(mech.commands, [])
        plan_str = str(plan.model_dump()).lower()
        self.assertNotIn("effect give", plan_str)
        self.assertNotIn("/effect", plan_str)
        self.assertNotIn("attribute @", plan_str)
        self.assertNotIn("/attribute", plan_str)

    # 16. Backward compatibility with existing Step 16 planner behavior
    def test_16_backward_compatibility_step16_scoreboard_planning(self):
        # Scoreboard objective mechanism continues to validate
        obj_mech = MechanismSpecification(
            type="scoreboard_objective",
            objective="player_deaths",
            criteria="deathCount",
            display_slot="sidebar",
        )
        validate_mechanism_specification(obj_mech)

        # Score action continues to validate
        score_act = ActionSpecification(
            action_type="set_score",
            target="#global",
            objective="timer",
            score_value=0,
        )
        self.assertEqual(score_act.action_type, "set_score")
        self.assertEqual(score_act.score_value, 0)

        # Full plan validation on standard mechanism
        full_plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "Track deaths",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Track deaths",
                    "mechanisms": [obj_mech.model_dump()],
                    "steps": [],
                    "constraints": [],
                    "missing_knowledge": [],
                }
            ],
            "missing_knowledge": [],
            "clarifications": [],
        }
        validate_plan_mechanisms(full_plan)

    # 17. Blocker 1: PropertyModification without extra_metadata does not crash planner
    def test_17_extra_metadata_contract_no_crash(self):
        mod = PropertyModification(
            property="speed",
            operation="multiply",
            value=SemanticNumericValue(kind="multiplier", value=2)
        )
        plan = self.planner.plan_property_modification(mod)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.property_modification.property, "speed")
        self.assertEqual(plan.mechanisms[0].implementation, "attribute")
        self.assertEqual(plan.property_modification.extra_metadata, {})

    # 18. Blocker 2: Missing operation halts at clarification and does not silently default to 'set'
    def test_18_missing_operation_requires_clarification(self):
        mod = PropertyModification(
            property="attack_damage",
            operation=None,
            value=SemanticNumericValue(kind="absolute", value=10),
            missing=["operation"]
        )
        plan_entry = self.planner.plan_property_modification(mod)
        self.assertIsNone(plan_entry.mechanisms[0].implementation)
        self.assertNotIn("set attack_damage", plan_entry.objective.lower())

        # Full planner execution should request clarification for missing operation
        result = self.planner.plan(
            {"understood_request": "modify attack damage by 10", "status": "understood"},
            property_modifications=[mod]
        )
        self.assertEqual(result["status"], "needs_clarification")
        self.assertTrue(len(result["clarifications"]) > 0)
        self.assertTrue(any("how" in c.lower() or "operation" in c.lower() or "modified" in c.lower() for c in result["clarifications"]))

    # 19. Blocker 3: Unknown property is not silently guessed as attribute
    def test_19_unknown_property_not_guessed_as_attribute(self):
        mod = PropertyModification(
            property="unknown_property",
            operation="set",
            value=SemanticNumericValue(kind="absolute", value=10)
        )
        plan_entry = self.planner.plan_property_modification(mod)
        # Must NOT be 'attribute'
        self.assertIsNone(plan_entry.mechanisms[0].implementation)
        self.assertIn("unknown_property", plan_entry.missing_knowledge)

        result = self.planner.plan(
            {"understood_request": "set unknown_property to 10", "status": "understood"},
            property_modifications=[mod]
        )
        self.assertEqual(result["status"], "needs_clarification")
        self.assertTrue(any("unknown_property" in c or "not recognized" in c for c in result["clarifications"]))

    # 20. Blocker 4: Compound request with generic bow item
    def test_20_compound_request_with_bow(self):
        req = "make me 10 times faster and give me a bow"
        result = self.planner.plan({"understood_request": req, "status": "understood"})

        self.assertEqual(result["status"], "ready")
        self.assertEqual(len(result["implementation_plan"]), 2)

        # Plan 0: speed modification
        plan_0 = result["implementation_plan"][0]
        self.assertEqual(plan_0["property_modification"]["property"], "speed")
        self.assertEqual(plan_0["property_modification"]["value"]["value"], 10)

        # Plan 1: bow item action
        plan_1 = result["implementation_plan"][1]
        self.assertTrue(len(plan_1["mechanisms"]) > 0)
        action = plan_1["mechanisms"][0]["actions"][0]
        self.assertEqual(action["action_type"], "give_item")
        self.assertEqual(action["item"], "minecraft:bow")

    # 21. Blocker 4: Compound request with summon entity
    def test_21_compound_request_with_summon(self):
        req = "make me 10 times faster and summon a zombie"
        result = self.planner.plan({"understood_request": req, "status": "understood"})

        self.assertEqual(result["status"], "ready")
        self.assertEqual(len(result["implementation_plan"]), 2)

        # Plan 0: speed modification
        plan_0 = result["implementation_plan"][0]
        self.assertEqual(plan_0["property_modification"]["property"], "speed")

        # Plan 1: summon zombie action
        plan_1 = result["implementation_plan"][1]
        self.assertTrue(len(plan_1["mechanisms"]) > 0)
        action = plan_1["mechanisms"][0]["actions"][0]
        self.assertEqual(action["action_type"], "summon_entity")
        self.assertEqual(action["entity"], "minecraft:zombie")


if __name__ == "__main__":
    unittest.main()
