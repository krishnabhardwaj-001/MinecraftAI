"""
test_step17_models.py - Step 17.1 Semantic Property Modification Models Test Suite

Validates the Minecraft-independent semantic property modification data contract:
1. absolute value
2. relative value
3. percentage
4. multiplier
5. qualitative value
6. missing value
7. "10 times faster" semantic representation
8. absolute attack damage
9. relative attack damage
10. percentage decrease
11. missing property
12. missing operation
13. missing value
14. invalid operation
15. invalid value kind
16. numeric value without number
17. invalid missing parameter
+ additional edge cases (boolean rejection, extra metadata preservation, serialization).
"""

import unittest
from pydantic import ValidationError

from ai.semantic_models import (
    PropertyModification,
    SemanticNumericValue,
    SemanticValue,
    SUPPORTED_OPERATIONS,
    SUPPORTED_VALUE_KINDS,
    TYPED_MISSING_PARAMETERS,
)


class TestStep17SemanticModels(unittest.TestCase):
    """
    Test suite for Step 17.1 generic semantic property modification contracts.
    """

    # 1. Absolute value
    def test_01_absolute_value(self):
        val = SemanticNumericValue(kind="absolute", value=10)
        self.assertEqual(val.kind, "absolute")
        self.assertEqual(val.value, 10)

        # Float absolute value
        val_f = SemanticNumericValue(kind="absolute", value=15.5)
        self.assertEqual(val_f.value, 15.5)

    # 2. Relative value
    def test_02_relative_value(self):
        val = SemanticNumericValue(kind="relative", value=5)
        self.assertEqual(val.kind, "relative")
        self.assertEqual(val.value, 5)

        # Negative relative value
        val_neg = SemanticNumericValue(kind="relative", value=-2.5)
        self.assertEqual(val_neg.value, -2.5)

    # 3. Percentage
    def test_03_percentage(self):
        val = SemanticNumericValue(kind="percentage", value=50, unit="%")
        self.assertEqual(val.kind, "percentage")
        self.assertEqual(val.value, 50)
        self.assertEqual(val.unit, "%")

    # 4. Multiplier
    def test_04_multiplier(self):
        val = SemanticNumericValue(kind="multiplier", value=10)
        self.assertEqual(val.kind, "multiplier")
        self.assertEqual(val.value, 10)

        # Fractional multiplier (e.g. 0.5x speed)
        val_half = SemanticNumericValue(kind="multiplier", value=0.5)
        self.assertEqual(val_half.value, 0.5)

    # 5. Qualitative value
    def test_05_qualitative_value(self):
        val = SemanticValue(kind="qualitative", value="strong")
        self.assertEqual(val.kind, "qualitative")
        self.assertEqual(val.value, "strong")

        val_fast = SemanticValue(kind="qualitative", value="very fast")
        self.assertEqual(val_fast.value, "very fast")

    # 6. Missing value
    def test_06_missing_value(self):
        val = SemanticValue(kind="missing", value=None)
        self.assertEqual(val.kind, "missing")
        self.assertIsNone(val.value)

    # 7. "10 times faster" semantic representation
    def test_07_ten_times_faster_semantic_representation(self):
        mod = PropertyModification(
            property="speed",
            operation="multiply",
            value=SemanticNumericValue(
                kind="multiplier",
                value=10
            ),
            source_text="10 times faster"
        )
        self.assertEqual(mod.property, "speed")
        self.assertEqual(mod.operation, "multiply")
        self.assertIsNotNone(mod.value)
        self.assertEqual(mod.value.kind, "multiplier")
        self.assertEqual(mod.value.value, 10)
        self.assertEqual(mod.source_text, "10 times faster")
        self.assertEqual(mod.missing, [])

    # 8. Absolute attack damage
    def test_08_absolute_attack_damage(self):
        mod = PropertyModification(
            property="attack_damage",
            operation="set",
            value=SemanticNumericValue(
                kind="absolute",
                value=10
            ),
            source_text="set zombie attack damage to 10"
        )
        self.assertEqual(mod.property, "attack_damage")
        self.assertEqual(mod.operation, "set")
        self.assertEqual(mod.value.kind, "absolute")
        self.assertEqual(mod.value.value, 10)

    # 9. Relative attack damage
    def test_09_relative_attack_damage(self):
        mod = PropertyModification(
            property="attack_damage",
            operation="add",
            value=SemanticNumericValue(
                kind="relative",
                value=5
            ),
            source_text="increase zombie attack damage by 5"
        )
        self.assertEqual(mod.property, "attack_damage")
        self.assertEqual(mod.operation, "add")
        self.assertEqual(mod.value.kind, "relative")
        self.assertEqual(mod.value.value, 5)

    # 10. Percentage decrease
    def test_10_percentage_decrease(self):
        mod = PropertyModification(
            property="speed",
            operation="subtract",
            value=SemanticNumericValue(
                kind="percentage",
                value=20,
                unit="%"
            ),
            source_text="decrease speed by 20%"
        )
        self.assertEqual(mod.property, "speed")
        self.assertEqual(mod.operation, "subtract")
        self.assertEqual(mod.value.kind, "percentage")
        self.assertEqual(mod.value.value, 20)

    # 11. Missing property
    def test_11_missing_property(self):
        # Explicit missing declaration when property is None
        mod = PropertyModification(
            property=None,
            operation="add",
            value=SemanticNumericValue(kind="relative", value=5),
            missing=["property"],
            source_text="make the zombie stronger"
        )
        self.assertIsNone(mod.property)
        self.assertIn("property", mod.missing)

        # Missing property without explicit declaration must be rejected
        with self.assertRaises(ValidationError):
            PropertyModification(
                property=None,
                operation="add",
                value=SemanticNumericValue(kind="relative", value=5),
                missing=[]
            )

    # 12. Missing operation
    def test_12_missing_operation(self):
        # Explicit missing declaration when operation is None
        mod = PropertyModification(
            property="attack_damage",
            operation=None,
            value=SemanticNumericValue(kind="absolute", value=10),
            missing=["operation"]
        )
        self.assertIsNone(mod.operation)
        self.assertIn("operation", mod.missing)

        # Missing operation without explicit declaration must be rejected
        with self.assertRaises(ValidationError):
            PropertyModification(
                property="attack_damage",
                operation=None,
                value=SemanticNumericValue(kind="absolute", value=10),
                missing=[]
            )

    # 13. Missing value
    def test_13_missing_value(self):
        # Explicit missing declaration when value is None
        mod = PropertyModification(
            property="attack_damage",
            operation="add",
            value=None,
            missing=["value"],
            source_text="increase zombie attack damage"
        )
        self.assertIsNone(mod.value)
        self.assertIn("value", mod.missing)

        # Explicit missing declaration when value has kind="missing"
        mod_with_val = PropertyModification(
            property="attack_damage",
            operation="add",
            value=SemanticValue(kind="missing", value=None),
            missing=["value"]
        )
        self.assertEqual(mod_with_val.value.kind, "missing")
        self.assertIn("value", mod_with_val.missing)

        # Missing value without explicit declaration must be rejected
        with self.assertRaises(ValidationError):
            PropertyModification(
                property="attack_damage",
                operation="add",
                value=None,
                missing=[]
            )

    # 14. Invalid operation
    def test_14_invalid_operation(self):
        with self.assertRaises(ValidationError):
            PropertyModification(
                property="speed",
                operation="boost_super_fast",
                value=SemanticNumericValue(kind="multiplier", value=2)
            )

        with self.assertRaises(ValidationError):
            PropertyModification(
                property="health",
                operation="triple",
                value=SemanticNumericValue(kind="absolute", value=50)
            )

    # 15. Invalid value kind
    def test_15_invalid_value_kind(self):
        with self.assertRaises(ValidationError):
            SemanticNumericValue(kind="arbitrary_scale", value=10)

        with self.assertRaises(ValidationError):
            SemanticValue(kind="unknown_kind", value="some_val")

    # 16. Numeric value without number
    def test_16_numeric_value_without_number(self):
        # Numeric kind with None value
        with self.assertRaises(ValidationError):
            SemanticNumericValue(kind="multiplier", value=None)

        with self.assertRaises(ValidationError):
            SemanticNumericValue(kind="absolute", value=None)

        # Numeric kind with non-numeric string value
        with self.assertRaises(ValidationError):
            SemanticNumericValue(kind="relative", value="five")

        # Numeric kind with boolean value (isinstance(True, int) is True in Python)
        with self.assertRaises(ValidationError):
            SemanticNumericValue(kind="multiplier", value=True)

        with self.assertRaises(ValidationError):
            SemanticNumericValue(kind="percentage", value=False)

        # 'missing' kind with a numeric value
        with self.assertRaises(ValidationError):
            SemanticValue(kind="missing", value=10)

    # 17. Invalid missing parameter
    def test_17_invalid_missing_parameter(self):
        with self.assertRaises(ValidationError):
            PropertyModification(
                property="speed",
                operation="multiply",
                value=SemanticNumericValue(kind="multiplier", value=2),
                missing=["target"]
            )

        with self.assertRaises(ValidationError):
            PropertyModification(
                property="speed",
                operation="multiply",
                value=SemanticNumericValue(kind="multiplier", value=2),
                missing=["unsupported_missing_param"]
            )

    # 18. Contradictory missing declarations
    def test_18_contradictory_missing_declarations(self):
        # Declared missing while property is provided
        with self.assertRaises(ValidationError):
            PropertyModification(
                property="speed",
                operation="multiply",
                value=SemanticNumericValue(kind="multiplier", value=2),
                missing=["property"]
            )

        # Declared missing while operation is provided
        with self.assertRaises(ValidationError):
            PropertyModification(
                property="speed",
                operation="multiply",
                value=SemanticNumericValue(kind="multiplier", value=2),
                missing=["operation"]
            )

        # Declared missing while valid value is provided
        with self.assertRaises(ValidationError):
            PropertyModification(
                property="speed",
                operation="multiply",
                value=SemanticNumericValue(kind="multiplier", value=2),
                missing=["value"]
            )

    # 19. Extra metadata and serialization
    def test_19_extra_metadata_and_serialization(self):
        mod = PropertyModification(
            property="speed",
            operation="multiply",
            value=SemanticNumericValue(kind="multiplier", value=10),
            source_text="10 times faster",
            subject="player",
            custom_note="movement enhancement"
        )
        data = mod.model_dump()
        self.assertEqual(data["property"], "speed")
        self.assertEqual(data["operation"], "multiply")
        self.assertEqual(data["value"]["kind"], "multiplier")
        self.assertEqual(data["value"]["value"], 10)
        self.assertEqual(data["subject"], "player")
        self.assertEqual(data["custom_note"], "movement enhancement")

        # Round-trip deserialization
        restored = PropertyModification(**data)
        self.assertEqual(restored.property, "speed")
        self.assertEqual(restored.value.value, 10)

    # 20. Qualitative modification with operation=None is valid without missing=['operation']
    def test_20_qualitative_without_operation_valid(self):
        mod = PropertyModification(
            property="speed",
            operation=None,
            value=SemanticValue(kind="qualitative", value="faster")
        )
        self.assertIsNone(mod.operation)
        self.assertEqual(mod.missing, [])
        self.assertEqual(mod.value.kind, "qualitative")
        self.assertEqual(mod.value.value, "faster")

        # Qualitative value with 'operation' in missing must be rejected (operation not required)
        with self.assertRaises(ValidationError):
            PropertyModification(
                property="speed",
                operation=None,
                value=SemanticValue(kind="qualitative", value="faster"),
                missing=["operation"]
            )

    # 21. extra_metadata typed field and default factory
    def test_21_extra_metadata_typed_field_default_factory(self):
        # Default construction has empty dict without AttributeError
        mod = PropertyModification(
            property="speed",
            operation="multiply",
            value=SemanticNumericValue(kind="multiplier", value=2)
        )
        self.assertTrue(hasattr(mod, "extra_metadata"))
        self.assertIsInstance(mod.extra_metadata, dict)
        self.assertEqual(mod.extra_metadata, {})

        # Preserves explicit extra_metadata
        mod_with_meta = PropertyModification(
            property="speed",
            operation="multiply",
            value=SemanticNumericValue(kind="multiplier", value=2),
            extra_metadata={"target": "zombie", "custom_flag": True}
        )
        self.assertEqual(mod_with_meta.extra_metadata.get("target"), "zombie")
        self.assertTrue(mod_with_meta.extra_metadata.get("custom_flag"))


if __name__ == "__main__":
    unittest.main()
