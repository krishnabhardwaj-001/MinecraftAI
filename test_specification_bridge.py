"""
test_specification_bridge.py - Unit tests for Implementation-Neutral Specification Bridge.

Verifies:
1. Capability validation for vanilla datapack boundaries.
2. Conversion of confirmed proposals to downstream-compatible understanding schemas.
3. Injection of confirmed assumptions as structured requirement details.
4. Session confirmation enforcement.
"""
import unittest

from ai.conversation import (
    AssumptionItem,
    ConversationSession,
    ProposedBehavior,
)
from ai.specification import SpecificationBridge


class TestSpecificationBridge(unittest.TestCase):
    """Verifies SpecificationBridge validation and translation contracts."""

    def setUp(self):
        self.bridge = SpecificationBridge()

    def test_1_supported_datapack_capabilities_validation(self):
        """Standard gameplay proposals must pass capability validation."""
        proposal = ProposedBehavior(
            summary="Skeletons drop iron ingots on death.",
            trigger_condition="When skeleton dies",
            target_affected="Skeletons",
            mechanisms_involved=["loot_table"],
            status="proposed",
            is_complete=True
        )
        report = self.bridge.validate_capabilities(proposal)
        self.assertTrue(report.is_supported)
        self.assertIsNone(report.unsupported_reason)

    def test_2_unsupported_client_side_concepts_detection(self):
        """Concepts requiring client mods (3D models, shaders, textures) must fail capability validation."""
        proposal = ProposedBehavior(
            summary="Add a custom 3D model of a dragon and apply a custom texture.",
            status="proposed",
            is_complete=True
        )
        report = self.bridge.validate_capabilities(proposal)
        self.assertFalse(report.is_supported)
        self.assertIn("resource pack", report.unsupported_reason.lower())

    def test_3_unsupported_networking_concept_detection(self):
        """External HTTP requests must be rejected as outside server datapack sandbox."""
        proposal = ProposedBehavior(
            summary="Make an external http request to a Discord webhook on player join.",
            status="proposed",
            is_complete=True
        )
        report = self.bridge.validate_capabilities(proposal)
        self.assertFalse(report.is_supported)
        self.assertIn("sandboxed", report.unsupported_reason.lower())

    def test_4_convert_confirmed_proposal_to_understanding_result(self):
        """Confirmed proposal must convert into a valid understanding dictionary schema."""
        proposal = ProposedBehavior(
            summary="Increases movement speed by 50% permanently.",
            trigger_condition="Continuously in world",
            target_affected="Player",
            mechanisms_involved=["attribute_modifier"],
            assumptions=[
                AssumptionItem(
                    description="50% speed boost",
                    rationale="Avoids camera distortion",
                    default_applied="+50% speed"
                )
            ],
            status="confirmed",
            is_complete=True,
            raw_requirements=[
                {
                    "subject": "Player",
                    "target": "@s",
                    "intent": "Increase movement speed by 50%",
                    "conditions": [],
                    "constraints": []
                }
            ]
        )

        result = self.bridge.convert_to_understanding_result(proposal, version="1.21.11")

        self.assertEqual(result["status"], "understood")
        self.assertEqual(result["minecraft_version"], "1.21.11")
        self.assertEqual(result["understood_request"], proposal.summary)
        self.assertIsNone(result["clarification"])
        self.assertEqual(len(result["requirements"]), 1)

        req = result["requirements"][0]
        self.assertEqual(req["subject"], "Player")
        # Check that assumptions are injected as details
        self.assertGreaterEqual(len(req.get("details", [])), 1)
        self.assertEqual(req["details"][0]["value"], "+50% speed")

    def test_5_session_confirmation_enforcement(self):
        """Unconfirmed session must not be convertible into a specification."""
        session = ConversationSession()
        session.add_user_message("Make me fast.")
        proposal = ProposedBehavior(
            summary="Increase speed by 50%.",
            status="proposed",
            is_complete=True
        )
        session.add_assistant_message("Proposal", proposal=proposal)

        # 1. Unconfirmed session fails
        success, spec, err = self.bridge.convert_session_to_specification(session)
        self.assertFalse(success)
        self.assertIsNone(spec)
        self.assertIn("not been confirmed", err)

        # 2. Confirmed session succeeds
        session.confirm_proposal()
        success, spec, err = self.bridge.convert_session_to_specification(session)
        self.assertTrue(success)
        self.assertIsNotNone(spec)
        self.assertEqual(spec["status"], "understood")


if __name__ == "__main__":
    unittest.main()
