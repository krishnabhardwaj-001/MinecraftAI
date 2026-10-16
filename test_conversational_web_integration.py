"""
test_conversational_web_integration.py - Safe unit and integration tests for Phase 2.

Verifies:
1. Conversation session creation, isolation, and TTL cleanup.
2. Invalidation of stale proposals upon user requirement edits.
3. Enforcement that confirmation cannot trigger generation when choices are open or capability is unsupported.
4. Specification validation and bridge conversion.
5. FastAPI conversational REST endpoints (/api/conversation/session, /message, /confirm).
6. MinecraftPipeline Stage 1 handoff with pre-confirmed understanding.

SAFE EXECUTION:
All tests run with mocked pipeline executions and in-memory test doubles.
Never writes to generated/, never executes real datapack generation, and never launches Minecraft servers.
"""
import time
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from ai.conversation import (
    AssumptionItem,
    ConversationMessage,
    ConversationSession,
    ConversationSessionManager,
    DEFAULT_CONVERSATION_MANAGER,
    ProposedBehavior,
)
from ai.conversational_agent import ConversationalUnderstandingEngine
from ai.specification import SpecificationBridge, ValidationReport
from pipeline.minecraft_pipeline import MinecraftPipeline
from pipeline.models import PipelineResult
from web.app import app


class TestConversationalCore(unittest.TestCase):
    """Verifies core session management and invalidation semantics."""

    def setUp(self):
        self.manager = ConversationSessionManager(ttl_seconds=3600)

    def test_session_creation_and_isolation(self):
        """Sessions must remain strictly isolated by unique session IDs."""
        s1 = self.manager.create_session(version="1.21.11")
        s2 = self.manager.create_session(version="1.21.1")

        self.assertNotEqual(s1.session_id, s2.session_id)
        self.assertEqual(s1.minecraft_version, "1.21.11")
        self.assertEqual(s2.minecraft_version, "1.21.1")

        s1.add_user_message("Give me diamonds")
        self.assertEqual(len(s1.messages), 1)
        self.assertEqual(len(s2.messages), 0)

    def test_session_expiration(self):
        """Sessions older than TTL must be pruned automatically."""
        short_manager = ConversationSessionManager(ttl_seconds=1)
        session = short_manager.create_session()
        sid = session.session_id

        self.assertIsNotNone(short_manager.get_session(sid))
        # Age session beyond TTL
        session.updated_at = time.time() - 10
        self.assertIsNone(short_manager.get_session(sid))

    def test_proposal_invalidation_on_user_edit(self):
        """
        Requirement 5: Edits to requirements must invalidate or update stale proposals.
        A previously confirmed specification must be cleared when the user amends the request.
        """
        session = self.manager.create_session()
        proposal = ProposedBehavior(
            summary="Give 1 diamond when raining",
            trigger_condition="Raining",
            target_affected="All players",
            mechanisms_involved=["command"],
            assumptions=[],
            open_choices=[],
            status="proposed",
            is_complete=True
        )
        session.add_assistant_message("Proposal ready", proposal=proposal)
        self.assertIsNotNone(session.confirm_proposal())
        self.assertTrue(session.is_confirmed())
        self.assertIsNotNone(session.confirmed_specification)

        # User sends a requirement edit
        session.add_user_message("Actually make it drop gold ingots instead")
        self.assertFalse(session.is_confirmed())
        self.assertIsNone(session.confirmed_specification)
        self.assertEqual(session.current_proposal.status, "proposed")

    def test_confirmation_blocked_with_open_choices(self):
        """
        Requirement 5: A confirmation message must not trigger generation unless
        a valid proposal is pending without unresolved choices.
        """
        session = self.manager.create_session()
        proposal = ProposedBehavior(
            summary="Make zombies stronger",
            trigger_condition="Zombie spawn",
            target_affected="Zombies",
            mechanisms_involved=["attribute"],
            assumptions=[],
            open_choices=["Increase max health", "Increase attack damage", "Give armor"],
            status="needs_clarification",
            is_complete=False
        )
        session.add_assistant_message("Please choose an option", proposal=proposal)

        # Attempting to confirm must fail
        spec = session.confirm_proposal()
        self.assertIsNone(spec)
        self.assertFalse(session.is_confirmed())

    def test_confirmation_blocked_for_unsupported_capabilities(self):
        """
        Requirement 6: Unsupported capabilities must be rejected before confirmation or generation.
        """
        session = self.manager.create_session()
        proposal = ProposedBehavior(
            summary="Add a custom 3D dragon model with animated wings",
            trigger_condition="Player spawn",
            target_affected="Dragon",
            mechanisms_involved=[],
            status="unsupported",
            unsupported_reason="Custom 3D models require client-side mods or resource packs.",
            is_complete=False
        )
        session.add_assistant_message("Unsupported", proposal=proposal)

        spec = session.confirm_proposal()
        self.assertIsNone(spec)
        self.assertFalse(session.is_confirmed())

        # Bridge validation must also reject
        bridge = SpecificationBridge()
        report = bridge.validate_capabilities(proposal)
        self.assertFalse(report.is_supported)


class TestConversationalAgentTurn(unittest.TestCase):
    """Verifies ConversationalUnderstandingEngine turn processing with mocked LLM."""

    def test_process_turn_with_assumptions(self):
        """Assumptions and sensible defaults must be retained and structured."""
        mock_provider = MagicMock()
        mock_provider.generate_structured.return_value = {
            "summary": "Give players speed when running on ice",
            "trigger_condition": "Player standing on ice",
            "target_affected": "All players",
            "mechanisms_involved": ["attribute_modifier"],
            "assumptions": [
                {
                    "description": "Speed II applied",
                    "rationale": "Standard sensible movement buff",
                    "default_applied": "effect give @s speed 1 1 true"
                }
            ],
            "open_choices": [],
            "status": "proposed",
            "is_complete": True,
            "confirmation_prompt": "Does Speed II match what you want?",
            "raw_requirements": [
                {
                    "subject": "player",
                    "intent": "grant speed on ice",
                    "conditions": ["block is packed_ice or blue_ice"],
                    "constraints": []
                }
            ]
        }

        engine = ConversationalUnderstandingEngine(ai_provider=mock_provider, version="1.21.11")
        session = ConversationSession(minecraft_version="1.21.11")

        proposal = engine.process_turn(session, "Make me faster when on ice")
        self.assertEqual(proposal.summary, "Give players speed when running on ice")
        self.assertEqual(len(proposal.assumptions), 1)
        self.assertEqual(proposal.assumptions[0].description, "Speed II applied")
        self.assertEqual(proposal.assumptions[0].rationale, "Standard sensible movement buff")
        self.assertTrue(proposal.is_complete)
        self.assertEqual(proposal.status, "proposed")


class TestPipelineSpecificationHandoff(unittest.TestCase):
    """Verifies MinecraftPipeline Stage 1 bypass with pre-confirmed understanding."""

    def test_pipeline_run_with_pre_confirmed_understanding(self):
        """When pre-confirmed understanding is supplied, Stage 1 AI understanding is bypassed."""
        mock_understanding_engine = MagicMock()
        mock_ai = MagicMock()

        pipeline = MinecraftPipeline(
            version="1.21.11",
            understanding_engine=mock_understanding_engine,
            ai_provider=mock_ai,
            verbose=False
        )

        pre_confirmed = {
            "status": "understood",
            "minecraft_version": "1.21.11",
            "edition": "Java",
            "understood_request": "Skeletons drop iron ingots",
            "requirements": [
                {
                    "subject": "skeleton",
                    "intent": "drop iron ingot on death",
                    "conditions": ["entity_killed"],
                    "constraints": []
                }
            ],
            "clarification": None,
            "missing_information": []
        }

        # Mock downstream planner and RAG so test remains safe and purely in-memory
        with patch("pipeline.minecraft_pipeline.retrieve_minecraft_context") as mock_rag, \
             patch("pipeline.minecraft_pipeline.create_plan") as mock_planner:
            mock_rag.return_value = {"knowledge": {}}
            mock_planner.return_value = {
                "status": "needs_clarification",
                "clarifications": ["Clarification test"]
            }

            result = pipeline.run(
                request="Skeletons drop iron",
                create_zip=False,
                understanding=pre_confirmed
            )

            # Stage 1 understanding engine must NOT have been called
            mock_understanding_engine.understand.assert_not_called()
            # Stage 2 RAG and Stage 3 Planner were invoked with the pre_confirmed dict
            mock_rag.assert_called_once_with(pre_confirmed, version="1.21.11")
            mock_planner.assert_called_once()
            self.assertEqual(result.status, "needs_clarification")

    def test_pipeline_run_with_unsupported_specification_halts_immediately(self):
        """An unsupported specification must halt at Stage 1 with status 'unsupported'."""
        pipeline = MinecraftPipeline(version="1.21.11", verbose=False)
        unsupported_und = {
            "status": "unsupported",
            "minecraft_version": "1.21.11",
            "edition": "Java",
            "understood_request": "Custom 3D model",
            "requirements": [],
            "clarification": {
                "reason": "Datapacks cannot create custom 3D models."
            }
        }

        result = pipeline.run(
            request="Custom 3D model",
            create_zip=False,
            understanding=unsupported_und
        )
        self.assertEqual(result.status, "unsupported")
        self.assertIn("Datapacks cannot create custom 3D models.", result.errors[0])


class TestConversationalWebEndpoints(unittest.TestCase):
    """Verifies FastAPI conversational endpoints with TestClient."""

    def setUp(self):
        self.client = TestClient(app)

    def test_create_and_get_session(self):
        """POST /api/conversation/session and GET /api/conversation/session/{id}."""
        res = self.client.post("/api/conversation/session", json={"minecraft_version": "1.21.11"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("session_id", data)
        self.assertEqual(data["minecraft_version"], "1.21.11")

        sid = data["session_id"]
        get_res = self.client.get(f"/api/conversation/session/{sid}")
        self.assertEqual(get_res.status_code, 200)
        get_data = get_res.json()
        self.assertEqual(get_data["session_id"], sid)
        self.assertFalse(get_data["is_confirmed"])

    def test_message_turn_and_proposal_review(self):
        """POST /api/conversation/message processes user turns."""
        sess = DEFAULT_CONVERSATION_MANAGER.create_session(version="1.21.11")
        sid = sess.session_id

        # Mock ConversationalUnderstandingEngine.process_turn for safe deterministic testing
        with patch.object(ConversationalUnderstandingEngine, "process_turn") as mock_turn:
            mock_turn.return_value = ProposedBehavior(
                summary="Creeper drops emeralds",
                trigger_condition="On death",
                target_affected="Creeper",
                mechanisms_involved=["loot_table"],
                assumptions=[
                    AssumptionItem(
                        description="1 to 3 emeralds",
                        rationale="Standard mob drop quantity",
                        default_applied="Uniform count 1-3"
                    )
                ],
                open_choices=[],
                status="proposed",
                is_complete=True
            )

            res = self.client.post("/api/conversation/message", json={
                "session_id": sid,
                "message": "Make creepers drop emeralds"
            })
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["proposal"]["summary"], "Creeper drops emeralds")
            self.assertTrue(data["can_generate"])
            self.assertEqual(len(data["proposal"]["assumptions"]), 1)

    def test_confirm_rejected_without_proposal(self):
        """POST /api/conversation/confirm must return 400 if no proposal exists."""
        sess = DEFAULT_CONVERSATION_MANAGER.create_session(version="1.21.11")
        res = self.client.post("/api/conversation/confirm", json={"session_id": sess.session_id})
        self.assertEqual(res.status_code, 400)
        self.assertIn("No active proposal", res.json()["detail"])

    def test_confirm_rejected_with_open_choices(self):
        """POST /api/conversation/confirm must return 400 if open choices exist."""
        sess = DEFAULT_CONVERSATION_MANAGER.create_session(version="1.21.11")
        sess.current_proposal = ProposedBehavior(
            summary="Ambiguous request",
            open_choices=["Option A", "Option B"],
            status="needs_clarification",
            is_complete=False
        )

        res = self.client.post("/api/conversation/confirm", json={"session_id": sess.session_id})
        self.assertEqual(res.status_code, 400)
        self.assertIn("incomplete", res.json()["detail"].lower())

    def test_confirm_rejected_for_unsupported_capability(self):
        """POST /api/conversation/confirm must return 400 for unsupported capabilities."""
        sess = DEFAULT_CONVERSATION_MANAGER.create_session(version="1.21.11")
        sess.current_proposal = ProposedBehavior(
            summary="Add custom 3D model with custom texture",
            open_choices=[],
            status="unsupported",
            unsupported_reason="Requires resource pack.",
            is_complete=True
        )

        res = self.client.post("/api/conversation/confirm", json={"session_id": sess.session_id})
        self.assertEqual(res.status_code, 400)
        self.assertIn("unsupported", res.json()["detail"].lower())

    def test_confirm_success_with_mocked_pipeline(self):
        """
        POST /api/conversation/confirm must execute generation handoff
        when a valid complete proposal is confirmed.
        """
        sess = DEFAULT_CONVERSATION_MANAGER.create_session(version="1.21.11")
        sess.current_proposal = ProposedBehavior(
            summary="Skeletons drop iron ingots",
            trigger_condition="Skeleton death",
            target_affected="Skeleton",
            mechanisms_involved=["loot_table"],
            assumptions=[],
            open_choices=[],
            status="proposed",
            is_complete=True,
            raw_requirements=[{
                "subject": "skeleton",
                "intent": "drop iron ingot",
                "conditions": ["death"],
                "constraints": []
            }]
        )

        # Mock _execute_pipeline_task so no real filesystem generation occurs
        mock_result = PipelineResult(
            status="success",
            verification_status="verified",
            minecraft_version="1.21.11",
            original_request="Skeletons drop iron ingots",
            final_datapack_path="generated/test_pack",
            final_zip_path=None,
            execution_summary="Mocked verification passed."
        )

        with patch("web.app._execute_pipeline_task") as mock_exec:
            mock_exec.return_value = mock_result

            res = self.client.post("/api/conversation/confirm", json={"session_id": sess.session_id})
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["status"], "success")
            self.assertTrue(data["is_success"])
            self.assertEqual(data["original_request"], "Skeletons drop iron ingots")
            mock_exec.assert_called_once()


if __name__ == "__main__":
    unittest.main()
