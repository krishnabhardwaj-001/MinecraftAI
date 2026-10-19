"""
Unit tests for B16: READY gate structural validation enforcement and repair info preservation.

Verifies:
1. Structural validity is a hard requirement for READY regardless of create_zip=False.
   An invalid datapack directory cannot pass the READY gate even when create_zip=False.
2. Failure results in Stage 7 (Intent Verification) and Stage 8 (Final Verification)
   contain repair information (result.repair is not None).
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from generator.models import GenerationResult
from pipeline.minecraft_pipeline import MinecraftPipeline
from pipeline.models import PipelineResult
from qa.models import IntentVerificationResult, QAResult
from qa.runtime import RuntimeTestResult, RuntimeTestMode
from validator.models import ValidationIssue, ValidationResult


class TestAuditB16ReadyGate(unittest.TestCase):

    def test_ready_gate_fails_on_structurally_invalid_datapack_with_create_zip_false(self):
        """Even with create_zip=False, an invalid datapack is rejected at Stage 8 and NOT marked success."""
        pipeline = MinecraftPipeline(ai_provider=MagicMock(), verbose=False)

        mock_plan = {"datapack_name": "test_pack", "status": "planned", "files": []}

        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_dir = Path(tmp_dir) / "test_pack"
            pack_dir.mkdir(parents=True)

            mock_gen = GenerationResult(
                datapack_name="test_pack",
                datapack_path=pack_dir,
                zip_path=None,
                status="success"
            )
            pipeline.generator = MagicMock()
            pipeline.generator.generate.return_value = mock_gen

            # First call (Stage 5) returns valid; Second call (Stage 8 READY gate) returns invalid
            valid_val = ValidationResult(status="valid", target_path=str(pack_dir), errors=[])
            invalid_val = ValidationResult(
                status="invalid",
                target_path=str(pack_dir),
                errors=[ValidationIssue(level="error", code="MISSING_MCMETA", message="pack.mcmeta missing")]
            )
            pipeline.validator = MagicMock()
            pipeline.validator.validate.side_effect = [valid_val, invalid_val]

            # QA review passes
            mock_qa = QAResult(
                status="passed",
                summary="Clean review",
                findings=[],
                intent_verification=IntentVerificationResult(
                    matches_intent=True, reasoning="Matches intent", confidence=1.0
                )
            )
            pipeline.qa_reviewer = MagicMock()
            pipeline.qa_reviewer.review.return_value = mock_qa

            dummy_understanding = {
                "user_intent": "Make creepers drop diamonds",
                "primary_mechanism": "loot_table",
                "requirements": ["modify creeper loot table"]
            }

            with patch("pipeline.minecraft_pipeline.create_plan", return_value=mock_plan):
                res = pipeline.run("Make creepers drop diamonds", create_zip=False, understanding=dummy_understanding)

            # Must NOT be marked success!
            self.assertFalse(res.is_success)
            self.assertEqual(res.status, "verification_failed")
            self.assertEqual(res.failed_stage, "final_verification")
            self.assertIn("Structural validation error", res.errors[0])

    def test_failure_results_in_stage7_and_stage8_include_repair_info(self):
        """Failure results in Stage 7 and Stage 8 preserve repair information."""
        pipeline = MinecraftPipeline(ai_provider=MagicMock(), verbose=False)

        mock_plan = {"datapack_name": "test_pack", "status": "planned", "files": []}

        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_dir = Path(tmp_dir) / "test_pack"
            pack_dir.mkdir(parents=True)

            mock_gen = GenerationResult(
                datapack_name="test_pack",
                datapack_path=pack_dir,
                zip_path=None,
                status="success"
            )
            pipeline.generator = MagicMock()
            pipeline.generator.generate.return_value = mock_gen

            # Validator returns valid
            valid_val = ValidationResult(status="valid", target_path=str(pack_dir), errors=[])
            pipeline.validator = MagicMock()
            pipeline.validator.validate.return_value = valid_val

            # Intent verification fails at Stage 7
            class MockPassQAResult(QAResult):
                @property
                def is_pass(self) -> bool:
                    return True

            intent_fail = IntentVerificationResult(
                matches_intent=False,
                reasoning="Missing requested feature",
                missing_aspects=["creeper drops"],
                confidence=0.2
            )
            mock_qa = MockPassQAResult(
                status="passed",
                summary="Review passed",
                findings=[],
                intent_verification=intent_fail
            )
            pipeline.qa_reviewer = MagicMock()
            pipeline.qa_reviewer.review.return_value = mock_qa

            dummy_understanding = {
                "user_intent": "Make creepers drop diamonds",
                "primary_mechanism": "loot_table",
                "requirements": ["modify creeper loot table"]
            }
            with patch("pipeline.minecraft_pipeline.create_plan", return_value=mock_plan):
                res = pipeline.run("Make creepers drop diamonds", create_zip=False, understanding=dummy_understanding)

            self.assertEqual(res.status, "verification_failed")
            self.assertEqual(res.failed_stage, "intent_verification")
            self.assertTrue(hasattr(res, "repair"))

            # Now test Stage 8 runtime simulation failure
            mock_qa.intent_verification = IntentVerificationResult(matches_intent=True, reasoning="OK", confidence=1.0)
            pipeline.qa_reviewer.review.side_effect = None
            pipeline.runtime_runner.run = MagicMock(
                return_value=RuntimeTestResult(
                    mode=RuntimeTestMode.STATIC_SIMULATION,
                    passed=False,
                    details="simulation fail"
                )
            )

            with patch("pipeline.minecraft_pipeline.create_plan", return_value=mock_plan):
                res8 = pipeline.run("Make creepers drop diamonds", create_zip=False, understanding=dummy_understanding)

            self.assertEqual(res8.status, "verification_failed")
            self.assertEqual(res8.failed_stage, "final_verification")
            self.assertTrue(hasattr(res8, "repair"))


if __name__ == "__main__":
    unittest.main()
