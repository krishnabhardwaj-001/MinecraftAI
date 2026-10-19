"""
test_step24_multiversion.py - Step 24 Multi-Version Test Suite

Comprehensive automated test suite covering:
1. VersionRegistry support for Minecraft Java 1.21.1 and 1.21.11
2. Pack format resolution (1.21.1 -> 48, 1.21.11 -> 94)
3. Pack.mcmeta generation with version-specific formats
4. Version-aware attribute resolution (generic.* for 1.21.1, unprefixed for 1.21.11)
5. Validator isolation & cross-version pack_format rejection
6. Function tag generation (load.json and tick.json under data/minecraft/tags/function/)
7. ZIP structure root layout (no outer directory, pack.mcmeta and data/ at root)
8. Knowledge isolation between 1.21.1 and 1.21.11
9. Generator VersionContext forwarding to all mechanism generators
10. Real Minecraft 1.21.1 headless runtime verification
"""

import json
import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from ai.property_registry import resolve_attribute_identifier
from ai.version_registry import VersionContext, VersionRegistry, get_default_version, get_version_registry
from generator.datapack_generator import DatapackGenerator
from generator.models import FunctionDefinition, FunctionTagDefinition
from knowledge_retriever import MinecraftKnowledgeRetriever
from qa.runtime import RuntimeTestMode, RuntimeTestRunner
from validator.datapack_validator import DatapackValidator


class TestStep24MultiVersion(unittest.TestCase):
    """
    Test suite verifying full multi-version support across Minecraft 1.21.1 and 1.21.11.
    """

    @classmethod
    def setUpClass(cls):
        cls.test_dir = Path(tempfile.mkdtemp(prefix="step24_multiversion_"))
        cls.registry = get_version_registry()

    @classmethod
    def tearDownClass(cls):
        if cls.test_dir.exists():
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    # =========================================================================
    # 1. Version Registry Tests
    # =========================================================================

    def test_01_version_registry_both_supported(self):
        """Requirement: Both 1.21.1 and 1.21.11 are registered and officially supported."""
        self.assertTrue(self.registry.is_supported("1.21.1"))
        self.assertTrue(self.registry.is_supported("1.21.11"))
        self.assertEqual(get_default_version(), "1.21.11")

        supported = self.registry.get_supported_versions()
        self.assertIn("1.21.1", supported)
        self.assertIn("1.21.11", supported)

    # =========================================================================
    # 2. Pack Format Tests
    # =========================================================================

    def test_02_pack_format_resolution(self):
        """Requirement: 1.21.1 resolves pack_format 48; 1.21.11 resolves pack_format 94."""
        ctx_1 = VersionContext("1.21.1")
        self.assertEqual(ctx_1.pack_format, 48)
        self.assertEqual(ctx_1.min_format, [48, 0])
        self.assertEqual(ctx_1.max_format, [48, 0])
        self.assertEqual(ctx_1.data_pack_version, "48.0")

        ctx_11 = VersionContext("1.21.11")
        self.assertEqual(ctx_11.pack_format, 94)
        self.assertEqual(ctx_11.min_format, [94, 0])
        self.assertEqual(ctx_11.max_format, [94, 1])
        self.assertEqual(ctx_11.data_pack_version, "94.1")

    def test_03_generated_pack_mcmeta_format(self):
        """Requirement: Generated pack.mcmeta correctly reflects version-specific pack_format."""
        # 1.21.1 pack
        gen_1 = DatapackGenerator(output_dir=self.test_dir, version="1.21.1")
        res_1 = gen_1.generate(
            datapack_name="pack_mcmeta_1211",
            functions=[FunctionDefinition(function_path="main", commands=["say test 1.21.1"])],
            create_zip=False
        )
        mcmeta_1 = json.loads((res_1.datapack_path / "pack.mcmeta").read_text(encoding="utf-8"))
        self.assertEqual(mcmeta_1["pack"]["pack_format"], 48)
        self.assertEqual(mcmeta_1["pack"]["min_format"], [48, 0])
        self.assertEqual(mcmeta_1["pack"]["max_format"], [48, 0])

        # 1.21.11 pack
        gen_11 = DatapackGenerator(output_dir=self.test_dir, version="1.21.11")
        res_11 = gen_11.generate(
            datapack_name="pack_mcmeta_12111",
            functions=[FunctionDefinition(function_path="main", commands=["say test 1.21.11"])],
            create_zip=False
        )
        mcmeta_11 = json.loads((res_11.datapack_path / "pack.mcmeta").read_text(encoding="utf-8"))
        self.assertEqual(mcmeta_11["pack"]["pack_format"], 94)
        self.assertEqual(mcmeta_11["pack"]["min_format"], [94, 0])
        self.assertEqual(mcmeta_11["pack"]["max_format"], [94, 1])

    # =========================================================================
    # 3. Attribute Resolution Tests
    # =========================================================================

    def test_04_attribute_resolution_version_aware(self):
        """Requirement: Semantic properties resolve to generic.* for 1.21.1 and unprefixed for 1.21.11."""
        ctx_1 = VersionContext("1.21.1")
        ctx_11 = VersionContext("1.21.11")

        # speed -> generic.movement_speed vs movement_speed
        self.assertEqual(resolve_attribute_identifier("speed", ctx_1), "minecraft:generic.movement_speed")
        self.assertEqual(resolve_attribute_identifier("speed", ctx_11), "minecraft:movement_speed")

        # movement_speed
        self.assertEqual(resolve_attribute_identifier("movement_speed", ctx_1), "minecraft:generic.movement_speed")
        self.assertEqual(resolve_attribute_identifier("movement_speed", ctx_11), "minecraft:movement_speed")

        # attack_damage
        self.assertEqual(resolve_attribute_identifier("attack_damage", ctx_1), "minecraft:generic.attack_damage")
        self.assertEqual(resolve_attribute_identifier("attack_damage", ctx_11), "minecraft:attack_damage")

        # max_health
        self.assertEqual(resolve_attribute_identifier("max_health", ctx_1), "minecraft:generic.max_health")
        self.assertEqual(resolve_attribute_identifier("max_health", ctx_11), "minecraft:max_health")

        # armor
        self.assertEqual(resolve_attribute_identifier("armor", ctx_1), "minecraft:generic.armor")
        self.assertEqual(resolve_attribute_identifier("armor", ctx_11), "minecraft:armor")

        # scale
        self.assertEqual(resolve_attribute_identifier("scale", ctx_1), "minecraft:generic.scale")
        self.assertEqual(resolve_attribute_identifier("scale", ctx_11), "minecraft:scale")

    # =========================================================================
    # 4. Validator Isolation Tests
    # =========================================================================

    def test_05_validator_accepts_valid_matching_version(self):
        """Requirement: DatapackValidator accepts valid datapacks matching its version."""
        # 1.21.1
        gen_1 = DatapackGenerator(output_dir=self.test_dir, version="1.21.1")
        res_1 = gen_1.generate(
            datapack_name="val_iso_1211",
            functions=[FunctionDefinition(function_path="main", commands=["say hello 1.21.1"])],
            tags=[FunctionTagDefinition(tag_name="load", values=["minecraft_ai:main"], namespace="minecraft")],
            create_zip=True
        )
        validator_1 = DatapackValidator(version="1.21.1")
        v_res_1 = validator_1.validate(res_1.zip_path)
        self.assertTrue(v_res_1.is_valid, f"1.21.1 validation failed: {v_res_1.errors}")

        # 1.21.11
        gen_11 = DatapackGenerator(output_dir=self.test_dir, version="1.21.11")
        res_11 = gen_11.generate(
            datapack_name="val_iso_12111",
            functions=[FunctionDefinition(function_path="main", commands=["say hello 1.21.11"])],
            tags=[FunctionTagDefinition(tag_name="load", values=["minecraft_ai:main"], namespace="minecraft")],
            create_zip=True
        )
        validator_11 = DatapackValidator(version="1.21.11")
        v_res_11 = validator_11.validate(res_11.zip_path)
        self.assertTrue(v_res_11.is_valid, f"1.21.11 validation failed: {v_res_11.errors}")

    def test_06_validator_rejects_incompatible_pack_format(self):
        """Requirement: DatapackValidator rejects datapack with incompatible pack_format."""
        # Generate 1.21.1 pack (format 48)
        gen_1 = DatapackGenerator(output_dir=self.test_dir, version="1.21.1")
        res_1 = gen_1.generate(
            datapack_name="val_cross_1211",
            functions=[FunctionDefinition(function_path="main", commands=["say test"])],
            create_zip=True
        )

        # Validate with 1.21.11 validator (expects 94) -> MUST FAIL
        validator_11 = DatapackValidator(version="1.21.11")
        v_res = validator_11.validate(res_1.zip_path)
        self.assertFalse(v_res.is_valid, "1.21.11 validator must reject 1.21.1 pack (format 48 != 94)")
        self.assertTrue(any("pack_format" in str(e).lower() for e in v_res.errors))

        # Generate 1.21.11 pack (format 94)
        gen_11 = DatapackGenerator(output_dir=self.test_dir, version="1.21.11")
        res_11 = gen_11.generate(
            datapack_name="val_cross_12111",
            functions=[FunctionDefinition(function_path="main", commands=["say test"])],
            create_zip=True
        )

        # Validate with 1.21.1 validator (expects 48) -> MUST FAIL
        validator_1 = DatapackValidator(version="1.21.1")
        v_res_cross = validator_1.validate(res_11.zip_path)
        self.assertFalse(v_res_cross.is_valid, "1.21.1 validator must reject 1.21.11 pack (format 94 != 48)")
        self.assertTrue(any("pack_format" in str(e).lower() for e in v_res_cross.errors))

    # =========================================================================
    # 5. Function Tags Tests
    # =========================================================================

    def test_07_function_tags_both_versions(self):
        """Requirement: Both versions generate canonical function tags under data/minecraft/tags/function/."""
        for ver in ["1.21.1", "1.21.11"]:
            gen = DatapackGenerator(output_dir=self.test_dir, version=ver)
            res = gen.generate(
                datapack_name=f"tag_test_{ver.replace('.', '_')}",
                functions=[
                    FunctionDefinition(function_path="on_tick", commands=["say tick"], namespace="minecraft_ai"),
                    FunctionDefinition(function_path="on_load", commands=["say load"], namespace="minecraft_ai"),
                ],
                tags=[
                    FunctionTagDefinition(tag_name="tick", values=["minecraft_ai:on_tick"], namespace="minecraft"),
                    FunctionTagDefinition(tag_name="load", values=["minecraft_ai:on_load"], namespace="minecraft"),
                ],
                create_zip=True
            )
            # Check paths
            load_tag = res.datapack_path / "data" / "minecraft" / "tags" / "function" / "load.json"
            tick_tag = res.datapack_path / "data" / "minecraft" / "tags" / "function" / "tick.json"
            self.assertTrue(load_tag.exists(), f"Missing load.json for {ver}")
            self.assertTrue(tick_tag.exists(), f"Missing tick.json for {ver}")

            load_data = json.loads(load_tag.read_text(encoding="utf-8"))
            tick_data = json.loads(tick_tag.read_text(encoding="utf-8"))
            self.assertIn("minecraft_ai:on_load", load_data["values"])
            self.assertIn("minecraft_ai:on_tick", tick_data["values"])
            self.assertNotIn("replace", load_data)

    # =========================================================================
    # 6. ZIP Structure Tests
    # =========================================================================

    def test_08_zip_structure_root_layout(self):
        """Requirement: ZIP structure has pack.mcmeta and data/ at root with no outer wrapper folder."""
        for ver in ["1.21.1", "1.21.11"]:
            gen = DatapackGenerator(output_dir=self.test_dir, version=ver)
            res = gen.generate(
                datapack_name=f"zip_test_{ver.replace('.', '_')}",
                functions=[FunctionDefinition(function_path="main", commands=["say test"])],
                create_zip=True
            )
            self.assertTrue(res.zip_path.exists())
            with zipfile.ZipFile(res.zip_path, "r") as zf:
                names = zf.namelist()
                self.assertIn("pack.mcmeta", names, f"pack.mcmeta missing from ZIP root for {ver}")
                self.assertTrue(any(n.startswith("data/") for n in names), f"data/ hierarchy missing from ZIP for {ver}")
                # Ensure no wrapper directory
                for n in names:
                    self.assertFalse(n.startswith("zip_test_"), f"Found unwanted outer wrapper folder in ZIP: {n}")

    # =========================================================================
    # 7. Knowledge Isolation Tests
    # =========================================================================

    def test_09_knowledge_isolation(self):
        """Requirement: 1.21.1 does not read 1.21.11 knowledge files."""
        ret_1 = MinecraftKnowledgeRetriever(version="1.21.1")
        ret_11 = MinecraftKnowledgeRetriever(version="1.21.11")

        self.assertEqual(ret_1.version, "1.21.1")
        self.assertEqual(ret_11.version, "1.21.11")

        # Syntax records: 1.21.1 has 1007, 1.21.11 has 1273
        self.assertEqual(len(ret_1.syntax_records), 1007)
        self.assertEqual(len(ret_11.syntax_records), 1273)

        # Entities: 1.21.1 has 130, 1.21.11 has 157
        self.assertEqual(len(ret_1.entities), 130)
        self.assertEqual(len(ret_11.entities), 157)

        # Attribute base reset was introduced in 1.21.2+ (present in 1.21.11, absent in 1.21.1)
        cmds_1_text = [r.get("syntax", "") for r in ret_1.syntax_records]
        cmds_11_text = [r.get("syntax", "") for r in ret_11.syntax_records]
        has_base_reset_1 = any("base reset" in c for c in cmds_1_text)
        has_base_reset_11 = any("base reset" in c for c in cmds_11_text)
        self.assertFalse(has_base_reset_1, "1.21.1 must not contain 'base reset' subcommand")
        self.assertTrue(has_base_reset_11, "1.21.11 must contain 'base reset' subcommand")

    # =========================================================================
    # 8. Generator VersionContext Forwarding
    # =========================================================================

    def test_10_generator_version_forwarding(self):
        """Requirement: DatapackGenerator forwards active version to all mechanism generators."""
        gen_1 = DatapackGenerator(version="1.21.1")
        self.assertEqual(gen_1.version, "1.21.1")
        self.assertEqual(gen_1.function_mech.version, "1.21.1")
        self.assertEqual(gen_1.tag_mech.version, "1.21.1")
        self.assertEqual(gen_1.advancement_mech.version, "1.21.1")
        self.assertEqual(gen_1.loot_mech.version, "1.21.1")

        gen_11 = DatapackGenerator(version="1.21.11")
        self.assertEqual(gen_11.version, "1.21.11")
        self.assertEqual(gen_11.function_mech.version, "1.21.11")
        self.assertEqual(gen_11.tag_mech.version, "1.21.11")
        self.assertEqual(gen_11.advancement_mech.version, "1.21.11")
        self.assertEqual(gen_11.loot_mech.version, "1.21.11")

    # =========================================================================
    # 9. Real Minecraft 1.21.1 Headless Runtime Verification
    # =========================================================================

    def test_11_real_minecraft_1_21_1_headless_server_execution(self):
        """Requirement: Headless Minecraft 1.21.1 server execution verifies datapack loading, reload, and function tags."""
        gen_1 = DatapackGenerator(output_dir=self.test_dir, version="1.21.1")
        res_1 = gen_1.generate(
            datapack_name="live_1211_runtime_test",
            functions=[
                FunctionDefinition(
                    function_path="main",
                    commands=[
                        "say 1.21.1 real server test verified",
                        "attribute @a minecraft:generic.movement_speed base set 0.2"
                    ],
                    namespace="minecraft_ai"
                )
            ],
            tags=[
                FunctionTagDefinition(
                    tag_name="load",
                    values=["minecraft_ai:main"],
                    namespace="minecraft"
                )
            ],
            create_zip=True
        )

        runner = RuntimeTestRunner(version="1.21.1")
        server_jar = runner.version_context.server_jar_path
        if not server_jar or not server_jar.exists():
            self.skipTest("Minecraft server JAR for 1.21.1 not found.")
        repo_root = Path(__file__).resolve().parent
        if not (repo_root / "source" / "1.21.1" / "libraries").exists() and not (repo_root / "libraries").exists():
            self.skipTest("Required libraries directory for 1.21.1 not found.")
        if not shutil.which("java"):
            self.skipTest("Java runtime ('java') not found on PATH.")
        rt_res = runner.run(
            datapack_dir=res_1.zip_path,
            mode=RuntimeTestMode.MINECRAFT_SERVER,
            timeout_s=60,
            custom_commands=["reload", "function minecraft_ai:main", "stop"]
        )

        self.assertTrue(rt_res.passed, f"1.21.1 real server execution failed: {rt_res.details} (logs: {rt_res.logs[:10]})")
        self.assertIn("boot_load", rt_res.events_tested)
        self.assertIn("cmd_reload", rt_res.events_tested)
        self.assertIn("cmd_stop", rt_res.events_tested)

        # Check logs for exact version string
        has_version = any("Starting minecraft server version 1.21.1" in l for l in rt_res.logs)
        self.assertTrue(has_version, "Server logs must confirm 'Starting minecraft server version 1.21.1'")


if __name__ == "__main__":
    unittest.main()
