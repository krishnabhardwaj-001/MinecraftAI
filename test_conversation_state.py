"""
test_conversation_state.py - Unit tests for Conversational State & Turn Manager.
Verifies session creation, message tracking, turn management, proposal confirmation,
TTL expiration, and session isolation.
"""
import time
import unittest

from ai.conversation import (
    AssumptionItem,
    ConversationMessage,
    ConversationSession,
    ConversationSessionManager,
    ProposedBehavior,
)


class TestConversationState(unittest.TestCase):
    """Verifies ConversationSession and ConversationSessionManager behavior."""

    def test_session_creation_and_defaults(self):
        """Verify new session has unique ID, default version, and empty history."""
        session = ConversationSession(minecraft_version="1.21.11")
        self.assertTrue(bool(session.session_id))
        self.assertEqual(session.minecraft_version, "1.21.11")
        self.assertEqual(len(session.messages), 0)
        self.assertEqual(len(session.turns), 0)
        self.assertIsNone(session.current_proposal)
        self.assertFalse(session.is_confirmed())

    def test_message_history_and_formatting(self):
        """Verify user and assistant messages append correctly and format into text."""
        session = ConversationSession()
        session.add_user_message("Make every zombie drop diamonds.")
        session.add_assistant_message("I propose that zombies drop 1 diamond upon death.")

        self.assertEqual(len(session.messages), 2)
        self.assertEqual(session.get_latest_user_message_text(), "Make every zombie drop diamonds.")

        history = session.get_formatted_history()
        self.assertIn("User: Make every zombie drop diamonds.", history)
        self.assertIn("Assistant: I propose that zombies drop 1 diamond upon death.", history)

    def test_turn_tracking_and_proposal_association(self):
        """Verify adding an assistant message with a proposal records a structured turn."""
        session = ConversationSession()
        session.add_user_message("Make me faster.")

        proposal = ProposedBehavior(
            summary="Increase player movement speed by 50% permanently.",
            trigger_condition="Continuously while in the world",
            target_affected="The player",
            mechanisms_involved=["attribute_modifier"],
            assumptions=[
                AssumptionItem(
                    description="50% movement speed increase",
                    rationale="Noticeable speed boost without camera warping",
                    default_applied="+50% speed attribute modifier"
                )
            ],
            status="proposed",
            is_complete=True
        )

        session.add_assistant_message("Here is the proposed speed increase.", proposal=proposal)

        self.assertEqual(len(session.turns), 1)
        turn = session.turns[0]
        self.assertEqual(turn.turn_index, 1)
        self.assertEqual(turn.user_message, "Make me faster.")
        self.assertEqual(turn.proposed_behavior.summary, proposal.summary)
        self.assertEqual(session.current_proposal.summary, proposal.summary)

    def test_proposal_confirmation_lifecycle(self):
        """Verify proposal confirmation transitions state and locks the specification."""
        session = ConversationSession()
        session.add_user_message("When it rains, give me a diamond.")

        proposal = ProposedBehavior(
            summary="Give the player one diamond when rain starts.",
            trigger_condition="When weather changes to rain",
            target_affected="@s",
            mechanisms_involved=["predicate", "function"],
            status="proposed",
            is_complete=True
        )
        session.add_assistant_message("Here is the proposal", proposal=proposal)
        self.assertFalse(session.is_confirmed())

        # Confirm the proposal
        spec = session.confirm_proposal()
        self.assertIsNotNone(spec)
        self.assertTrue(session.is_confirmed())
        self.assertEqual(session.current_proposal.status, "confirmed")
        self.assertEqual(spec["summary"], "Give the player one diamond when rain starts.")

    def test_incomplete_proposal_cannot_be_confirmed(self):
        """Verify an incomplete proposal (waiting on open choices) cannot be confirmed."""
        session = ConversationSession()
        session.add_user_message("Make zombies drop something cool.")

        proposal = ProposedBehavior(
            summary="Modify zombie drops.",
            open_choices=["Diamonds and emeralds", "Weapons and armor"],
            status="needs_clarification",
            is_complete=False
        )
        session.add_assistant_message("Choose a style:", proposal=proposal)

        self.assertIsNone(session.confirm_proposal())
        self.assertFalse(session.is_confirmed())

    def test_session_manager_crud_and_ttl(self):
        """Verify thread-safe session manager creation, retrieval, and TTL cleanup."""
        manager = ConversationSessionManager(ttl_seconds=1)
        session = manager.create_session(version="1.21.1")
        sid = session.session_id

        # Retrieve session
        retrieved = manager.get_session(sid)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.session_id, sid)
        self.assertEqual(retrieved.minecraft_version, "1.21.1")

        # Session isolation: second session has distinct ID
        session2 = manager.create_session(version="1.21.11")
        self.assertNotEqual(session.session_id, session2.session_id)

        # Wait for TTL expiration
        time.sleep(1.1)
        purged = manager.cleanup_expired()
        self.assertGreaterEqual(purged, 1)
        self.assertIsNone(manager.get_session(sid))


if __name__ == "__main__":
    unittest.main()
