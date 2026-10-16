"""
test_phase2_1_refinements.py - Unit tests for Phase 2.1 refinements.

Verifies:
1. Multi-requirement assumption association:
   - Single requirement: attached to reqs[0]["details"].
   - Explicit reference: attached via target_requirement_index.
   - Semantic matching: attached only when match is unambiguous.
   - Ambiguous / Unmatched: preserved as global context (result["assumptions"]) and not attached to reqs.
2. Bounded conversation history:
   - Trims complete conversational turns rather than arbitrary messages.
   - Preserves Turn 0 (Initial User Goal) and recent sliding window.
   - Preserves active proposals, assumptions, choices, and confirmation state.
   - Re-synchronizes messages to stay consistent with retained turns.
   - Invalidates stale confirmation when new user message arrives after trimming.
"""
import unittest
from ai.conversation import (
    AssumptionItem,
    ConversationMessage,
    ConversationSession,
    ProposedBehavior,
)
from ai.specification import SpecificationBridge


class TestAssumptionAssociation(unittest.TestCase):
    """Verifies targeted assumption association in SpecificationBridge."""

    def setUp(self):
        self.bridge = SpecificationBridge()

    def test_single_requirement_assumption_association(self):
        """Single requirement proposals must attach all assumptions to reqs[0]."""
        proposal = ProposedBehavior(
            summary="Make creepers drop diamonds",
            status="confirmed",
            is_complete=True,
            raw_requirements=[{
                "subject": "creeper",
                "target": "creeper",
                "intent": "drop diamonds"
            }],
            assumptions=[
                AssumptionItem(
                    description="1 to 3 diamonds",
                    rationale="Sensible drop quantity",
                    default_applied="uniform 1-3"
                )
            ]
        )
        res = self.bridge.convert_to_understanding_result(proposal, version="1.21.11")
        self.assertEqual(len(res["requirements"]), 1)
        req0 = res["requirements"][0]
        self.assertIn("details", req0)
        self.assertEqual(len(req0["details"]), 1)
        self.assertEqual(req0["details"][0]["value"], "uniform 1-3")
        self.assertNotIn("assumptions", res)

    def test_multi_requirement_explicit_matching(self):
        """Assumptions with target_requirement_index must attach to the targeted requirement."""
        proposal = ProposedBehavior(
            summary="Custom mobs: Skeleton drops iron, Zombie has Speed II",
            status="confirmed",
            is_complete=True,
            raw_requirements=[
                {"subject": "skeleton", "intent": "drop iron"},
                {"subject": "zombie", "intent": "gain speed"}
            ],
            assumptions=[
                AssumptionItem(
                    description="Speed II amplifier",
                    rationale="Standard buff",
                    default_applied="amplifier 1",
                    target_requirement_index=1
                )
            ]
        )
        res = self.bridge.convert_to_understanding_result(proposal, version="1.21.11")
        self.assertEqual(len(res["requirements"]), 2)
        # Requirement 0 (skeleton) must NOT have the Speed assumption
        self.assertEqual(len(res["requirements"][0].get("details", [])), 0)
        # Requirement 1 (zombie) MUST have the Speed assumption
        self.assertEqual(len(res["requirements"][1].get("details", [])), 1)
        self.assertEqual(res["requirements"][1]["details"][0]["name"], "Speed II amplifier")
        self.assertNotIn("assumptions", res)

    def test_multi_requirement_unambiguous_semantic_matching(self):
        """Assumptions matching exactly one requirement subject or target must attach to that requirement."""
        proposal = ProposedBehavior(
            summary="Custom drops for skeletons and creepers",
            status="confirmed",
            is_complete=True,
            raw_requirements=[
                {"subject": "skeleton", "target": "skeleton", "intent": "drop bones"},
                {"subject": "creeper", "target": "creeper", "intent": "drop gunpowder"}
            ],
            assumptions=[
                AssumptionItem(
                    description="Creeper drops 2x gunpowder",
                    rationale="Enhanced explosive loot",
                    default_applied="count 2",
                    target_subject="creeper"
                )
            ]
        )
        res = self.bridge.convert_to_understanding_result(proposal, version="1.21.11")
        self.assertEqual(len(res["requirements"]), 2)
        # Skeleton requirement must have 0 details
        self.assertEqual(len(res["requirements"][0].get("details", [])), 0)
        # Creeper requirement must have the matched detail
        self.assertEqual(len(res["requirements"][1].get("details", [])), 1)
        self.assertEqual(res["requirements"][1]["details"][0]["value"], "count 2")
        self.assertNotIn("assumptions", res)

    def test_multi_requirement_ambiguous_and_unmatched_assumptions(self):
        """
        Ambiguous or unmatched assumptions must NOT be attached to all requirements.
        They must be preserved as global context in understanding['assumptions'].
        """
        proposal = ProposedBehavior(
            summary="Custom world rules: Skeletons drop iron, Zombies burn in day",
            status="confirmed",
            is_complete=True,
            raw_requirements=[
                {"subject": "skeleton", "intent": "drop iron"},
                {"subject": "zombie", "intent": "burn in daylight"}
            ],
            assumptions=[
                # Unmatched assumption (applies to world / general environment)
                AssumptionItem(
                    description="Keep inventory enabled",
                    rationale="Casual gameplay rule",
                    default_applied="gamerule keepInventory true"
                ),
                # Ambiguous assumption matching both mobs
                AssumptionItem(
                    description="Undead mobs burn in fire",
                    rationale="Affects both skeleton and zombie",
                    default_applied="fire vulnerability",
                    target_subject="all undead"
                )
            ]
        )
        res = self.bridge.convert_to_understanding_result(proposal, version="1.21.11")
        self.assertEqual(len(res["requirements"]), 2)
        # Neither requirement should have these ambiguous/unmatched assumptions attached
        self.assertEqual(len(res["requirements"][0].get("details", [])), 0)
        self.assertEqual(len(res["requirements"][1].get("details", [])), 0)

        # Preserved as global context
        self.assertIn("assumptions", res)
        self.assertEqual(len(res["assumptions"]), 2)
        self.assertEqual(res["assumptions"][0]["name"], "Keep inventory enabled")
        self.assertEqual(res["assumptions"][0]["scope"], "global")
        self.assertEqual(res["assumptions"][1]["name"], "Undead mobs burn in fire")
        self.assertEqual(res["assumptions"][1]["scope"], "global")


class TestBoundedConversationHistory(unittest.TestCase):
    """Verifies complete-turn history trimming and context preservation."""

    def test_bounded_history_trims_complete_turns(self):
        """When turns exceed max_turns, complete turns are trimmed while preserving Turn 0 and recent window."""
        session = ConversationSession(max_turns=5)

        for i in range(1, 11):
            session.add_user_message(f"User turn {i}")
            prop = ProposedBehavior(
                summary=f"Cumulative proposal after turn {i}",
                status="proposed",
                is_complete=True
            )
            session.add_assistant_message(f"Assistant turn {i}", proposal=prop)

        # Must have exactly max_turns = 5
        self.assertEqual(len(session.turns), 5)
        # Message count must stay synchronized (2 messages per turn = 10)
        self.assertEqual(len(session.messages), 10)

        # Turn 0 must be preserved (Turn 1 initial goal)
        self.assertEqual(session.turns[0].turn_index, 1)
        self.assertEqual(session.turns[0].user_message, "User turn 1")
        self.assertEqual(session.turns[0].assistant_response, "Assistant turn 1")

        # Recent turns must be turns 7, 8, 9, 10
        recent_indexes = [t.turn_index for t in session.turns[1:]]
        self.assertEqual(recent_indexes, [7, 8, 9, 10])

        # Messages must strictly match the retained turns
        self.assertEqual(session.messages[0].content, "User turn 1")
        self.assertEqual(session.messages[1].content, "Assistant turn 1")
        self.assertEqual(session.messages[-2].content, "User turn 10")
        self.assertEqual(session.messages[-1].content, "Assistant turn 10")

    def test_history_trimming_preserves_active_proposal_and_confirmed_specification(self):
        """Trimming history must not mutate or clear the active proposal or confirmed spec."""
        session = ConversationSession(max_turns=3)

        # Turn 1
        session.add_user_message("Make creepers drop diamonds.")
        p1 = ProposedBehavior(
            summary="Creepers drop diamonds",
            status="proposed",
            is_complete=True
        )
        session.add_assistant_message("Proposal ready", proposal=p1)

        # Turn 2
        session.add_user_message("Add 1 to 3 count.")
        p2 = ProposedBehavior(
            summary="Creepers drop 1-3 diamonds",
            status="proposed",
            is_complete=True,
            assumptions=[AssumptionItem(description="1-3 diamonds", rationale="count", default_applied="1-3")]
        )
        session.add_assistant_message("Proposal updated", proposal=p2)

        # Confirm proposal
        spec = session.confirm_proposal()
        self.assertIsNotNone(spec)
        self.assertTrue(session.is_confirmed())
        self.assertIsNotNone(session.confirmed_specification)

        # Turn 3
        p3 = session.current_proposal.model_copy()
        session.add_assistant_message("Confirmation acknowledged", proposal=p3)

        # Turn 4 (triggers trimming with max_turns=3)
        p4 = session.current_proposal.model_copy()
        session.add_assistant_message("Ready to build", proposal=p4)

        # History trimmed to 3 turns
        self.assertEqual(len(session.turns), 3)
        # Active proposal and confirmed specification MUST remain intact
        self.assertTrue(session.is_confirmed())
        self.assertIsNotNone(session.confirmed_specification)
        self.assertEqual(session.current_proposal.summary, "Creepers drop 1-3 diamonds")
        self.assertEqual(len(session.current_proposal.assumptions), 1)

    def test_new_user_message_after_trimming_invalidates_confirmation(self):
        """New user messages after trimming must still invalidate confirmed specifications."""
        session = ConversationSession(max_turns=3)

        for i in range(1, 5):
            session.add_user_message(f"Msg {i}")
            p = ProposedBehavior(summary=f"Prop {i}", status="proposed", is_complete=True)
            session.add_assistant_message(f"Resp {i}", proposal=p)

        # Confirm
        session.confirm_proposal()
        self.assertTrue(session.is_confirmed())

        # New user message edits requirements
        session.add_user_message("Actually change everything to gold.")
        self.assertFalse(session.is_confirmed())
        self.assertIsNone(session.confirmed_specification)
        self.assertEqual(session.current_proposal.status, "proposed")

    def test_get_formatted_history_with_anchored_baseline(self):
        """get_formatted_history must annotate pruned dialogue and display initial goal and baseline."""
        session = ConversationSession(max_turns=3)
        for i in range(1, 6):
            session.add_user_message(f"Goal {i}")
            p = ProposedBehavior(summary=f"Summary {i}", status="proposed", is_complete=True)
            session.add_assistant_message(f"Response {i}", proposal=p)

        formatted = session.get_formatted_history()
        self.assertIn("User [Initial Goal]: Goal 1", formatted)
        self.assertIn("[Note: Intermediate turns compacted", formatted)
        self.assertIn("Goal 5", formatted)


if __name__ == "__main__":
    unittest.main()
