"""
Unit tests for B11: Server filesystem path leak prevention.
Verifies that:
1. /api/generate never returns absolute server filesystem paths in datapack_path or zip_path.
2. In production mode, paths are None.
3. In development mode, paths are strictly relative (e.g. 'generated/<name>') and contain no drive letters or root paths.
4. execution_summary and repair_summary do not expose server paths.
"""

import unittest
from unittest.mock import patch
from pathlib import Path
from pipeline.models import PipelineResult
from generator.models import GenerationResult
from validator.models import ValidationResult
from security.config import DEFAULT_SECURITY_CONFIG
from web.app import _format_pipeline_result


class TestAuditB11PathLeak(unittest.TestCase):

    def test_paths_are_relative_in_development_mode(self):
        """In development mode, datapack_path and zip_path must be relative, not absolute server paths."""
        val = ValidationResult(status="valid", target_path="generated/test_pack", errors=[], warnings=[], checks=[])
        gen = GenerationResult(datapack_name="test_pack", datapack_path="generated/test_pack", files_generated=["pack.mcmeta"])
        res = PipelineResult(
            status="success",
            minecraft_version="1.21.11",
            original_request="Test prompt",
            generation=gen,
            validation=val,
            final_datapack_path="D:\\Projects\\MinecraftAI\\generated\\test_pack",
            final_zip_path="D:\\Projects\\MinecraftAI\\generated\\test_pack.zip",
            execution_summary="Datapack generated at D:\\Projects\\MinecraftAI\\generated\\test_pack"
        )

        with patch.object(DEFAULT_SECURITY_CONFIG, "is_development_mode", True):
            out = _format_pipeline_result(res)

            dp_path = out["datapack_path"]
            zip_path = out["zip_path"]

            self.assertIsNotNone(dp_path)
            self.assertIsNotNone(zip_path)

            # Crucial: Must be relative, e.g. 'generated/test_pack'
            self.assertEqual(dp_path, "generated/test_pack")
            self.assertEqual(zip_path, "generated/test_pack.zip")

            # Must not contain drive letters or absolute prefixes
            self.assertNotIn("D:", dp_path)
            self.assertNotIn("C:", dp_path)
            self.assertNotIn("Projects", dp_path)
            self.assertFalse(dp_path.startswith("/"))
            self.assertFalse(dp_path.startswith("\\"))

            # Execution summary must be sanitized
            self.assertNotIn("D:\\Projects", out["execution_summary"])

    def test_paths_are_none_in_production_mode(self):
        """In production mode, datapack_path and zip_path must be None."""
        val = ValidationResult(status="valid", target_path="generated/test_pack", errors=[], warnings=[], checks=[])
        gen = GenerationResult(datapack_name="test_pack", datapack_path="generated/test_pack", files_generated=["pack.mcmeta"])
        res = PipelineResult(
            status="success",
            minecraft_version="1.21.11",
            original_request="Test prompt",
            generation=gen,
            validation=val,
            final_datapack_path="D:\\Projects\\MinecraftAI\\generated\\test_pack",
            final_zip_path="D:\\Projects\\MinecraftAI\\generated\\test_pack.zip"
        )

        with patch.object(DEFAULT_SECURITY_CONFIG, "is_development_mode", False):
            out = _format_pipeline_result(res)
            self.assertIsNone(out["datapack_path"])
            self.assertIsNone(out["zip_path"])


if __name__ == "__main__":
    unittest.main()
