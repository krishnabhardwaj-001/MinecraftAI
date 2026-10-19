"""
test_phase3_property_generalization.py - Phase 3 Architectural Repair Regression Suite

Validates that:
1. Relational and descriptive gameplay requests are NOT misclassified as arithmetic property modifications.
2. The word "damage" in combat/event contexts (dealing, taking, receiving, environmental damage)
   is NOT misclassified as the attack_damage attribute.
3. Incomplete heuristic extractions from raw text do NOT hijack the planner when structured understanding
   defines broader gameplay mechanics.
4. Genuine numeric property modifications ("increase health by 5", "reduce attack damage by 2",
   "double attack damage", "reduce damage by 2") continue to be parsed accurately.
"""

import unittest
from unittest.mock import MagicMock
from ai.numeric_interpreter import (
    NumericSemanticInterpreter,
    extract_property_modifications,
)
from ai.semantic_models import (
    PropertyModification,
    SemanticNumericValue,
)
from ai.planner import MinecraftPlanner, create_plan, validate_plan_mechanisms


class TestPropertyGeneralizationRegression(unittest.TestCase):
    def setUp(self):
        self.interpreter = NumericSemanticInterpreter()

    # -------------------------------------------------------------------------
    # Mandatory Regression Suite: Non-Property / Descriptive / Relational Cases
    # -------------------------------------------------------------------------

    def test_players_share_health(self):
        """Relational mechanic 'players share health' must NOT be classified as a property modification."""
        text = "players share health"
        mods = extract_property_modifications(text)
        self.assertEqual(mods, [], f"Expected no property modifications for '{text}', got {mods}")

        compound = self.interpreter.interpret_compound(text)
        self.assertEqual(compound["modifications"], [])
        self.assertIn(text, compound["other_requirements"])

    def test_whenever_one_player_takes_damage(self):
        """Conditional combat event 'whenever one player takes damage, the shared health decreases for everyone' must NOT be a property modification."""
        text = "whenever one player takes damage, the shared health decreases for everyone"
        mods = extract_property_modifications(text)
        self.assertEqual(mods, [], f"Expected no property modifications for '{text}', got {mods}")

        compound = self.interpreter.interpret_compound(text)
        self.assertEqual(compound["modifications"], [])
        self.assertIn(text, compound["other_requirements"])

    def test_if_one_player_heals_everyone_heals(self):
        """Event mechanic 'if one player heals, everyone heals' must NOT be a property modification."""
        text = "if one player heals, everyone heals"
        mods = extract_property_modifications(text)
        self.assertEqual(mods, [], f"Expected no property modifications for '{text}', got {mods}")

        compound = self.interpreter.interpret_compound(text)
        self.assertEqual(compound["modifications"], [])
        self.assertIn(text, compound["other_requirements"])

    def test_immune_to_fall_damage(self):
        """Hazard immunity 'immune to fall damage' must NOT be classified as an attribute modification."""
        text = "immune to fall damage"
        mods = extract_property_modifications(text)
        self.assertEqual(mods, [], f"Expected no property modifications for '{text}', got {mods}")

        compound = self.interpreter.interpret_compound(text)
        self.assertEqual(compound["modifications"], [])
        self.assertIn(text, compound["other_requirements"])

    def test_display_health_on_the_scoreboard(self):
        """UI / Scoreboard display 'display health on the scoreboard' must NOT be a property modification."""
        text = "display health on the scoreboard"
        mods = extract_property_modifications(text)
        self.assertEqual(mods, [], f"Expected no property modifications for '{text}', got {mods}")

        compound = self.interpreter.interpret_compound(text)
        self.assertEqual(compound["modifications"], [])
        self.assertIn(text, compound["other_requirements"])

    # -------------------------------------------------------------------------
    # Mandatory Regression Suite: Genuine Property Modifications
    # -------------------------------------------------------------------------

    def test_increase_health_by_5(self):
        """Genuine numeric modification 'increase health by 5' must be accurately parsed."""
        text = "increase health by 5"
        mods = extract_property_modifications(text)
        self.assertEqual(len(mods), 1)
        mod = mods[0]
        self.assertEqual(mod.property, "health")
        self.assertEqual(mod.operation, "add")
        self.assertIsInstance(mod.value, SemanticNumericValue)
        self.assertEqual(mod.value.value, 5)
        self.assertEqual(mod.value.kind, "relative")
        self.assertEqual(mod.missing, [])

    def test_reduce_attack_damage_by_2(self):
        """Genuine numeric modification 'reduce attack damage by 2' must be accurately parsed."""
        text = "reduce attack damage by 2"
        mods = extract_property_modifications(text)
        self.assertEqual(len(mods), 1)
        mod = mods[0]
        self.assertEqual(mod.property, "attack_damage")
        self.assertEqual(mod.operation, "subtract")
        self.assertIsInstance(mod.value, SemanticNumericValue)
        self.assertEqual(mod.value.value, 2)
        self.assertEqual(mod.value.kind, "relative")
        self.assertEqual(mod.missing, [])

    def test_double_attack_damage(self):
        """Multiplier modification 'double attack damage' must be accurately parsed."""
        text = "double attack damage"
        mods = extract_property_modifications(text)
        self.assertEqual(len(mods), 1)
        mod = mods[0]
        self.assertEqual(mod.property, "attack_damage")
        self.assertEqual(mod.operation, "multiply")
        self.assertIsInstance(mod.value, SemanticNumericValue)
        self.assertEqual(mod.value.value, 2)
        self.assertEqual(mod.value.kind, "multiplier")
        self.assertEqual(mod.missing, [])

    def test_reduce_damage_by_2(self):
        """Disambiguation: 'reduce damage by 2' with an arithmetic verb and number maps to attack_damage."""
        text = "reduce damage by 2"
        mods = extract_property_modifications(text)
        self.assertEqual(len(mods), 1)
        mod = mods[0]
        self.assertEqual(mod.property, "attack_damage")
        self.assertEqual(mod.operation, "subtract")
        self.assertEqual(mod.value.value, 2)

    def test_increase_health_by_5_for_everyone(self):
        """A numeric modification with a recipient modifier 'for everyone' preserves the numeric modification."""
        text = "increase health by 5 for everyone"
        mods = extract_property_modifications(text)
        self.assertEqual(len(mods), 1)
        mod = mods[0]
        self.assertEqual(mod.property, "health")
        self.assertEqual(mod.operation, "add")
        self.assertEqual(mod.value.value, 5)

    def test_double_attack_damage_for_everyone(self):
        """Multiplier modification with recipient specifier 'for everyone' preserves multiplier."""
        text = "double attack damage for everyone"
        mods = extract_property_modifications(text)
        self.assertEqual(len(mods), 1)
        mod = mods[0]
        self.assertEqual(mod.property, "attack_damage")
        self.assertEqual(mod.operation, "multiply")
        self.assertEqual(mod.value.value, 2)
        self.assertEqual(mod.value.kind, "multiplier")

    def test_make_players_faster_for_everyone(self):
        """Qualitative modification with recipient specifier 'for everyone' preserves qualitative value."""
        text = "make players faster for everyone"
        mods = extract_property_modifications(text)
        self.assertEqual(len(mods), 1)
        mod = mods[0]
        self.assertEqual(mod.property, "speed")
        self.assertIsNone(mod.operation)
        self.assertEqual(mod.value.value, "faster")
        self.assertEqual(mod.value.kind, "qualitative")

    def test_increase_speed_for_everyone(self):
        """Missing-value modification with recipient specifier 'for everyone' preserves missing value request."""
        text = "increase speed for everyone"
        mods = extract_property_modifications(text)
        self.assertEqual(len(mods), 1)
        mod = mods[0]
        self.assertEqual(mod.property, "speed")
        self.assertEqual(mod.operation, "add")
        self.assertIsNone(mod.value)
        self.assertEqual(mod.missing, ["value"])


class TestPlannerHijackingPrevention(unittest.TestCase):
    def setUp(self):
        self.mock_ai = MagicMock()
        self.planner = MinecraftPlanner(version="1.21.11", ai_provider=self.mock_ai)

    def test_planner_does_not_hijack_shared_health_mechanics(self):
        """When understanding contains structured non-property requirements,

        raw text heuristic extraction must not hijack the plan or trigger false clarification.
        """
        understanding = {
            "summary": "Shared health across players",
            "understood_request": "every player shares same health, whenever one deals damage all shares same, if one heals all heals",
            "requirements": [
                {"intent": "synchronize_health", "details": "all players share the same health pool"},
                {"intent": "damage_sharing", "details": "whenever one takes damage all share same"},
                {"intent": "heal_sharing", "details": "if one heals all heal"},
            ],
        }

        # Mock generate_structured to return a valid PlannerResult dict
        self.mock_ai.generate_structured.return_value = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "Shared health datapack plan",
            "implementation_plan": [],
            "missing_knowledge": [],
            "clarifications": [],
        }

        result = self.planner.plan(understanding)

        # General LLM path must have been invoked, not the property modification hijacker
        self.mock_ai.generate_structured.assert_called_once()
        self.assertEqual(result["status"], "ready")
        for c in result.get("clarifications", []):
            self.assertNotIn("How should health be modified", c)
            self.assertNotIn("How should attack_damage be modified", c)

    def test_planner_property_modification_pipeline_intact(self):
        """Genuine property modifications are still routed to plan_property_modification."""
        understanding = {
            "summary": "Increase health by 5",
            "understood_request": "increase health by 5",
            "requirements": [],
        }

        result = self.planner.plan(understanding)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(len(result["implementation_plan"]), 1)
        ip = result["implementation_plan"][0]
        self.assertIn("health", ip["objective"].lower())
        validate_plan_mechanisms(result)

    def test_planner_clarification_for_missing_value_preserved(self):
        """Genuine incomplete property modifications ('increase speed') still trigger clarification."""
        understanding = {
            "summary": "Increase speed",
            "understood_request": "increase speed",
            "requirements": [],
        }

        result = self.planner.plan(understanding)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertTrue(any("speed" in c.lower() for c in result.get("clarifications", [])))


if __name__ == "__main__":
    unittest.main()
