"""
test_step17_mapper.py - Step 17.5 Deterministic Minecraft Implementation Mapping Test Suite

Validates that ImplementationMapper converts structured, validated PropertyModification
models into deterministic Minecraft implementation specifications using the authoritative
PropertyCapabilityRegistry.

Covers all 22 required scenarios:
1. speed ×10 multiplier
2. speed +5 relative
3. speed -5 relative
4. speed +25% percentage
5. speed ×2 multiplier
6. absolute speed value where supported
7. qualitative speed
8. attack damage set absolute
9. attack damage add relative
10. attack damage percentage
11. unknown property
12. missing operation
13. missing value
14. missing target
15. unsupported mechanism request
16. compound request preservation
17. registry is the only capability source
18. mapper contains no duplicate capability table
19. no raw Minecraft commands in ai/
20. generator does not invent duration
21. generator does not convert multiplier to amplifier
22. generator does not convert relative values to absolute effect levels
"""

import unittest
import inspect
from ai.implementation_mapper import ImplementationMapper, MappedImplementation
from ai.semantic_models import (
    PropertyModification,
    SemanticNumericValue,
    SemanticValue,
)
from ai.property_registry import (
    DEFAULT_PROPERTY_REGISTRY,
    PropertyCapability,
    PropertyCapabilityRegistry,
    MechanismCapability,
)
from ai.planner import MinecraftPlanner
from ai.numeric_interpreter import NumericSemanticInterpreter
from generator.mechanisms.function_mech import FunctionMechanismGenerator
from generator.models import ActionSpecification


class TestStep17ImplementationMapper(unittest.TestCase):
    """
    Step 17.5 Comprehensive Test Suite for Deterministic Minecraft Implementation Mapping.
    """

    def setUp(self):
        self.mapper = ImplementationMapper(registry=DEFAULT_PROPERTY_REGISTRY)
        self.planner = MinecraftPlanner(version="1.21.11")
        self.interpreter = NumericSemanticInterpreter()
        self.generator = FunctionMechanismGenerator(version="1.21.11")

    # 1. speed ×10 multiplier
    def test_01_speed_multiply_10_multiplier(self):
        mod = PropertyModification(
            property="speed",
            operation="multiply",
            value=SemanticNumericValue(kind="multiplier", value=10),
            extra_metadata={"target": "player"},
        )
        res = self.mapper.map_modification(mod)

        self.assertEqual(res.status, "ready")
        self.assertEqual(res.property_name, "speed")
        self.assertEqual(res.target, "@a")
        self.assertEqual(res.mechanism_type, "attribute")
        self.assertEqual(res.minecraft_identifier, "minecraft:generic.movement_speed")
        self.assertEqual(res.operation, "multiply")
        self.assertEqual(res.value.kind, "multiplier")
        self.assertEqual(res.value.value, 10)
        self.assertIsNotNone(res.mechanism_spec)
        self.assertIsNotNone(res.action_spec)

        # Synthesized command uses add_multiplied_total with amount 10 - 1 = 9.0
        cmd = self.generator.synthesize_action(res.action_spec)
        self.assertEqual(
            cmd,
            "execute as @a run attribute @s minecraft:generic.movement_speed modifier add minecraft_ai:speed_mult_10 9.0 add_multiplied_total"
        )
        self.assertNotIn("effect give", cmd)

    # 2. speed +5 relative
    def test_02_speed_add_5_relative(self):
        mod = PropertyModification(
            property="speed",
            operation="add",
            value=SemanticNumericValue(kind="relative", value=5),
            extra_metadata={"target": "player"},
        )
        res = self.mapper.map_modification(mod)

        self.assertEqual(res.status, "ready")
        self.assertEqual(res.property_name, "speed")
        self.assertEqual(res.mechanism_type, "attribute")
        self.assertEqual(res.minecraft_identifier, "minecraft:generic.movement_speed")
        self.assertEqual(res.operation, "add")
        self.assertEqual(res.value.kind, "relative")
        self.assertEqual(res.value.value, 5)

        # Synthesized command uses add_value
        cmd = self.generator.synthesize_action(res.action_spec)
        self.assertEqual(
            cmd,
            "execute as @a run attribute @s minecraft:generic.movement_speed modifier add minecraft_ai:speed_add_5 5.0 add_value"
        )
        self.assertNotIn("effect give", cmd)

    # 3. speed -5 relative
    def test_03_speed_subtract_5_relative(self):
        mod = PropertyModification(
            property="speed",
            operation="subtract",
            value=SemanticNumericValue(kind="relative", value=5),
            extra_metadata={"target": "player"},
        )
        res = self.mapper.map_modification(mod)

        self.assertEqual(res.status, "ready")
        self.assertEqual(res.mechanism_type, "attribute")
        self.assertEqual(res.operation, "subtract")
        self.assertEqual(res.value.kind, "relative")
        self.assertEqual(res.value.value, 5)

        cmd = self.generator.synthesize_action(res.action_spec)
        self.assertEqual(
            cmd,
            "execute as @a run attribute @s minecraft:generic.movement_speed modifier add minecraft_ai:speed_sub_5 -5.0 add_value"
        )

    # 4. speed +25% percentage
    def test_04_speed_add_25_percentage(self):
        mod = PropertyModification(
            property="speed",
            operation="add",
            value=SemanticNumericValue(kind="percentage", value=25, unit="%"),
            extra_metadata={"target": "player"},
        )
        res = self.mapper.map_modification(mod)

        self.assertEqual(res.status, "ready")
        self.assertEqual(res.mechanism_type, "attribute")
        self.assertEqual(res.operation, "add")
        self.assertEqual(res.value.kind, "percentage")
        self.assertEqual(res.value.value, 25)

        # 25% translates to 0.25 fractional modifier with add_multiplied_base
        cmd = self.generator.synthesize_action(res.action_spec)
        self.assertEqual(
            cmd,
            "execute as @a run attribute @s minecraft:generic.movement_speed modifier add minecraft_ai:speed_add_pct_25 0.25 add_multiplied_base"
        )

    # 5. speed ×2 multiplier
    def test_05_speed_multiply_2_multiplier(self):
        mod = PropertyModification(
            property="speed",
            operation="multiply",
            value=SemanticNumericValue(kind="multiplier", value=2),
            extra_metadata={"target": "player"},
        )
        res = self.mapper.map_modification(mod)

        self.assertEqual(res.status, "ready")
        self.assertEqual(res.mechanism_type, "attribute")
        self.assertEqual(res.value.value, 2)

        # Multiplier 2 translates to amount 2 - 1 = 1.0
        cmd = self.generator.synthesize_action(res.action_spec)
        self.assertEqual(
            cmd,
            "execute as @a run attribute @s minecraft:generic.movement_speed modifier add minecraft_ai:speed_mult_2 1.0 add_multiplied_total"
        )

    # 6. absolute speed value where supported
    def test_06_absolute_speed_value_where_supported(self):
        mod = PropertyModification(
            property="speed",
            operation="set",
            value=SemanticNumericValue(kind="absolute", value=0.2),
            extra_metadata={"target": "player"},
        )
        res = self.mapper.map_modification(mod)

        self.assertEqual(res.status, "ready")
        self.assertEqual(res.mechanism_type, "attribute")
        self.assertEqual(res.value.kind, "absolute")
        self.assertEqual(res.value.value, 0.2)

        cmd = self.generator.synthesize_action(res.action_spec)
        self.assertEqual(
            cmd,
            "execute as @a run attribute @s minecraft:generic.movement_speed base set 0.2"
        )

    # 7. qualitative speed
    def test_07_qualitative_speed(self):
        mod = PropertyModification(
            property="speed",
            operation=None,
            value=SemanticValue(kind="qualitative", value="faster"),
            extra_metadata={"target": "player"},
        )
        res = self.mapper.map_modification(mod)

        # Mapper marks unresolved without guessing magnitude or duration
        self.assertEqual(res.status, "unresolved")
        self.assertEqual(res.property_name, "speed")
        self.assertIsNone(res.operation)
        self.assertEqual(res.value.kind, "qualitative")
        self.assertEqual(res.value.value, "faster")
        self.assertIn("clarification", res.reason.lower())

        # If a qualitative action reaches generator, generator fails structurally
        action = ActionSpecification(
            action_type="modify_property",
            target="@a",
            property_modification=mod,
            implementation="effect",
        )
        cmd = self.generator.synthesize_action(action)
        self.assertIsNone(cmd)

    # 8. attack damage set absolute
    def test_08_attack_damage_set_absolute(self):
        mod = PropertyModification(
            property="attack_damage",
            operation="set",
            value=SemanticNumericValue(kind="absolute", value=10),
            extra_metadata={"target": "zombie"},
        )
        res = self.mapper.map_modification(mod)

        self.assertEqual(res.status, "ready")
        self.assertEqual(res.property_name, "attack_damage")
        self.assertEqual(res.target, "@e[type=zombie]")
        self.assertEqual(res.mechanism_type, "attribute")
        self.assertEqual(res.minecraft_identifier, "minecraft:generic.attack_damage")
        self.assertEqual(res.operation, "set")
        self.assertEqual(res.value.kind, "absolute")
        self.assertEqual(res.value.value, 10)

        cmd = self.generator.synthesize_action(res.action_spec)
        self.assertEqual(
            cmd,
            "execute as @e[type=zombie] run attribute @s minecraft:generic.attack_damage base set 10"
        )

    # 9. attack damage add relative
    def test_09_attack_damage_add_relative(self):
        mod = PropertyModification(
            property="attack_damage",
            operation="add",
            value=SemanticNumericValue(kind="relative", value=5),
            extra_metadata={"target": "player"},
        )
        res = self.mapper.map_modification(mod)

        self.assertEqual(res.status, "ready")
        self.assertEqual(res.mechanism_type, "attribute")
        self.assertEqual(res.minecraft_identifier, "minecraft:generic.attack_damage")

        cmd = self.generator.synthesize_action(res.action_spec)
        self.assertEqual(
            cmd,
            "execute as @a run attribute @s minecraft:generic.attack_damage modifier add minecraft_ai:attack_damage_add_5 5.0 add_value"
        )

    # 10. attack damage percentage
    def test_10_attack_damage_percentage(self):
        mod = PropertyModification(
            property="attack_damage",
            operation="add",
            value=SemanticNumericValue(kind="percentage", value=20, unit="%"),
            extra_metadata={"target": "player"},
        )
        res = self.mapper.map_modification(mod)

        self.assertEqual(res.status, "ready")
        self.assertEqual(res.mechanism_type, "attribute")

        cmd = self.generator.synthesize_action(res.action_spec)
        self.assertEqual(
            cmd,
            "execute as @a run attribute @s minecraft:generic.attack_damage modifier add minecraft_ai:attack_damage_add_pct_20 0.2 add_multiplied_base"
        )

    # 11. unknown property
    def test_11_unknown_property(self):
        mod = PropertyModification(
            property="mana",
            operation="set",
            value=SemanticNumericValue(kind="absolute", value=10),
            extra_metadata={"target": "player"},
        )
        res = self.mapper.map_modification(mod)

        self.assertEqual(res.status, "unresolved")
        self.assertIn("mana", res.missing_knowledge)
        self.assertIsNone(res.mechanism_spec)
        self.assertIsNone(res.action_spec)

    # 12. missing operation
    def test_12_missing_operation(self):
        mod = PropertyModification(
            property="speed",
            operation=None,
            value=SemanticNumericValue(kind="absolute", value=10),
            missing=["operation"],
            extra_metadata={"target": "player"},
        )
        res = self.mapper.map_modification(mod)

        self.assertEqual(res.status, "unresolved")
        self.assertIn("operation", res.missing)
        self.assertIsNone(res.mechanism_spec)

    # 13. missing value
    def test_13_missing_value(self):
        mod = PropertyModification(
            property="speed",
            operation="add",
            value=None,
            missing=["value"],
            extra_metadata={"target": "player"},
        )
        res = self.mapper.map_modification(mod)

        self.assertEqual(res.status, "unresolved")
        self.assertIn("value", res.missing)
        self.assertIsNone(res.mechanism_spec)

    # 14. missing target
    def test_14_missing_target(self):
        mod = PropertyModification(
            property="speed",
            operation="multiply",
            value=SemanticNumericValue(kind="multiplier", value=10),
        )
        res = self.mapper.map_modification(mod)

        self.assertEqual(res.status, "unresolved")
        self.assertIn("target", res.missing)
        self.assertIn("missing", res.reason.lower())

    # 15. unsupported mechanism request
    def test_15_unsupported_mechanism_request(self):
        mod = PropertyModification(
            property="attack_damage",
            operation="set",
            value=SemanticNumericValue(kind="absolute", value=10),
            extra_metadata={"target": "player"},
        )
        res = self.mapper.map_modification(mod, preferred_mechanism="scoreboard")

        self.assertEqual(res.status, "unsupported")
        self.assertIn("not supported", res.reason.lower())
        self.assertIsNone(res.mechanism_spec)

    # 16. compound request preservation
    def test_16_compound_request_preservation(self):
        req_text = "make me 10 times faster and make the zombie stronger"
        plan_result = self.planner.plan({"understood_request": req_text, "status": "understood"})

        self.assertEqual(plan_result["status"], "needs_clarification")
        self.assertEqual(len(plan_result["implementation_plan"]), 2)

        # Plan 0 (speed x10) is fully ready and mapped to attribute
        plan_0 = plan_result["implementation_plan"][0]
        self.assertEqual(plan_0["property_modification"]["property"], "speed")
        self.assertEqual(plan_0["mechanisms"][0]["implementation"], "attribute")
        self.assertEqual(plan_0["property_modification"]["value"]["value"], 10)
        self.assertEqual(plan_0.get("clarifications", []), [])

        # Plan 1 (zombie stronger) is unresolved (missing property)
        plan_1 = plan_result["implementation_plan"][1]
        self.assertIsNone(plan_1["mechanisms"][0]["implementation"])
        self.assertTrue(len(plan_1.get("clarification_requirements", [])) > 0)

    # 17. registry is the only capability source
    def test_17_registry_is_the_only_capability_source(self):
        custom_reg = PropertyCapabilityRegistry()
        custom_reg.register(
            PropertyCapability(
                property_name="stamina",
                primary_mechanism="attribute",
                supported_mechanisms=["attribute"],
                minecraft_identifier="minecraft:generic.stamina",
                description="Custom stamina attribute",
                mechanisms={
                    "attribute": MechanismCapability(
                        mechanism_type="attribute",
                        minecraft_identifier="minecraft:generic.stamina",
                        supported_operations=["set"],
                        supported_value_kinds=["absolute"],
                        operation_value_kinds={"set": ["absolute"]},
                    )
                }
            )
        )

        mod = PropertyModification(
            property="stamina",
            operation="set",
            value=SemanticNumericValue(kind="absolute", value=100),
            extra_metadata={"target": "player"},
        )
        res = self.mapper.map_modification(mod, registry=custom_reg)

        self.assertEqual(res.status, "ready")
        self.assertEqual(res.property_name, "stamina")
        self.assertEqual(res.mechanism_type, "attribute")
        self.assertEqual(res.minecraft_identifier, "minecraft:generic.stamina")

    # 18. mapper contains no duplicate capability table
    def test_18_mapper_contains_no_duplicate_capability_table(self):
        import ai.implementation_mapper as mapper_mod

        source = inspect.getsource(mapper_mod)
        # Ensure no duplicate dictionary mapping properties to mechanisms
        self.assertNotIn("PROPERTY_TO_MECHANISM", source)
        self.assertNotIn("PROPERTIES =", source)
        self.assertNotIn('"speed": "effect"', source)
        self.assertNotIn('"attack_damage": "attribute"', source)

    # 19. no raw Minecraft commands in ai/
    def test_19_no_raw_minecraft_commands_in_ai_layer(self):
        mod = PropertyModification(
            property="speed",
            operation="multiply",
            value=SemanticNumericValue(kind="multiplier", value=10),
            extra_metadata={"target": "player"},
        )
        res = self.mapper.map_modification(mod)

        # Check that no command strings leak into MappedImplementation fields
        dumped = res.model_dump()
        dump_str = str(dumped)
        self.assertNotIn("/effect", dump_str)
        self.assertNotIn("/attribute", dump_str)
        self.assertNotIn("/scoreboard", dump_str)
        self.assertNotIn("effect give", dump_str)
        self.assertNotIn("attribute @", dump_str)

        # Check planner plan as well
        plan = self.planner.plan_property_modification(mod)
        plan_str = str(plan.model_dump())
        self.assertNotIn("/effect", plan_str)
        self.assertNotIn("/attribute", plan_str)
        self.assertNotIn("/scoreboard", plan_str)
        self.assertNotIn("effect give", plan_str)
        self.assertNotIn("attribute @", plan_str)

    # 20. generator does not invent duration
    def test_20_generator_does_not_invent_duration(self):
        mod = PropertyModification(
            property="speed",
            operation="set",
            value=SemanticNumericValue(kind="absolute", value=1),
        )
        # Effect action without explicit duration must fail structurally (None)
        act = ActionSpecification(
            action_type="modify_property",
            target="@a",
            property_modification=mod,
            implementation="effect",
            duration=None,
        )
        cmd = self.generator.synthesize_action(act)
        self.assertIsNone(cmd)

        # With explicit duration, generator synthesizes properly
        act.duration = 15
        cmd_with_dur = self.generator.synthesize_action(act)
        self.assertIsNotNone(cmd_with_dur)
        self.assertIn("15", cmd_with_dur)

    # 21. generator does not convert multiplier to amplifier
    def test_21_generator_does_not_convert_multiplier_to_amplifier(self):
        mod = PropertyModification(
            property="speed",
            operation="multiply",
            value=SemanticNumericValue(kind="multiplier", value=10),
            extra_metadata={"duration": 30},
        )
        # If an effect action is provided with multiplier semantics, it must fail structurally
        act = ActionSpecification(
            action_type="modify_property",
            target="@a",
            property_modification=mod,
            implementation="effect",
            duration=30,
        )
        cmd = self.generator.synthesize_action(act)
        self.assertIsNone(cmd)

    # 22. generator does not convert relative values to absolute effect levels
    def test_22_generator_does_not_convert_relative_to_absolute_effect_levels(self):
        mod = PropertyModification(
            property="speed",
            operation="add",
            value=SemanticNumericValue(kind="relative", value=5),
            extra_metadata={"duration": 30},
        )
        # If an effect action is provided with relative semantics, it must fail structurally
        act = ActionSpecification(
            action_type="modify_property",
            target="@a",
            property_modification=mod,
            implementation="effect",
            duration=30,
        )
        cmd = self.generator.synthesize_action(act)
        self.assertIsNone(cmd)

    # 23. Blocker 1: 'make me 5 faster' comparative numeric semantics end-to-end
    def test_23_comparative_numeric_make_me_5_faster_end_to_end(self):
        from ai.numeric_interpreter import NumericSemanticInterpreter
        interp = NumericSemanticInterpreter()
        mod = interp.interpret("make me 5 faster")

        self.assertEqual(mod.property, "speed")
        self.assertEqual(mod.operation, "add")
        self.assertEqual(mod.value.kind, "relative")
        self.assertEqual(mod.value.value, 5)

        res = self.mapper.map_modification(mod)
        self.assertEqual(res.status, "ready")
        self.assertEqual(res.mechanism_type, "attribute")

        cmd = self.generator.synthesize_action(res.action_spec)
        self.assertEqual(
            cmd,
            "execute as @a run attribute @s minecraft:generic.movement_speed modifier add minecraft_ai:speed_add_5 5.0 add_value"
        )
        self.assertNotIn("base set 5", cmd)

    # 24. Blocker 2: Distinct deterministic modifier IDs
    def test_24_distinct_deterministic_modifier_ids(self):
        m_add5 = PropertyModification(
            property="speed",
            operation="add",
            value=SemanticNumericValue(kind="relative", value=5),
        )
        m_add2 = PropertyModification(
            property="speed",
            operation="add",
            value=SemanticNumericValue(kind="relative", value=2),
        )
        m_mul2 = PropertyModification(
            property="speed",
            operation="multiply",
            value=SemanticNumericValue(kind="multiplier", value=2),
        )
        m_mul3 = PropertyModification(
            property="speed",
            operation="multiply",
            value=SemanticNumericValue(kind="multiplier", value=3),
        )

        cmd_add5 = self.generator.synthesize_action(
            ActionSpecification(action_type="modify_property", property_modification=m_add5, target="@a")
        )
        cmd_add2 = self.generator.synthesize_action(
            ActionSpecification(action_type="modify_property", property_modification=m_add2, target="@a")
        )
        cmd_mul2 = self.generator.synthesize_action(
            ActionSpecification(action_type="modify_property", property_modification=m_mul2, target="@a")
        )
        cmd_mul3 = self.generator.synthesize_action(
            ActionSpecification(action_type="modify_property", property_modification=m_mul3, target="@a")
        )

        import re
        id_pattern = re.compile(r"modifier add\s+([^\s]+)")
        id_add5 = id_pattern.search(cmd_add5).group(1)
        id_add2 = id_pattern.search(cmd_add2).group(1)
        id_mul2 = id_pattern.search(cmd_mul2).group(1)
        id_mul3 = id_pattern.search(cmd_mul3).group(1)

        self.assertEqual(id_add5, "minecraft_ai:speed_add_5")
        self.assertEqual(id_add2, "minecraft_ai:speed_add_2")
        self.assertEqual(id_mul2, "minecraft_ai:speed_mult_2")
        self.assertEqual(id_mul3, "minecraft_ai:speed_mult_3")

        # Verify all 4 IDs are mutually distinct
        ids = {id_add5, id_add2, id_mul2, id_mul3}
        self.assertEqual(len(ids), 4)

        # Verify valid Minecraft identifier syntax (namespace:path)
        valid_mc_id = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_.-/]+$")
        for mid in ids:
            self.assertTrue(valid_mc_id.match(mid), f"Invalid Minecraft ID: {mid}")

        # Verify determinism on repeated call
        cmd_add5_second = self.generator.synthesize_action(
            ActionSpecification(action_type="modify_property", property_modification=m_add5, target="@a")
        )
        self.assertEqual(cmd_add5, cmd_add5_second)

    # 25. Blocker 2: Intentional repeated modifier identity
    def test_25_intentional_repeated_modifier_identity(self):
        m = PropertyModification(
            property="speed",
            operation="add",
            value=SemanticNumericValue(kind="relative", value=5),
        )
        act1 = ActionSpecification(
            action_type="modify_property",
            property_modification=m,
            target="@a",
            modifier_id="speed_buff_1",
        )
        act2 = ActionSpecification(
            action_type="modify_property",
            property_modification=m,
            target="@a",
            modifier_id="speed_buff_2",
        )

        cmd1 = self.generator.synthesize_action(act1)
        cmd2 = self.generator.synthesize_action(act2)

        self.assertIn("minecraft_ai:speed_buff_1", cmd1)
        self.assertIn("minecraft_ai:speed_buff_2", cmd2)
        self.assertNotEqual(cmd1, cmd2)

    # 26. Blocker 3: Target handling for @s, @a, @p
    def test_26_target_handling_single_vs_multi_entity(self):
        m = PropertyModification(
            property="speed",
            operation="add",
            value=SemanticNumericValue(kind="relative", value=5),
        )

        # @s: direct form (no execute wrapper)
        cmd_s = self.generator.synthesize_action(
            ActionSpecification(action_type="modify_property", property_modification=m, target="@s")
        )
        self.assertEqual(
            cmd_s,
            "attribute @s minecraft:generic.movement_speed modifier add minecraft_ai:speed_add_5 5.0 add_value"
        )
        self.assertFalse(cmd_s.startswith("execute "))

        # @a: execution context wrapper
        cmd_a = self.generator.synthesize_action(
            ActionSpecification(action_type="modify_property", property_modification=m, target="@a")
        )
        self.assertEqual(
            cmd_a,
            "execute as @a run attribute @s minecraft:generic.movement_speed modifier add minecraft_ai:speed_add_5 5.0 add_value"
        )

        # @p: execution context wrapper
        cmd_p = self.generator.synthesize_action(
            ActionSpecification(action_type="modify_property", property_modification=m, target="@p")
        )
        self.assertEqual(
            cmd_p,
            "execute as @p run attribute @s minecraft:generic.movement_speed modifier add minecraft_ai:speed_add_5 5.0 add_value"
        )

    # 27. Blocker 3: Entity knowledge resolution for mob target
    def test_27_target_handling_entity_knowledge_resolution(self):
        mod = PropertyModification(
            property="speed",
            operation="add",
            value=SemanticNumericValue(kind="relative", value=5),
            extra_metadata={"target": "zombie"},
        )
        res = self.mapper.map_modification(mod)

        self.assertEqual(res.status, "ready")
        self.assertEqual(res.target, "@e[type=zombie]")

        cmd = self.generator.synthesize_action(res.action_spec)
        self.assertEqual(
            cmd,
            "execute as @e[type=zombie] run attribute @s minecraft:generic.movement_speed modifier add minecraft_ai:speed_add_5 5.0 add_value"
        )
        self.assertNotIn("attribute zombie", cmd)

    # 28. Blocker 3: Unresolvable entity target fails safely
    def test_28_target_handling_unresolvable_entity_fails_safely(self):
        mod = PropertyModification(
            property="speed",
            operation="add",
            value=SemanticNumericValue(kind="relative", value=5),
            extra_metadata={"target": "flugelhorn"},
        )
        res = self.mapper.map_modification(mod)

        self.assertEqual(res.status, "unresolved")
        self.assertIn("target", res.missing)
        self.assertIn("flugelhorn", res.reason)

        # Planner propagates this unresolved status
        plan = self.planner.plan_property_modification(mod)
        self.assertTrue(len(plan.clarifications) > 0 or len(plan.missing_knowledge) > 0)

    # 29. Two identical speed x2 modifications receive distinct deterministic IDs
    def test_29_identical_multiplier_modifications_receive_distinct_ids(self):
        mod1 = PropertyModification(
            target="@a",
            property="speed",
            operation="multiply",
            value=SemanticNumericValue(kind="multiplier", value=2.0),
        )
        mod2 = PropertyModification(
            target="@a",
            property="speed",
            operation="multiply",
            value=SemanticNumericValue(kind="multiplier", value=2.0),
        )

        res1 = self.mapper.map_modification(mod1, step_id="step_0")
        res2 = self.mapper.map_modification(mod2, step_id="step_1")

        cmd1 = self.generator.synthesize_action(res1.action_spec)
        cmd2 = self.generator.synthesize_action(res2.action_spec)

        self.assertIn("minecraft_ai:speed_mult_2_step_0", cmd1)
        self.assertIn("minecraft_ai:speed_mult_2_step_1", cmd2)
        self.assertNotEqual(cmd1, cmd2)

        # Verify command validity
        self.assertEqual(
            cmd1,
            "execute as @a run attribute @s minecraft:generic.movement_speed modifier add minecraft_ai:speed_mult_2_step_0 1.0 add_multiplied_total"
        )
        self.assertEqual(
            cmd2,
            "execute as @a run attribute @s minecraft:generic.movement_speed modifier add minecraft_ai:speed_mult_2_step_1 1.0 add_multiplied_total"
        )

    # 30. Two identical speed +5 modifications receive distinct deterministic IDs
    def test_30_identical_relative_modifications_receive_distinct_ids(self):
        mod1 = PropertyModification(
            target="@a",
            property="speed",
            operation="add",
            value=SemanticNumericValue(kind="relative", value=5.0),
        )
        mod2 = PropertyModification(
            target="@a",
            property="speed",
            operation="add",
            value=SemanticNumericValue(kind="relative", value=5.0),
        )

        res1 = self.mapper.map_modification(mod1, step_id="step_0")
        res2 = self.mapper.map_modification(mod2, step_id="step_1")

        cmd1 = self.generator.synthesize_action(res1.action_spec)
        cmd2 = self.generator.synthesize_action(res2.action_spec)

        self.assertIn("minecraft_ai:speed_add_5_step_0", cmd1)
        self.assertIn("minecraft_ai:speed_add_5_step_1", cmd2)
        self.assertNotEqual(cmd1, cmd2)

        self.assertEqual(
            cmd1,
            "execute as @a run attribute @s minecraft:generic.movement_speed modifier add minecraft_ai:speed_add_5_step_0 5.0 add_value"
        )
        self.assertEqual(
            cmd2,
            "execute as @a run attribute @s minecraft:generic.movement_speed modifier add minecraft_ai:speed_add_5_step_1 5.0 add_value"
        )

    # 31. Compound request: make me 2 times faster and make me 2 times faster
    def test_31_compound_identical_modifications_planner_integration(self):
        from ai.numeric_interpreter import NumericSemanticInterpreter
        interp = NumericSemanticInterpreter()
        text = "make me 2 times faster and make me 2 times faster"
        compound = interp.interpret_compound(text)
        mods = compound.get("modifications", [])
        self.assertEqual(len(mods), 2)

        full_plan = self.planner.plan(
            {"intent": "modify_property", "understood_request": text, "status": "ready"},
            property_modifications=mods,
        )
        self.assertEqual(full_plan["status"], "ready")
        self.assertEqual(len(full_plan["implementation_plan"]), 2)

        cmds = []
        for ip in full_plan["implementation_plan"]:
            for mech in ip.get("mechanisms", []):
                for act in mech.get("actions", []):
                    action_spec = act if isinstance(act, ActionSpecification) else ActionSpecification(**act)
                    cmd = self.generator.synthesize_action(action_spec)
                    cmds.append(cmd)

        self.assertEqual(len(cmds), 2)
        self.assertNotEqual(cmds[0], cmds[1])
        self.assertIn("minecraft_ai:speed_mult_2_step_0", cmds[0])
        self.assertIn("minecraft_ai:speed_mult_2_step_1", cmds[1])

    # 32. Same action regenerated twice -> identical modifier ID (determinism)
    def test_32_same_action_regenerated_twice_deterministic(self):
        mod = PropertyModification(
            target="@a",
            property="speed",
            operation="multiply",
            value=SemanticNumericValue(kind="multiplier", value=2.0),
        )

        res_a = self.mapper.map_modification(mod, step_id="step_0")
        cmd_a = self.generator.synthesize_action(res_a.action_spec)

        res_b = self.mapper.map_modification(mod, step_id="step_0")
        cmd_b = self.generator.synthesize_action(res_b.action_spec)

        self.assertEqual(cmd_a, cmd_b)
        self.assertIn("minecraft_ai:speed_mult_2_step_0", cmd_a)

    # 33. Different action identities -> different deterministic IDs
    def test_33_different_action_identities_produce_different_ids(self):
        mod = PropertyModification(
            target="@a",
            property="speed",
            operation="add",
            value=SemanticNumericValue(kind="relative", value=5.0),
        )

        ids = set()
        for idx in range(3):
            res = self.mapper.map_modification(mod, step_id=f"step_{idx}")
            cmd = self.generator.synthesize_action(res.action_spec)
            import re
            m = re.search(r"modifier add\s+([^\s]+)", cmd)
            self.assertIsNotNone(m)
            ids.add(m.group(1))

        self.assertEqual(len(ids), 3)
        self.assertIn("minecraft_ai:speed_add_5_step_0", ids)
        self.assertIn("minecraft_ai:speed_add_5_step_1", ids)
        self.assertIn("minecraft_ai:speed_add_5_step_2", ids)

    # 34. Explicit custom modifier_id remains unchanged
    def test_34_explicit_custom_modifier_id_remains_unchanged(self):
        mod = PropertyModification(
            target="@a",
            property="speed",
            operation="add",
            value=SemanticNumericValue(kind="relative", value=5.0),
            extra_metadata={"modifier_id": "custom_override_id"},
        )

        res = self.mapper.map_modification(mod, step_id="step_0")
        cmd = self.generator.synthesize_action(res.action_spec)

        self.assertIn("minecraft_ai:custom_override_id", cmd)
        self.assertNotIn("step_0", cmd)


if __name__ == "__main__":
    unittest.main()

