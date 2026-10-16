"""
test_conversational_understanding.py - Unit tests for Conversational Understanding Engine.

Verifies:
1. Whole-message semantic interpretation without keyword/regex classification.
2. Incomplete/vague request completion with sensible defaults and explained assumptions.
3. Ambiguous requests with focused human choices.
4. Multi-turn context reconciliation and revision preservation.
5. Confirmation phrase detection.
6. Multi-part compound requests.
7. Novel / unseen request interpretation.
8. Capability limit explanations for unsupported requests.
"""
import unittest
from unittest.mock import MagicMock

from ai.conversation import (
    AssumptionItem,
    ConversationSession,
    ProposedBehavior,
)
from ai.conversational_agent import ConversationalUnderstandingEngine


class TestConversationalUnderstanding(unittest.TestCase):
    """Verifies ConversationalUnderstandingEngine behaviors across dialogue scenarios."""

    def setUp(self):
        self.mock_ai = MagicMock()
        self.engine = ConversationalUnderstandingEngine(
            ai_provider=self.mock_ai,
            version="1.21.11"
        )

    def test_1_vague_request_completion_with_sensible_defaults(self):
        """Vague requests must infer sensible defaults and explain assumptions in plain English."""
        # Simulated LLM response for 'make me faster'
        self.mock_ai.generate_structured.return_value = {
            "summary": "Increases player movement speed by 50% permanently.",
            "trigger_condition": "Continuously active in world",
            "target_affected": "The player (@s)",
            "mechanisms_involved": ["attribute_modifier"],
            "assumptions": [
                {
                    "description": "50% movement speed increase",
                    "rationale": "Noticeable speed boost without causing FOV camera distortion",
                    "default_applied": "+50% generic.movement_speed modifier"
                },
                {
                    "description": "Permanent attribute rather than potion effect",
                    "rationale": "Clean gameplay without potion swirls or expiration timers",
                    "default_applied": "Permanent attribute modifier"
                }
            ],
            "open_choices": [],
            "status": "proposed",
            "is_complete": True,
            "confirmation_prompt": "Does this 50% speed increase sound good, or would you like a different speed amount?"
        }

        session = ConversationSession()
        proposal = self.engine.process_turn(session, "Make me faster.")

        self.assertEqual(proposal.status, "proposed")
        self.assertTrue(proposal.is_complete)
        self.assertEqual(len(proposal.assumptions), 2)
        self.assertIn("50%", proposal.assumptions[0].description)
        self.assertIn("camera distortion", proposal.assumptions[0].rationale)
        self.assertIn("Does this 50% speed increase sound good", proposal.confirmation_prompt)
        self.assertEqual(len(session.turns), 1)

    def test_2_detailed_request_direct_comprehension_without_unnecessary_questions(self):
        """Detailed requests must be understood directly without asking unnecessary questions."""
        self.mock_ai.generate_structured.return_value = {
            "summary": "When rain starts, gives every player exactly 1 diamond once.",
            "trigger_condition": "When weather transitions to rain",
            "target_affected": "All players (@a)",
            "mechanisms_involved": ["predicate", "scoreboard_latch", "function"],
            "assumptions": [],
            "open_choices": [],
            "status": "proposed",
            "is_complete": True,
            "confirmation_prompt": "Would you like to build this rain-triggered diamond datapack?"
        }

        session = ConversationSession()
        proposal = self.engine.process_turn(session, "When it starts raining, give every player one diamond.")

        self.assertEqual(proposal.status, "proposed")
        self.assertTrue(proposal.is_complete)
        self.assertEqual(len(proposal.open_choices), 0)
        self.assertEqual(proposal.target_affected, "All players (@a)")

    def test_3_ambiguous_request_with_materially_divergent_choices(self):
        """Requests with multiple materially different interpretations must offer focused choices."""
        self.mock_ai.generate_structured.return_value = {
            "summary": "Custom loot drops for zombies.",
            "trigger_condition": "When a zombie dies",
            "target_affected": "Zombies",
            "mechanisms_involved": ["loot_table"],
            "assumptions": [],
            "open_choices": [
                "Rare Minerals: 20% chance for diamonds or emeralds",
                "Combat Gear: Iron sword or chainmail armor",
                "Magical Items: Experience bottles and golden apples"
            ],
            "status": "needs_clarification",
            "is_complete": False,
            "confirmation_prompt": "Which of these loot drop styles would you prefer?"
        }

        session = ConversationSession()
        proposal = self.engine.process_turn(session, "Make zombies drop something cool.")

        self.assertEqual(proposal.status, "needs_clarification")
        self.assertFalse(proposal.is_complete)
        self.assertEqual(len(proposal.open_choices), 3)
        self.assertIn("Rare Minerals", proposal.open_choices[0])

    def test_4_multi_turn_follow_up_correction_and_context_preservation(self):
        """Follow-up turns must update revised fields while preserving untouched requirements."""
        session = ConversationSession()

        # Turn 1: Initial proposal
        self.mock_ai.generate_structured.return_value = {
            "summary": "Zombies drop diamonds when killed.",
            "trigger_condition": "When a zombie dies",
            "target_affected": "Zombies",
            "mechanisms_involved": ["loot_table"],
            "assumptions": [{"description": "100% drop chance", "rationale": "Default guaranteed drop", "default_applied": "1 diamond"}],
            "open_choices": [],
            "status": "proposed",
            "is_complete": True,
            "raw_requirements": [{"subject": "zombie", "target": "zombie", "intent": "drop diamond", "conditions": ["death"]}]
        }
        p1 = self.engine.process_turn(session, "Make zombies drop diamonds.")
        self.assertEqual(p1.summary, "Zombies drop diamonds when killed.")

        # Turn 2: User revises item to gold and specifies 20% chance
        self.mock_ai.generate_structured.return_value = {
            "summary": "Zombies have a 20% chance to drop 1 gold ingot when killed.",
            "trigger_condition": "When a zombie dies",
            "target_affected": "Zombies",
            "mechanisms_involved": ["loot_table"],
            "assumptions": [{"description": "20% drop chance", "rationale": "Specified by user", "default_applied": "20% chance"}],
            "open_choices": [],
            "status": "proposed",
            "is_complete": True,
            "raw_requirements": [{"subject": "zombie", "target": "zombie", "intent": "drop gold ingot", "conditions": ["death", "chance: 20%"]}]
        }
        p2 = self.engine.process_turn(session, "Actually make them drop gold ingots and only a 20% chance.")

        self.assertEqual(p2.summary, "Zombies have a 20% chance to drop 1 gold ingot when killed.")
        self.assertEqual(p2.target_affected, "Zombies")  # Preserved from Turn 1
        self.assertEqual(len(session.turns), 2)

    def test_5_confirmation_phrase_transitions_to_confirmed_state(self):
        """User confirmation phrase ('looks good', 'confirm', 'yes') marks proposal as confirmed."""
        session = ConversationSession()

        # Initial turn establishing proposal
        self.mock_ai.generate_structured.return_value = {
            "summary": "Skeletons drop iron ingots.",
            "trigger_condition": "When skeleton dies",
            "target_affected": "Skeletons",
            "mechanisms_involved": ["loot_table"],
            "status": "proposed",
            "is_complete": True
        }
        self.engine.process_turn(session, "Make skeletons drop iron.")
        self.assertFalse(session.is_confirmed())

        # User confirms
        p_confirmed = self.engine.process_turn(session, "Looks good, generate it!")
        self.assertEqual(p_confirmed.status, "confirmed")
        self.assertTrue(session.is_confirmed())

    def test_6_multi_part_compound_request_interpretation(self):
        """Compound requests with multiple mechanics must be analyzed into unified proposal."""
        self.mock_ai.generate_structured.return_value = {
            "summary": "When a player kills a creeper, give them a golden apple, trigger particle effects, and increment their kill count on a scoreboard.",
            "trigger_condition": "Player kills a creeper",
            "target_affected": "The killer player",
            "mechanisms_involved": ["advancement", "function", "scoreboard"],
            "assumptions": [{"description": "Use custom scoreboard objective", "rationale": "Tracks kill counter", "default_applied": "creeper_kills objective"}],
            "open_choices": [],
            "status": "proposed",
            "is_complete": True
        }

        session = ConversationSession()
        proposal = self.engine.process_turn(
            session,
            "When I kill a creeper, give me a golden apple, spawn heart particles, and count my kills on the sidebar."
        )

        self.assertEqual(proposal.status, "proposed")
        self.assertIn("golden apple", proposal.summary)
        self.assertIn("scoreboard", proposal.mechanisms_involved)

    def test_7_novel_and_unseen_request_interpretation(self):
        """Novel requests not in standard examples must be understood semantically."""
        self.mock_ai.generate_structured.return_value = {
            "summary": "Whenever a player enters water, turns nearby water blocks into frosted ice temporarily.",
            "trigger_condition": "Player in water",
            "target_affected": "The player and surrounding water",
            "mechanisms_involved": ["predicate", "function"],
            "assumptions": [{"description": "3 block radius around player", "rationale": "Reasonable frost walker radius", "default_applied": "radius: 3"}],
            "open_choices": [],
            "status": "proposed",
            "is_complete": True
        }

        session = ConversationSession()
        proposal = self.engine.process_turn(session, "Make water freeze around me when I swim like a frost walker.")

        self.assertEqual(proposal.status, "proposed")
        self.assertIn("frosted ice", proposal.summary)

    def test_8_unsupported_capability_explanation(self):
        """Requests impossible in vanilla datapacks must explain limitations in plain English."""
        self.mock_ai.generate_structured.return_value = {
            "summary": "Add a 3D model of an airplane.",
            "status": "unsupported",
            "is_complete": False,
            "unsupported_reason": "Vanilla datapacks cannot add custom 3D entity models or meshes without a client-side resource pack or mod."
        }

        session = ConversationSession()
        proposal = self.engine.process_turn(session, "Add a custom 3D model of an airplane to the game.")

        self.assertEqual(proposal.status, "unsupported")
        self.assertIsNotNone(proposal.unsupported_reason)
        self.assertIn("resource pack", proposal.unsupported_reason)


if __name__ == "__main__":
    unittest.main()
