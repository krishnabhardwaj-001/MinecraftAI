"""
test_step17_interpreter.py - Step 17.2 Generic Natural-Language Numeric Interpretation Test Suite

Validates the deterministic conversion of natural-language numeric expressions and
property modifications into the Step 17.1 semantic contract (PropertyModification,
SemanticValue, SemanticNumericValue).

Covers all 21 minimum requirements + Minecraft-independence checks:
1. 10 times faster
2. 10x faster
3. 2x
4. twice
5. double
6. 3 times
7. increase by 5
8. decrease by 5
9. increase by 25%
10. reduce by 50 percent
11. set to 10
12. decimal absolute value
13. decimal multiplier
14. negative relative value if supported by the contract
15. qualitative faster
16. qualitative stronger
17. missing numeric value
18. ambiguous numeric wording
19. malformed numeric wording
20. boolean rejection
21. compound request preserving numeric meaning
22. "10 times faster" semantic independence (no amplifier=9, no Minecraft command syntax)
+ additional examples from the Step 17 specification.
"""

import unittest
from ai.numeric_interpreter import (
    NumericSemanticInterpreter,
    interpret_numeric_expression,
    extract_property_modifications,
)
from ai.semantic_models import (
    PropertyModification,
    SemanticNumericValue,
    SemanticValue,
)


class TestStep17NumericInterpretation(unittest.TestCase):
    """
    Focused test suite for Step 17.2: Generic Natural-Language Numeric Interpretation.
    """

    def setUp(self):
        self.interpreter = NumericSemanticInterpreter()

    # 1. 10 times faster
    def test_01_ten_times_faster(self):
        mod = self.interpreter.interpret("make me 10 times faster")
        self.assertEqual(mod.property, "speed")
        self.assertEqual(mod.operation, "multiply")
        self.assertIsNotNone(mod.value)
        self.assertEqual(mod.value.kind, "multiplier")
        self.assertEqual(mod.value.value, 10)
        self.assertEqual(mod.missing, [])
        self.assertEqual(mod.extra_metadata.get("target"), "player")

    # 2. 10x faster
    def test_02_ten_x_faster(self):
        mod = self.interpreter.interpret("make me 10x faster")
        self.assertEqual(mod.property, "speed")
        self.assertEqual(mod.operation, "multiply")
        self.assertIsNotNone(mod.value)
        self.assertEqual(mod.value.kind, "multiplier")
        self.assertEqual(mod.value.value, 10)
        self.assertEqual(mod.missing, [])

    # 3. 2x
    def test_03_two_x(self):
        mod = self.interpreter.interpret("2x")
        self.assertIsNone(mod.property)
        self.assertIn("property", mod.missing)
        self.assertEqual(mod.operation, "multiply")
        self.assertIsNotNone(mod.value)
        self.assertEqual(mod.value.kind, "multiplier")
        self.assertEqual(mod.value.value, 2)

    # 4. twice
    def test_04_twice(self):
        mod = self.interpreter.interpret("twice")
        self.assertIsNone(mod.property)
        self.assertIn("property", mod.missing)
        self.assertEqual(mod.operation, "multiply")
        self.assertIsNotNone(mod.value)
        self.assertEqual(mod.value.kind, "multiplier")
        self.assertEqual(mod.value.value, 2)

    # 5. double
    def test_05_double(self):
        mod = self.interpreter.interpret("double")
        self.assertIsNone(mod.property)
        self.assertIn("property", mod.missing)
        self.assertEqual(mod.operation, "multiply")
        self.assertIsNotNone(mod.value)
        self.assertEqual(mod.value.kind, "multiplier")
        self.assertEqual(mod.value.value, 2)

        # Also test with target property: "double my speed"
        mod_speed = self.interpreter.interpret("double my speed")
        self.assertEqual(mod_speed.property, "speed")
        self.assertEqual(mod_speed.operation, "multiply")
        self.assertEqual(mod_speed.value.kind, "multiplier")
        self.assertEqual(mod_speed.value.value, 2)
        self.assertEqual(mod_speed.missing, [])

    # 6. 3 times
    def test_06_three_times(self):
        mod = self.interpreter.interpret("3 times")
        self.assertIsNone(mod.property)
        self.assertIn("property", mod.missing)
        self.assertEqual(mod.operation, "multiply")
        self.assertEqual(mod.value.kind, "multiplier")
        self.assertEqual(mod.value.value, 3)

        # Word number variation: "three times"
        mod_word = self.interpreter.interpret("three times")
        self.assertEqual(mod_word.operation, "multiply")
        self.assertEqual(mod_word.value.kind, "multiplier")
        self.assertEqual(mod_word.value.value, 3)

        # In context: "make speed three times higher"
        mod_ctx = self.interpreter.interpret("make speed three times higher")
        self.assertEqual(mod_ctx.property, "speed")
        self.assertEqual(mod_ctx.operation, "multiply")
        self.assertEqual(mod_ctx.value.kind, "multiplier")
        self.assertEqual(mod_ctx.value.value, 3)
        self.assertEqual(mod_ctx.missing, [])

    # 7. increase by 5
    def test_07_increase_by_5(self):
        mod = self.interpreter.interpret("increase by 5")
        self.assertIsNone(mod.property)
        self.assertIn("property", mod.missing)
        self.assertEqual(mod.operation, "add")
        self.assertIsNotNone(mod.value)
        self.assertEqual(mod.value.kind, "relative")
        self.assertEqual(mod.value.value, 5)

    # 8. decrease by 5
    def test_08_decrease_by_5(self):
        mod = self.interpreter.interpret("decrease by 5")
        self.assertIsNone(mod.property)
        self.assertIn("property", mod.missing)
        self.assertEqual(mod.operation, "subtract")
        self.assertIsNotNone(mod.value)
        self.assertEqual(mod.value.kind, "relative")
        self.assertEqual(mod.value.value, 5)

    # 9. increase by 25%
    def test_09_increase_by_25_percent(self):
        mod = self.interpreter.interpret("increase by 25%")
        self.assertIsNone(mod.property)
        self.assertIn("property", mod.missing)
        self.assertEqual(mod.operation, "add")
        self.assertIsNotNone(mod.value)
        self.assertEqual(mod.value.kind, "percentage")
        self.assertEqual(mod.value.value, 25)
        self.assertEqual(mod.value.unit, "%")

        # In context with property: "increase speed by 25%"
        mod_speed = self.interpreter.interpret("increase speed by 25%")
        self.assertEqual(mod_speed.property, "speed")
        self.assertEqual(mod_speed.operation, "add")
        self.assertEqual(mod_speed.value.kind, "percentage")
        self.assertEqual(mod_speed.value.value, 25)
        self.assertEqual(mod_speed.missing, [])

    # 10. reduce by 50 percent
    def test_10_reduce_by_50_percent(self):
        mod = self.interpreter.interpret("reduce by 50 percent")
        self.assertIsNone(mod.property)
        self.assertIn("property", mod.missing)
        self.assertEqual(mod.operation, "subtract")
        self.assertIsNotNone(mod.value)
        self.assertEqual(mod.value.kind, "percentage")
        self.assertEqual(mod.value.value, 50)
        self.assertEqual(mod.value.unit, "%")

        # In context: "reduce health by 50%"
        mod_health = self.interpreter.interpret("reduce health by 50%")
        self.assertEqual(mod_health.property, "health")
        self.assertEqual(mod_health.operation, "subtract")
        self.assertEqual(mod_health.value.kind, "percentage")
        self.assertEqual(mod_health.value.value, 50)
        self.assertEqual(mod_health.missing, [])

    # 11. set to 10
    def test_11_set_to_10(self):
        mod = self.interpreter.interpret("set to 10")
        self.assertIsNone(mod.property)
        self.assertIn("property", mod.missing)
        self.assertEqual(mod.operation, "set")
        self.assertIsNotNone(mod.value)
        self.assertEqual(mod.value.kind, "absolute")
        self.assertEqual(mod.value.value, 10)

        # In context: "set speed to 10"
        mod_speed = self.interpreter.interpret("set speed to 10")
        self.assertEqual(mod_speed.property, "speed")
        self.assertEqual(mod_speed.operation, "set")
        self.assertEqual(mod_speed.value.kind, "absolute")
        self.assertEqual(mod_speed.value.value, 10)
        self.assertEqual(mod_speed.missing, [])

    # 12. decimal absolute value
    def test_12_decimal_absolute_value(self):
        mod = self.interpreter.interpret("set speed to 10.5")
        self.assertEqual(mod.property, "speed")
        self.assertEqual(mod.operation, "set")
        self.assertEqual(mod.value.kind, "absolute")
        self.assertEqual(mod.value.value, 10.5)

    # 13. decimal multiplier
    def test_13_decimal_multiplier(self):
        mod = self.interpreter.interpret("2.5x")
        self.assertEqual(mod.operation, "multiply")
        self.assertEqual(mod.value.kind, "multiplier")
        self.assertEqual(mod.value.value, 2.5)

        # In context: "make me 2.5x faster"
        mod_ctx = self.interpreter.interpret("make me 2.5x faster")
        self.assertEqual(mod_ctx.property, "speed")
        self.assertEqual(mod_ctx.operation, "multiply")
        self.assertEqual(mod_ctx.value.kind, "multiplier")
        self.assertEqual(mod_ctx.value.value, 2.5)

    # 14. negative relative value if supported by the contract
    def test_14_negative_relative_value(self):
        mod = self.interpreter.interpret("change speed by -5")
        self.assertEqual(mod.property, "speed")
        self.assertEqual(mod.value.kind, "relative")
        self.assertEqual(mod.value.value, -5)

    # 15. qualitative faster
    def test_15_qualitative_faster(self):
        mod = self.interpreter.interpret("make me faster")
        self.assertEqual(mod.property, "speed")
        self.assertIsNone(mod.operation)
        self.assertIsNotNone(mod.value)
        self.assertEqual(mod.value.kind, "qualitative")
        self.assertEqual(mod.value.value, "faster")
        self.assertEqual(mod.missing, [])

    # 16. qualitative stronger
    def test_16_qualitative_stronger(self):
        mod = self.interpreter.interpret("make the zombie stronger")
        self.assertIsNone(mod.property)
        self.assertIn("property", mod.missing)
        self.assertIsNone(mod.operation)
        self.assertIsNotNone(mod.value)
        self.assertEqual(mod.value.kind, "qualitative")
        self.assertEqual(mod.value.value, "stronger")
        self.assertEqual(mod.extra_metadata.get("target"), "zombie")

    # 17. missing numeric value
    def test_17_missing_numeric_value(self):
        # "increase speed"
        mod_spd = self.interpreter.interpret("increase speed")
        self.assertEqual(mod_spd.property, "speed")
        self.assertEqual(mod_spd.operation, "add")
        self.assertIsNone(mod_spd.value)
        self.assertIn("value", mod_spd.missing)

        # "increase attack damage"
        mod_atk = self.interpreter.interpret("increase attack damage")
        self.assertEqual(mod_atk.property, "attack_damage")
        self.assertEqual(mod_atk.operation, "add")
        self.assertIsNone(mod_atk.value)
        self.assertIn("value", mod_atk.missing)

        # "set health"
        mod_hp = self.interpreter.interpret("set health")
        self.assertEqual(mod_hp.property, "health")
        self.assertEqual(mod_hp.operation, "set")
        self.assertIsNone(mod_hp.value)
        self.assertIn("value", mod_hp.missing)

    # 18. ambiguous numeric wording
    def test_18_ambiguous_numeric_wording(self):
        # "make me faster by 10"
        mod = self.interpreter.interpret("make me faster by 10")
        self.assertEqual(mod.property, "speed")
        self.assertIsNone(mod.value)
        self.assertIn("value", mod.missing)
        self.assertTrue(mod.extra_metadata.get("ambiguous"))
        self.assertIn("Ambiguous", mod.extra_metadata.get("reason", ""))

    # 19. malformed numeric wording
    def test_19_malformed_numeric_wording(self):
        with self.assertRaises(ValueError):
            self.interpreter.interpret("increase speed by 10.5.2")

        with self.assertRaises(ValueError):
            self.interpreter.interpret("set speed to ++5")

        with self.assertRaises(ValueError):
            self.interpreter.interpret("make speed 10 times times")

        with self.assertRaises(ValueError):
            self.interpreter.interpret("speed by 25%%")

    # 20. boolean rejection
    def test_20_boolean_rejection(self):
        with self.assertRaises(ValueError):
            self.interpreter.interpret_value(True)

        with self.assertRaises(ValueError):
            self.interpreter.interpret_value(False)

        with self.assertRaises(ValueError):
            self.interpreter.interpret(True)  # type: ignore

        with self.assertRaises(ValueError):
            SemanticNumericValue(kind="multiplier", value=True)

    # 21. compound request preserving numeric meaning
    def test_21_compound_request_preserving_numeric_meaning(self):
        req = "make me 10 times faster and give me a netherite sword"
        result = self.interpreter.interpret_compound(req)

        self.assertEqual(len(result["modifications"]), 1)
        mod = result["modifications"][0]
        self.assertEqual(mod.property, "speed")
        self.assertEqual(mod.operation, "multiply")
        self.assertEqual(mod.value.kind, "multiplier")
        self.assertEqual(mod.value.value, 10)

        self.assertEqual(len(result["other_requirements"]), 1)
        self.assertIn("give me a netherite sword", result["other_requirements"])

        # Also test compound with two numeric modifications
        req_dual = "increase speed by 5 and reduce health by 10"
        result_dual = self.interpreter.interpret_compound(req_dual)
        self.assertEqual(len(result_dual["modifications"]), 2)
        mod_1, mod_2 = result_dual["modifications"]
        self.assertEqual(mod_1.property, "speed")
        self.assertEqual(mod_1.operation, "add")
        self.assertEqual(mod_1.value.value, 5)
        self.assertEqual(mod_2.property, "health")
        self.assertEqual(mod_2.operation, "subtract")
        self.assertEqual(mod_2.value.value, 10)

    # 22. Semantic independence: "10 times faster" does NOT become amplifier=9 or a Minecraft command
    def test_22_semantic_independence_ten_times_faster(self):
        mod = self.interpreter.interpret("make me 10 times faster")

        # Must NOT have an amplifier attribute
        self.assertFalse(hasattr(mod, "amplifier"))
        self.assertFalse(hasattr(mod.value, "amplifier"))
        dump = mod.model_dump()
        self.assertNotIn("amplifier", dump)
        self.assertNotIn("amplifier", dump["value"])

        # Must keep the actual semantic value 10 (not 9)
        self.assertEqual(mod.value.value, 10)

        # Must NOT generate Minecraft commands
        self.assertFalse(hasattr(mod, "command"))
        self.assertNotIn("command", dump)
        dump_str = str(dump).lower()
        self.assertNotIn("/effect", dump_str)
        self.assertNotIn("effect give", dump_str)
        self.assertNotIn("/attribute", dump_str)

    # 23. Additional prompt examples: zombie attack damage variations
    def test_23_zombie_attack_damage_variations(self):
        # "increase zombie attack damage by 5"
        m1 = self.interpreter.interpret("increase zombie attack damage by 5")
        self.assertEqual(m1.property, "attack_damage")
        self.assertEqual(m1.operation, "add")
        self.assertEqual(m1.value.kind, "relative")
        self.assertEqual(m1.value.value, 5)
        self.assertEqual(m1.extra_metadata.get("target"), "zombie")

        # "set zombie attack damage to 10"
        m2 = self.interpreter.interpret("set zombie attack damage to 10")
        self.assertEqual(m2.property, "attack_damage")
        self.assertEqual(m2.operation, "set")
        self.assertEqual(m2.value.kind, "absolute")
        self.assertEqual(m2.value.value, 10)
        self.assertEqual(m2.extra_metadata.get("target"), "zombie")

        # "make zombie attack damage 2x"
        m3 = self.interpreter.interpret("make zombie attack damage 2x")
        self.assertEqual(m3.property, "attack_damage")
        self.assertEqual(m3.operation, "multiply")
        self.assertEqual(m3.value.kind, "multiplier")
        self.assertEqual(m3.value.value, 2)
        self.assertEqual(m3.extra_metadata.get("target"), "zombie")

        # "make zombie attack damage 10"
        m4 = self.interpreter.interpret("make zombie attack damage 10")
        self.assertEqual(m4.property, "attack_damage")
        self.assertEqual(m4.operation, "set")
        self.assertEqual(m4.value.kind, "absolute")
        self.assertEqual(m4.value.value, 10)
        self.assertEqual(m4.extra_metadata.get("target"), "zombie")

    # 24. Convenience module-level functions
    def test_24_module_convenience_functions(self):
        mod = interpret_numeric_expression("2x faster")
        self.assertEqual(mod.property, "speed")
        self.assertEqual(mod.value.value, 2)

        mods = extract_property_modifications("make me 10 times faster and give me 64 apples")
        self.assertEqual(len(mods), 1)
        self.assertEqual(mods[0].value.value, 10)

    # 25. Comparative numeric faster (Blocker 1)
    def test_25_comparative_numeric_faster(self):
        m5 = self.interpreter.interpret("make me 5 faster")
        self.assertEqual(m5.property, "speed")
        self.assertEqual(m5.operation, "add")
        self.assertIsNotNone(m5.value)
        self.assertEqual(m5.value.kind, "relative")
        self.assertEqual(m5.value.value, 5)
        self.assertEqual(m5.missing, [])

        m10 = self.interpreter.interpret("make me 10 faster")
        self.assertEqual(m10.property, "speed")
        self.assertEqual(m10.operation, "add")
        self.assertEqual(m10.value.kind, "relative")
        self.assertEqual(m10.value.value, 10)

    # 26. Comparative numeric slower (Blocker 1)
    def test_26_comparative_numeric_slower(self):
        m5 = self.interpreter.interpret("make me 5 slower")
        self.assertEqual(m5.property, "speed")
        self.assertEqual(m5.operation, "subtract")
        self.assertIsNotNone(m5.value)
        self.assertEqual(m5.value.kind, "relative")
        self.assertEqual(m5.value.value, 5)

        m10 = self.interpreter.interpret("make me 10 slower")
        self.assertEqual(m10.property, "speed")
        self.assertEqual(m10.operation, "subtract")
        self.assertEqual(m10.value.kind, "relative")
        self.assertEqual(m10.value.value, 10)

    # 27. Distinction between 'make me 5 faster' and 'set my speed to 5' (Blocker 1)
    def test_27_distinction_faster_vs_set(self):
        mod_relative = self.interpreter.interpret("make me 5 faster")
        mod_absolute = self.interpreter.interpret("set my speed to 5")

        self.assertEqual(mod_relative.property, "speed")
        self.assertEqual(mod_relative.operation, "add")
        self.assertEqual(mod_relative.value.kind, "relative")
        self.assertEqual(mod_relative.value.value, 5)

        self.assertEqual(mod_absolute.property, "speed")
        self.assertEqual(mod_absolute.operation, "set")
        self.assertEqual(mod_absolute.value.kind, "absolute")
        self.assertEqual(mod_absolute.value.value, 5)

    # 28. Comparative numeric underspecified property (Blocker 1)
    def test_28_comparative_numeric_underspecified_property(self):
        mod = self.interpreter.interpret("make zombie 5 stronger")
        self.assertIsNone(mod.property)
        self.assertIn("property", mod.missing)
        self.assertEqual(mod.operation, "add")
        self.assertEqual(mod.value.kind, "relative")
        self.assertEqual(mod.value.value, 5)
        self.assertEqual(mod.extra_metadata.get("target"), "zombie")


if __name__ == "__main__":
    unittest.main()

