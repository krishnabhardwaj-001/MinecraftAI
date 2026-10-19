"""
Unit tests for B9: Authoritative 8-stage pipeline tracker.
Verifies that _compute_pipeline_stages and the API return genuine per-stage states
instead of faking stage completions on failure.
"""

import unittest
from unittest.mock import MagicMock
from pipeline.models import PipelineResult
from generator.models import GenerationResult
from validator.models import ValidationResult
from qa.models import QAResult, QACategory, QASeverity, QAFinding, IntentVerificationResult
from web.app import _compute_pipeline_stages, _format_pipeline_result


class TestAuditB9StageTracker(unittest.TestCase):

    def test_stage_1_understanding_failure(self):
        """When stage 1 fails, only stage 0 is failed; subsequent stages must NOT be marked done."""
        result = PipelineResult(
            status="error",
            failed_stage="understanding",
            minecraft_version="1.21.11",
            original_request="Make me a spaceship",
            errors=["AI Understanding failed: connection error"]
        )
        stages = _compute_pipeline_stages(result)
        self.assertEqual(len(stages), 8)
        self.assertEqual(stages[0]["status"], "failed")
        self.assertEqual(stages[0]["name"], "Understanding")

        # Crucial: none of the downstream stages should be 'done'
        for i in range(1, 8):
            self.assertNotEqual(
                stages[i]["status"],
                "done",
                f"Stage {i} ({stages[i]['name']}) should not be marked done when Stage 1 failed"
            )

    def test_stage_2_retrieval_failure(self):
        """When stage 2 fails, stage 0 is passed, stage 1 is failed, stages 2-7 are aborted/not done."""
        result = PipelineResult(
            status="error",
            failed_stage="retrieval",
            minecraft_version="1.21.11",
            original_request="Spawn a custom mob",
            understanding={"intent": "custom_mob", "requirements": [{"action": "spawn"}]},
            errors=["Knowledge retrieval failed: version registry error"]
        )
        stages = _compute_pipeline_stages(result)
        self.assertEqual(len(stages), 8)
        self.assertEqual(stages[0]["status"], "done")
        self.assertEqual(stages[1]["status"], "failed")
        self.assertEqual(stages[1]["name"], "RAG Retrieval")

        for i in range(2, 8):
            self.assertNotEqual(
                stages[i]["status"],
                "done",
                f"Stage {i} ({stages[i]['name']}) should not be marked done when Stage 2 failed"
            )

    def test_stage_6_qa_failure(self):
        """When Autonomous QA fails (stage index 5), stages 0-4 are done, stage 5 is failed, stages 6-7 aborted."""
        val_mock = ValidationResult(status="valid", target_path="generated/test_pack", errors=[], warnings=[], checks=[])
        gen_mock = GenerationResult(
            datapack_name="test_pack",
            datapack_path="generated/test_pack",
            files_generated=["pack.mcmeta", "data/test/function/main.mcfunction"]
        )
        qa_mock = QAResult(
            status="failed",
            summary="QA Failed due to syntax error",
            findings=[
                QAFinding(
                    id="QA-001",
                    category=QACategory.COMMAND_SEMANTICS,
                    severity=QASeverity.ERROR,
                    problem="Invalid command",
                    explanation="Syntax error",
                    expected_behavior="Valid syntax"
                )
            ]
        )
        result = PipelineResult(
            status="verification_failed",
            verification_status="qa_failed",
            failed_stage="qa_review",
            minecraft_version="1.21.11",
            original_request="Test QA Failure",
            understanding={"intent": "test", "requirements": [{"action": "test"}]},
            context={"knowledge": {}},
            plan={"summary": "test plan"},
            generation=gen_mock,
            validation=val_mock,
            qa_result=qa_mock,
            errors=["QA Failure: Invalid command"]
        )
        stages = _compute_pipeline_stages(result)
        self.assertEqual(len(stages), 8)
        self.assertEqual(stages[0]["status"], "done")  # Understanding
        self.assertEqual(stages[1]["status"], "done")  # RAG Retrieval
        self.assertEqual(stages[2]["status"], "done")  # Planning
        self.assertEqual(stages[3]["status"], "done")  # Generator
        self.assertEqual(stages[4]["status"], "done")  # Validation
        self.assertEqual(stages[5]["status"], "failed")  # Autonomous QA
        self.assertIn("QA Failed", stages[5]["message"])
        self.assertNotEqual(stages[6]["status"], "done")  # Intent Verification aborted
        self.assertNotEqual(stages[7]["status"], "done")  # READY Gate aborted

    def test_full_success_stages(self):
        """When pipeline succeeds completely, all 8 stages are done."""
        val_mock = ValidationResult(status="valid", target_path="generated/test_pack", errors=[], warnings=[], checks=[])
        gen_mock = GenerationResult(
            datapack_name="test_pack",
            datapack_path="generated/test_pack",
            files_generated=["pack.mcmeta"]
        )
        qa_mock = QAResult(status="passed", summary="QA Passed Cleanly", findings=[])
        intent_mock = IntentVerificationResult(matches_intent=True, reasoning="Matches intent perfectly")
        result = PipelineResult(
            status="success",
            minecraft_version="1.21.11",
            original_request="Valid prompt",
            understanding={"intent": "valid", "requirements": []},
            context={"knowledge": {}},
            plan={"summary": "Plan"},
            generation=gen_mock,
            validation=val_mock,
            qa_result=qa_mock,
            intent_verification=intent_mock,
            final_zip_path="generated/test.zip"
        )
        formatted = _format_pipeline_result(result)
        self.assertIn("stages", formatted)
        stages = formatted["stages"]
        self.assertEqual(len(stages), 8)
        for i, s in enumerate(stages):
            self.assertEqual(s["status"], "done", f"Stage {i} ({s['name']}) should be done on success")


if __name__ == "__main__":
    unittest.main()
