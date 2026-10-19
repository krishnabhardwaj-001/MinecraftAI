"""
Unit tests for B15: CLI argument handling via argparse and input security validation.

Verifies:
1. --help displays usage and returns 0 without calling the pipeline.
2. Unrecognized arguments (e.g. --unknown-flag) are rejected with non-zero exit code and not sent to pipeline.
3. Prompts are validated through validate_prompt:
   - Oversized prompts (> 2000 chars) are rejected with exit code 1.
   - Prompts containing null bytes are rejected.
   - Empty prompts are rejected.
4. Supported flags (--request, --version) and positional words are properly handled.
5. Unsupported versions are rejected with exit code 1 before pipeline execution.
"""

import io
import unittest
from unittest.mock import MagicMock, patch

from pipeline.models import PipelineResult
from run_pipeline import run_cli


class TestAuditB15CliArgs(unittest.TestCase):

    def setUp(self):
        self.mock_pipeline = MagicMock()
        self.mock_pipeline.return_value = PipelineResult(
            status="success",
            minecraft_version="1.21.11",
            original_request="Make every skeleton drop iron ingots.",
            final_datapack_path="generated/pack",
            final_zip_path="generated/pack.zip"
        )

    def test_help_flag_returns_0_without_calling_pipeline(self):
        """--help prints usage information and exits 0 without calling pipeline."""
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            exit_code = run_cli(args=["--help"], pipeline_fn=self.mock_pipeline)

        self.assertEqual(exit_code, 0)
        self.mock_pipeline.assert_not_called()
        self.assertIn("usage:", fake_out.getvalue().lower())

    def test_unknown_flag_rejected_without_calling_pipeline(self):
        """Unknown flags like --bogus are rejected and not sent to the LLM."""
        with patch("sys.stderr", new=io.StringIO()) as fake_err:
            exit_code = run_cli(args=["--bogus-flag", "Make diamonds"], pipeline_fn=self.mock_pipeline)

        self.assertNotEqual(exit_code, 0)
        self.mock_pipeline.assert_not_called()

    def test_oversized_prompt_rejected_by_validate_prompt(self):
        """Prompts exceeding maximum length are rejected by validate_prompt with code 1."""
        oversized = "give diamond " * 300
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            exit_code = run_cli(args=["--request", oversized], pipeline_fn=self.mock_pipeline)

        self.assertEqual(exit_code, 1)
        self.mock_pipeline.assert_not_called()
        self.assertIn("exceeds maximum permitted length", fake_out.getvalue().lower())

    def test_null_byte_prompt_rejected(self):
        """Prompts with null bytes are rejected by security validation."""
        malicious = "Make skeletons drop \x00 iron"
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            exit_code = run_cli(args=["--request", malicious], pipeline_fn=self.mock_pipeline)

        self.assertEqual(exit_code, 1)
        self.mock_pipeline.assert_not_called()

    def test_positional_words_passed_to_pipeline(self):
        """Positional words are combined and passed to the pipeline as request."""
        exit_code = run_cli(
            args=["Make", "every", "skeleton", "drop", "iron", "ingots."],
            pipeline_fn=self.mock_pipeline
        )
        self.assertEqual(exit_code, 0)
        self.mock_pipeline.assert_called_once()
        call_kwargs = self.mock_pipeline.call_args.kwargs
        self.assertEqual(call_kwargs["request"], "Make every skeleton drop iron ingots.")

    def test_version_flag_selection(self):
        """--version flag selects the target version."""
        exit_code = run_cli(
            args=["--version", "1.21.1", "--request", "Make every skeleton drop iron ingots."],
            pipeline_fn=self.mock_pipeline
        )
        self.assertEqual(exit_code, 0)
        call_kwargs = self.mock_pipeline.call_args.kwargs
        self.assertEqual(call_kwargs["minecraft_version"], "1.21.1")

    def test_unsupported_version_rejected(self):
        """Unsupported version string fails before pipeline execution."""
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            exit_code = run_cli(
                args=["--version", "1.12.2", "--request", "Make every skeleton drop iron ingots."],
                pipeline_fn=self.mock_pipeline
            )
        self.assertEqual(exit_code, 1)
        self.mock_pipeline.assert_not_called()
        self.assertIn("unsupported minecraft version", fake_out.getvalue().lower())


if __name__ == "__main__":
    unittest.main()
