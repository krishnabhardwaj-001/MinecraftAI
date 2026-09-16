import unittest
from unittest.mock import MagicMock
from pathlib import Path

from pipeline.models import PipelineResult
from run_pipeline import run_cli


class TestCliClarificationLoop(unittest.TestCase):
    """
    Unit tests for run_pipeline.py interactive refinement loop.
    """

    def test_direct_success_without_clarification(self):
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = PipelineResult(
            status="success",
            minecraft_version="1.21.11",
            original_request="Make creepers drop diamonds.",
            final_datapack_path="dummy/path",
            final_zip_path="dummy/path.zip"
        )

        exit_code = run_cli(
            args=["Make creepers drop diamonds."],
            pipeline_fn=mock_pipeline
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(mock_pipeline.call_count, 1)

    def test_direct_failure_returns_exit_1(self):
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = PipelineResult(
            status="failed",
            minecraft_version="1.21.11",
            original_request="Invalid impossible request.",
            errors=["Fatal validation error"]
        )

        exit_code = run_cli(
            args=["Invalid impossible request."],
            pipeline_fn=mock_pipeline
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(mock_pipeline.call_count, 1)

    def test_empty_request_returns_exit_1(self):
        exit_code = run_cli(
            args=["   "]
        )
        self.assertEqual(exit_code, 1)

    def test_clarification_user_cancels(self):
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = PipelineResult(
            status="needs_clarification",
            minecraft_version="1.21.11",
            original_request="Make the zombie stronger.",
            clarification="Which attribute do you want increased?"
        )

        # User presses Enter without typing anything
        mock_input = MagicMock(return_value="")

        exit_code = run_cli(
            args=["Make the zombie stronger."],
            input_fn=mock_input,
            pipeline_fn=mock_pipeline
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(mock_pipeline.call_count, 1)

    def test_clarification_user_provides_answer_and_succeeds(self):
        first_call = PipelineResult(
            status="needs_clarification",
            minecraft_version="1.21.11",
            original_request="Add a recipe to craft a diamond using 9 dirt blocks.",
            clarification="Do you want shaped 3x3 or shapeless?"
        )
        second_call = PipelineResult(
            status="success",
            minecraft_version="1.21.11",
            original_request="Add a recipe to craft a diamond using 9 dirt blocks. Specifically: shaped 3x3.",
            final_datapack_path="generated/pack",
            final_zip_path="generated/pack.zip"
        )

        mock_pipeline = MagicMock(side_effect=[first_call, second_call])
        mock_input = MagicMock(return_value="shaped 3x3")

        exit_code = run_cli(
            args=["Add a recipe to craft a diamond using 9 dirt blocks."],
            input_fn=mock_input,
            pipeline_fn=mock_pipeline
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(mock_pipeline.call_count, 2)

        # Verify second call received the refined request
        second_args, second_kwargs = mock_pipeline.call_args_list[1]
        self.assertEqual(
            second_kwargs.get("request"),
            "Add a recipe to craft a diamond using 9 dirt blocks. Specifically: shaped 3x3."
        )

    def test_multiple_clarification_turns(self):
        turn1 = PipelineResult(
            status="needs_clarification",
            minecraft_version="1.21.11",
            original_request="Craft diamond with dirt.",
            clarification="How many dirt blocks?"
        )
        turn2 = PipelineResult(
            status="needs_clarification",
            minecraft_version="1.21.11",
            original_request="Craft diamond with dirt. Specifically: 9 dirt blocks.",
            clarification="Shaped or shapeless?"
        )
        turn3 = PipelineResult(
            status="success",
            minecraft_version="1.21.11",
            original_request="Craft diamond with dirt. Specifically: 9 dirt blocks. Specifically: shaped.",
            final_datapack_path="generated/pack",
            final_zip_path="generated/pack.zip"
        )

        mock_pipeline = MagicMock(side_effect=[turn1, turn2, turn3])
        mock_input = MagicMock(side_effect=["9 dirt blocks", "shaped"])

        exit_code = run_cli(
            args=["Craft diamond with dirt."],
            input_fn=mock_input,
            pipeline_fn=mock_pipeline
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(mock_pipeline.call_count, 3)

        third_kwargs = mock_pipeline.call_args_list[2][1]
        self.assertEqual(
            third_kwargs.get("request"),
            "Craft diamond with dirt. Specifically: 9 dirt blocks. Specifically: shaped."
        )


if __name__ == "__main__":
    unittest.main()
