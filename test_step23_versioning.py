"""
test_step23_versioning.py - Multi-Version Minecraft Support & Version-Aware Generation Test Suite

Covers:
1. VersionRegistry registration, defaults, supported versions, rejection, and metadata fields.
2. Knowledge retriever isolation, dynamic resolution, rejection of fallback for unsupported versions.
3. Semantic IR MinecraftDatapackSpec version propagation and version-neutral property semantics.
4. Generator pack format 94, min_format/max_format [94, 0] / [94, 1], singular layout, determinism.
5. Validator format 94 acceptance, invalid format rejection, singular enforcement, unsupported version check.
6. Headless runtime server JAR resolution through VersionMetadata and parameterized startup detection.
7. CLI default version, --version argument handling, and clear rejection of unsupported versions.
8. Web API default version, /api/versions endpoint, and rejection of unsupported versions.
9. Evaluation benchmark version awareness and registry resolution.
10. End-to-end regression protection.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from ai.version_registry import (
    VersionContext,
    VersionMetadata,
    VersionRegistry,
    get_default_version,
    get_version_registry,
)
from ai.property_registry import (
    DEFAULT_PROPERTY_REGISTRY,
    resolve_attribute_identifier,
)
from ai.semantic_models import PropertyModification, SemanticNumericValue
from generator.datapack_generator import DatapackGenerator
from generator.models import (
    DatapackManifest,
    FunctionDefinition,
    MechanismSpecification,
    MinecraftDatapackSpec,
)
from knowledge_retriever import (
    MinecraftKnowledgeRetriever,
    get_commands_file,
    get_items_file,
    get_loot_tables_dir,
    load_entity_knowledge,
    load_item_knowledge,
    load_syntax_knowledge,
)
from qa.runtime import RuntimeTestMode, RuntimeTestRunner
from run_pipeline import run_cli
from validator.datapack_validator import DatapackValidator


class TestStep23Versioning(unittest.TestCase):
    """
    Test suite verifying Step 23 version-aware architecture.
    """

    def setUp(self):
        self.registry = get_version_registry()
        self.temp_dir = tempfile.mkdtemp(prefix="test_step23_")

    def tearDown(self):
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    # =========================================================================
    # 1. VersionRegistry Tests (Requirements 1 - 5)
    # =========================================================================

    def test_01_1_21_11_is_registered(self):
        """Requirement 1: 1.21.11 is registered in the VersionRegistry."""
        self.assertTrue(self.registry.is_supported("1.21.11"))
        meta = self.registry.get("1.21.11")
        self.assertEqual(meta.version_id, "1.21.11")

    def test_02_1_21_11_is_default(self):
        """Requirement 2: 1.21.11 is the default version."""
        self.assertEqual(get_default_version(), "1.21.11")
        default_meta = self.registry.get_default()
        self.assertEqual(default_meta.version_id, "1.21.11")

    def test_03_supported_version_listing_is_deterministic(self):
        """Requirement 3: supported-version listing is deterministic and sorted."""
        versions = self.registry.get_supported_versions()
        self.assertIsInstance(versions, list)
        self.assertEqual(versions, sorted(versions))
        self.assertIn("1.21.11", versions)

    def test_04_unsupported_versions_are_rejected(self):
        """Requirement 4: unsupported versions raise ValueError and are not reported as supported."""
        self.assertFalse(self.registry.is_supported("1.20.1"))
        self.assertFalse(self.registry.is_supported("1.21.1"))
        self.assertFalse(self.registry.is_supported("invalid_ver"))

        with self.assertRaises(ValueError) as ctx:
            self.registry.get("1.20.1")
        self.assertIn("Unsupported Minecraft version '1.20.1'", str(ctx.exception))

    def test_05_metadata_fields_are_valid(self):
        """Requirement 5: 1.21.11 metadata fields represent verified behavior."""
        meta = self.registry.get("1.21.11")
        self.assertEqual(meta.pack_format, 94)
        self.assertEqual(meta.min_format, [94, 0])
        self.assertEqual(meta.max_format, [94, 1])
        self.assertTrue(meta.supports_format_range)
        self.assertEqual(meta.directory_layout, "singular")
        self.assertEqual(meta.attribute_format, "namespaced")
        self.assertEqual(meta.modifier_id_format, "string")
        self.assertEqual(meta.recipe_result_format, "id_count")
        self.assertEqual(meta.data_pack_version, "94.1")

    # =========================================================================
    # 2. Knowledge Retrieval & Isolation Tests (Requirements 6 - 9)
    # =========================================================================

    def test_06_1_21_11_knowledge_resolves_correctly(self):
        """Requirement 6: 1.21.11 knowledge files resolve and load correctly."""
        retriever = MinecraftKnowledgeRetriever(version="1.21.11")
        self.assertEqual(retriever.version, "1.21.11")
        self.assertGreater(len(retriever.syntax_records), 0)
        self.assertGreater(len(retriever.items), 0)
        self.assertGreater(len(retriever.entities), 0)
        self.assertGreater(len(retriever.loot_tables), 0)

    def test_07_requested_version_is_used_by_retriever(self):
        """Requirement 7: Retriever accurately preserves and uses the requested version."""
        retriever = MinecraftKnowledgeRetriever(version="1.21.11")
        self.assertEqual(retriever.version, "1.21.11")

    def test_08_unsupported_versions_do_not_silently_fallback(self):
        """Requirement 8: Unsupported versions do not silently load 1.21.11 knowledge."""
        retriever = MinecraftKnowledgeRetriever(version="unsupported_target_version")
        self.assertEqual(retriever.version, "unsupported_target_version")
        self.assertEqual(len(retriever.syntax_records), 0)
        self.assertEqual(len(retriever.items), 0)
        self.assertEqual(len(retriever.entities), 0)
        self.assertEqual(len(retriever.loot_tables), 0)

    def test_09_version_path_isolation(self):
        """Requirement 9: Version paths isolate subdirectories per version."""
        p_1_21_11 = get_commands_file("1.21.11")
        p_other = get_commands_file("1.20.1")
        self.assertIn("1.21.11", p_1_21_11.parts)
        self.assertIn("1.20.1", p_other.parts)
        self.assertNotEqual(p_1_21_11, p_other)

    # =========================================================================
    # 3. Semantic IR Version Context Tests (Requirements 10 - 11)
    # =========================================================================

    def test_10_target_version_travels_with_datapack_specification(self):
        """Requirement 10: Target version travels with MinecraftDatapackSpec without breaking IR."""
        spec = MinecraftDatapackSpec(
            minecraft_version="1.21.11",
            requirements=[{"goal": "Make creepers drop diamonds"}],
            mechanisms=[
                MechanismSpecification(
                    type="loot_table",
                    target="entities/creeper.json",
                    item="minecraft:diamond"
                )
            ]
        )
        self.assertEqual(spec.minecraft_version, "1.21.11")
        self.assertEqual(len(spec.mechanisms), 1)

    def test_11_property_modifications_remain_version_neutral(self):
        """Requirement 11: PropertyModification contains no Minecraft version or command syntax."""
        prop = PropertyModification(
            property="speed",
            operation="multiply",
            value=SemanticNumericValue(kind="multiplier", value=2.0)
        )
        self.assertEqual(prop.property, "speed")
        self.assertEqual(prop.operation, "multiply")
        self.assertFalse(hasattr(prop, "minecraft_version"))
        self.assertFalse(hasattr(prop, "pack_format"))

    # =========================================================================
    # 4. Generator Version-Awareness Tests (Requirements 12 - 15)
    # =========================================================================

    def test_12_1_21_11_generates_pack_format_94(self):
        """Requirement 12: 1.21.11 generator produces pack_format 94 from VersionMetadata."""
        gen = DatapackGenerator(output_dir=Path(self.temp_dir), version="1.21.11")
        res = gen.generate(
            datapack_name="test_pack_94",
            functions=[FunctionDefinition(function_path="init", commands=["say test"], namespace="test_ns")],
            create_zip=False
        )
        self.assertEqual(res.status, "success")

        mcmeta_path = res.datapack_path / "pack.mcmeta"
        self.assertTrue(mcmeta_path.exists())
        with open(mcmeta_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["pack"]["pack_format"], 94)

    def test_13_1_21_11_generates_min_max_format_range(self):
        """Requirement 13: 1.21.11 generator produces min_format [94, 0] and max_format [94, 1]."""
        gen = DatapackGenerator(output_dir=Path(self.temp_dir), version="1.21.11")
        res = gen.generate(
            datapack_name="test_pack_range",
            functions=[FunctionDefinition(function_path="init", commands=["say test"], namespace="test_ns")],
            create_zip=False
        )
        mcmeta_path = res.datapack_path / "pack.mcmeta"

        with open(mcmeta_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["pack"]["min_format"], [94, 0])
        self.assertEqual(data["pack"]["max_format"], [94, 1])

    def test_14_1_21_11_generates_singular_directories(self):
        """Requirement 14: 1.21.11 generator uses singular directory conventions."""
        gen = DatapackGenerator(output_dir=Path(self.temp_dir), version="1.21.11")
        res = gen.generate(
            datapack_name="test_pack_singular",
            functions=[
                FunctionDefinition(
                    function_path="hello",
                    commands=["say hello"],
                    namespace="custom_ns"
                )
            ],
            create_zip=False
        )
        self.assertEqual(res.status, "success")
        self.assertTrue((res.datapack_path / "data" / "custom_ns" / "function" / "hello.mcfunction").exists())
        self.assertFalse((res.datapack_path / "data" / "custom_ns" / "functions").exists())

    def test_15_generated_1_21_11_output_remains_deterministic(self):
        """Requirement 15: Generated 1.21.11 output is deterministic across repeated runs."""
        funcs = [FunctionDefinition(function_path="init", commands=["say test"], namespace="test_ns")]
        gen1 = DatapackGenerator(output_dir=Path(self.temp_dir), version="1.21.11")
        gen2 = DatapackGenerator(output_dir=Path(self.temp_dir), version="1.21.11")

        res1 = gen1.generate(datapack_name="det_pack_1", functions=funcs, create_zip=True)
        res2 = gen2.generate(datapack_name="det_pack_2", functions=funcs, create_zip=True)

        mcmeta1 = (res1.datapack_path / "pack.mcmeta").read_text(encoding="utf-8")
        mcmeta2 = (res2.datapack_path / "pack.mcmeta").read_text(encoding="utf-8")
        self.assertEqual(mcmeta1, mcmeta2)

    # =========================================================================
    # 5. Validator Version-Awareness Tests (Requirements 16 - 19)
    # =========================================================================

    def test_16_1_21_11_accepts_valid_format_94(self):
        """Requirement 16: 1.21.11 validator accepts pack_format 94."""
        pack_dir = Path(self.temp_dir) / "valid_94"
        pack_dir.mkdir(parents=True, exist_ok=True)
        (pack_dir / "pack.mcmeta").write_text(
            json.dumps({"pack": {"pack_format": 94, "description": "test"}}),
            encoding="utf-8"
        )
        (pack_dir / "data").mkdir(parents=True, exist_ok=True)

        validator = DatapackValidator(version="1.21.11")
        result = validator.validate(pack_dir)
        format_checks = [c for c in result.checks if "Pack Format Compatibility" in c.name]
        self.assertTrue(any(c.passed for c in format_checks))

    def test_17_invalid_format_is_rejected(self):
        """Requirement 17: Incompatible pack format produces INVALID_PACK_FORMAT error."""
        pack_dir = Path(self.temp_dir) / "invalid_format"
        pack_dir.mkdir(parents=True, exist_ok=True)
        (pack_dir / "pack.mcmeta").write_text(
            json.dumps({"pack": {"pack_format": 48, "description": "1.20.4 pack"}}),
            encoding="utf-8"
        )
        (pack_dir / "data").mkdir(parents=True, exist_ok=True)

        validator = DatapackValidator(version="1.21.11")
        result = validator.validate(pack_dir)
        error_codes = [e.code for e in result.errors]
        self.assertIn("INVALID_PACK_FORMAT", error_codes)

    def test_18_singular_directory_rules_remain_enforced(self):
        """Requirement 18: Plural legacy directories remain rejected for 1.21.11."""
        pack_dir = Path(self.temp_dir) / "obsolete_dir_pack"
        (pack_dir / "data" / "minecraft_ai" / "functions").mkdir(parents=True, exist_ok=True)
        (pack_dir / "pack.mcmeta").write_text(
            json.dumps({"pack": {"pack_format": 94, "description": "test"}}),
            encoding="utf-8"
        )

        validator = DatapackValidator(version="1.21.11")
        result = validator.validate(pack_dir)
        error_codes = [e.code for e in result.errors]
        self.assertIn("OBSOLETE_PATH", error_codes)

    def test_19_unsupported_version_does_not_silently_validate_as_1_21_11(self):
        """Requirement 19: Initializing validator with unsupported version fails clearly."""
        with self.assertRaises(ValueError):
            DatapackValidator(version="unsupported_version_x")

    # =========================================================================
    # 6. Runtime Harness Version Tests (Requirements 20 - 21)
    # =========================================================================

    def test_20_runtime_resolves_1_21_11_jar_through_version_metadata(self):
        """Requirement 20: Runtime runner resolves the 1.21.11 server JAR dynamically."""
        runner = RuntimeTestRunner(version="1.21.11")
        meta_jar = runner.version_context.server_jar_path
        self.assertIsNotNone(meta_jar)
        self.assertTrue(Path(meta_jar).exists())
        self.assertIn("1.21.11", str(meta_jar))

    def test_21_runtime_startup_detection_remains_correct(self):
        """Requirement 21: Runtime startup detection checks expected version dynamically."""
        runner = RuntimeTestRunner(version="1.21.11")
        self.assertEqual(runner.version, "1.21.11")
        # An unsupported version fails to initialize
        with self.assertRaises(ValueError):
            RuntimeTestRunner(version="unsupported_ver")

    # =========================================================================
    # 7. CLI / Web Version Selection Tests (Requirements 22 - 26)
    # =========================================================================

    def test_22_cli_default_remains_1_21_11(self):
        """Requirement 22: CLI defaults to Minecraft 1.21.11 when --version is omitted."""
        executed_version = []

        def mock_pipeline(**kwargs):
            executed_version.append(kwargs.get("minecraft_version"))
            class MockRes:
                status = "success"
                is_success = True
                final_datapack_path = "p"
                final_zip_path = "z"
                def summary(self): return "ok"
            return MockRes()

        exit_code = run_cli(args=["Make creepers drop diamonds."], pipeline_fn=mock_pipeline)
        self.assertEqual(exit_code, 0)
        self.assertEqual(executed_version, ["1.21.11"])

    def test_23_cli_version_flag_works(self):
        """Requirement 23: CLI --version 1.21.11 executes cleanly."""
        executed_version = []

        def mock_pipeline(**kwargs):
            executed_version.append(kwargs.get("minecraft_version"))
            class MockRes:
                status = "success"
                is_success = True
                final_datapack_path = "p"
                final_zip_path = "z"
                def summary(self): return "ok"
            return MockRes()

        exit_code = run_cli(args=["--version", "1.21.11", "--request", "Make creepers drop diamonds."], pipeline_fn=mock_pipeline)
        self.assertEqual(exit_code, 0)
        self.assertEqual(executed_version, ["1.21.11"])

    def test_24_unsupported_cli_version_fails_clearly(self):
        """Requirement 24: Unsupported CLI version exits with error code 1 without running pipeline."""
        pipeline_called = []

        def mock_pipeline(**kwargs):
            pipeline_called.append(True)

        exit_code = run_cli(args=["--version", "1.20.1", "--request", "Make creepers drop diamonds."], pipeline_fn=mock_pipeline)
        self.assertEqual(exit_code, 1)
        self.assertEqual(len(pipeline_called), 0)

    def test_25_web_version_defaults_to_1_21_11(self):
        """Requirement 25: Web app /api/health and /api/versions report default version 1.21.11."""
        from web.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)

        resp = client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["minecraft_version"], "1.21.11")

        v_resp = client.get("/api/versions")
        self.assertEqual(v_resp.status_code, 200)
        v_data = v_resp.json()
        self.assertEqual(v_data["default_version"], "1.21.11")
        self.assertIn("1.21.11", v_data["supported_versions"])

    def test_26_web_rejects_unsupported_versions(self):
        """Requirement 26: Web API rejects unsupported version with HTTP 400."""
        from web.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)

        resp = client.post("/api/generate", json={
            "request": "Make creepers drop diamonds.",
            "minecraft_version": "1.20.1"
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Unsupported Minecraft version '1.20.1'", resp.json()["detail"])

    # =========================================================================
    # 8. Benchmark Version Tests (Requirements 27 - 28)
    # =========================================================================

    def test_27_benchmark_defaults_to_1_21_11(self):
        """Requirement 27: BenchmarkCase defaults to 1.21.11."""
        from eval.models import BenchmarkCase
        case = BenchmarkCase(
            id="test_case_ver",
            category="mob_loot",
            request="Make creepers drop diamonds."
        )
        self.assertEqual(case.minecraft_version, "1.21.11")

    def test_28_benchmark_resolves_version_through_registry(self):
        """Requirement 28: Benchmark runner resolves VersionContext from registry."""
        from eval.models import BenchmarkCase
        case = BenchmarkCase(
            id="test_case_reg",
            category="mob_loot",
            request="Make creepers drop diamonds.",
            minecraft_version="1.21.11"
        )
        v_ctx = VersionContext.from_version(case.minecraft_version)
        self.assertEqual(v_ctx.version_id, "1.21.11")
        self.assertEqual(v_ctx.pack_format, 94)

    # =========================================================================
    # 9. Regression Tests (Requirements 29 - 30)
    # =========================================================================

    def test_29_semantic_attribute_resolution_remains_valid(self):
        """Requirement 29: Semantic attribute identifier resolution produces verified identifier."""
        v_ctx = VersionContext.from_version("1.21.11")
        attr_id = resolve_attribute_identifier("speed", v_ctx)
        self.assertEqual(attr_id, "minecraft:generic.movement_speed")

    def test_30_existing_datapack_generation_remains_valid(self):
        """Requirement 30: End-to-end datapack generation and validation pass cleanly."""
        gen = DatapackGenerator(output_dir=Path(self.temp_dir), version="1.21.11")
        res = gen.generate(
            datapack_name="regression_pack",
            functions=[
                FunctionDefinition(
                    function_path="main",
                    commands=["say verified"],
                    namespace="minecraft_ai"
                )
            ],
            create_zip=True
        )
        self.assertEqual(res.status, "success")
        self.assertTrue(res.zip_path.exists())

        validator = DatapackValidator(version="1.21.11")
        val_res = validator.validate(res.zip_path)
        self.assertTrue(val_res.is_valid)


if __name__ == "__main__":
    unittest.main()
