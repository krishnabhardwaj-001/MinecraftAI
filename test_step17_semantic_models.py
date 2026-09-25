"""Step 17.1 semantic modification contract tests."""

import unittest
from pydantic import ValidationError

from ai.semantic_models import (
    MissingSemanticParameter,
    PropertyModification,
    SemanticNumericValue,
)


class TestStep17SemanticModels(unittest.TestCase):

    def test_absolute_value(self):
        value = SemanticNumericValue(kind="absolute", value=10)
        self.assertEqual(value.kind, "absolute")
        self.assertEqual(value.value, 10)

    def test_multiplier_value(self):
        value = SemanticNumericValue(kind="multiplier", value=10)
        self.assertEqual(value.kind, "multiplier")
        self.assertEqual(value.value, 10)

    def test_percentage_value(self):
        value = SemanticNumericValue(kind="percentage", value=50)
        self.assertEqual(value.kind, "percentage")
        self.assertEqual(value.value, 50)

    def test_relative_value(self):
        value = SemanticNumericValue(kind="relative", value=5)
        self.assertEqual(value.kind, "relative")
        self.assertEqual(value.value, 5)

    def test_missing_value_is_typed(self):
        value = SemanticNumericValue(kind="missing")
        modification = PropertyModification(
            property="attack_damage",
            operation="add",
            value=value,
            missing=[{"parameter": "value", "reason": "amount was not specified"}],
        )
        self.assertEqual(modification.missing[0].parameter, "value")

    def test_qualitative_value(self):
        value = SemanticNumericValue(kind="qualitative")
        modification = PropertyModification(
            property="strength",
            operation="multiply",
            value=value,
        )
        self.assertEqual(modification.value.kind, "qualitative")

    def test_ten_times_faster_can_be_represented_without_minecraft_mapping(self):
        modification = PropertyModification(
            property="speed",
            operation="multiply",
            value=SemanticNumericValue(kind="multiplier", value=10),
            source_text="10 times faster",
        )
        self.assertEqual(modification.property, "speed")
        self.assertEqual(modification.operation, "multiply")
        self.assertEqual(modification.value.kind, "multiplier")
        self.assertEqual(modification.value.value, 10)

    def test_set_absolute_property(self):
        modification = PropertyModification(
            property="attack_damage",
            operation="set",
            value=SemanticNumericValue(kind="absolute", value=10),
        )
        self.assertEqual(modification.operation, "set")

    def test_increase_by_absolute_amount(self):
        modification = PropertyModification(
            property="attack_damage",
            operation="add",
            value=SemanticNumericValue(kind="relative", value=5),
        )
        self.assertEqual(modification.operation, "add")
        self.assertEqual(modification.value.kind, "relative")

    def test_decrease_by_percentage(self):
        modification = PropertyModification(
            property="health",
            operation="subtract",
            value=SemanticNumericValue(kind="percentage", value=20),
        )
        self.assertEqual(modification.value.kind, "percentage")

    def test_missing_property_is_structured(self):
        modification = PropertyModification(
            operation="multiply",
            value=SemanticNumericValue(kind="multiplier", value=2),
            missing=[{"parameter": "property", "reason": "stronger is ambiguous"}],
        )
        self.assertEqual(modification.missing[0].parameter, "property")

    def test_missing_value_is_structured(self):
        modification = PropertyModification(
            property="attack_damage",
            operation="add",
            missing=[{"parameter": "value", "reason": "magnitude was omitted"}],
        )
        self.assertEqual(modification.missing[0].parameter, "value")

    def test_missing_operation_is_structured(self):
        modification = PropertyModification(
            property="speed",
            value=SemanticNumericValue(kind="absolute", value=2),
            missing=[{"parameter": "operation", "reason": "change direction was omitted"}],
        )
        self.assertEqual(modification.missing[0].parameter, "operation")

    def test_invalid_value_kind_rejected(self):
        with self.assertRaises(ValidationError):
            SemanticNumericValue(kind="times_faster", value=10)

    def test_invalid_operation_rejected(self):
        with self.assertRaises(ValidationError):
            PropertyModification(
                property="speed",
                operation="boost",
                value=SemanticNumericValue(kind="multiplier", value=2),
            )

    def test_numeric_kind_requires_value(self):
        with self.assertRaises(ValidationError):
            SemanticNumericValue(kind="multiplier")

    def test_missing_kind_cannot_have_numeric_value(self):
        with self.assertRaises(ValidationError):
            SemanticNumericValue(kind="missing", value=10)

    def test_property_cannot_be_implicitly_missing(self):
        with self.assertRaises(ValidationError):
            PropertyModification(
                operation="multiply",
                value=SemanticNumericValue(kind="multiplier", value=2),
            )

    def test_operation_cannot_be_implicitly_missing(self):
        with self.assertRaises(ValidationError):
            PropertyModification(
                property="speed",
                value=SemanticNumericValue(kind="multiplier", value=2),
            )

    def test_value_cannot_be_implicitly_missing(self):
        with self.assertRaises(ValidationError):
            PropertyModification(
                property="speed",
                operation="multiply",
            )

    def test_missing_parameter_type_is_validated(self):
        with self.assertRaises(ValidationError):
            MissingSemanticParameter(parameter="effect")

    def test_extra_context_is_allowed(self):
        modification = PropertyModification(
            property="speed",
            operation="multiply",
            value=SemanticNumericValue(kind="multiplier", value=10),
            source_text="make me 10 times faster",
            confidence=0.98,
        )
        self.assertEqual(modification.confidence, 0.98)


if __name__ == "__main__":
    unittest.main()
