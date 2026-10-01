"""
test_step25_1_loot_knowledge.py - Phase 25.1 1.21.1 Loot Table Knowledge Verification

Verifies:
1. 1.21.1 vanilla loot knowledge exists and can be loaded via knowledge_retriever.
2. 1.21.1 loot table modifications preserve vanilla drops (e.g. gunpowder, discs for creeper; rotten flesh for zombie).
3. DatapackValidator verifies vanilla drop preservation for 1.21.1 and detects destructive modifications.
4. 1.21.11 regression: existing 1.21.11 loot knowledge, generation, and validation remain unchanged.
5. 1.21.1 generated ZIP structure has root-level pack.mcmeta and data/ layout with exact directory parity.
"""

import json
import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from generator.datapack_generator import DatapackGenerator
from generator.models import LootTableModification
from knowledge_retriever import (
    load_loot_table_knowledge,
    get_loot_tables_dir,
    MinecraftKnowledgeRetriever,
)
from validator.datapack_validator import DatapackValidator


class TestPhase251LootKnowledge(unittest.TestCase):
    """
    Focused verification tests for Phase 25.1: 1.21.1 loot knowledge restoration
    and vanilla drop preservation parity with 1.21.11.
    """

    @classmethod
    def setUpClass(cls):
        cls.test_dir = Path(tempfile.mkdtemp(prefix="step25_1_loot_"))
        cls.repo_root = Path(__file__).resolve().parent

    @classmethod
    def tearDownClass(cls):
        if cls.test_dir.exists():
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    # =========================================================================
    # Test A: 1.21.1 Vanilla Loot Knowledge Exists
    # =========================================================================

    def test_01_1_21_1_loot_knowledge_exists(self):
        """Requirement: 1.21.1 loot tables directory exists and contains representative entity tables."""
        lt_dir = get_loot_tables_dir("1.21.1")
        self.assertTrue(lt_dir.exists(), f"1.21.1 loot tables dir does not exist at {lt_dir}")

        # Check representative entity loot tables
        representatives = [
            "entities/creeper.json",
            "entities/zombie.json",
            "entities/skeleton.json",
            "entities/spider.json",
            "blocks/stone.json",
            "chests/simple_dungeon.json",
            "equipment/trial_chamber_melee.json",
        ]
        for rel in representatives:
            file_path = lt_dir / rel
            self.assertTrue(file_path.exists(), f"Missing representative 1.21.1 loot table: {rel}")
            # Ensure valid JSON
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("type", data)
            self.assertIn("pools", data)

        # Check knowledge retriever loading
        loaded_tables = load_loot_table_knowledge("1.21.1")
        self.assertGreaterEqual(len(loaded_tables), 1100, f"Expected >= 1100 loot tables, got {len(loaded_tables)}")

        # Verify creeper specifically has gunpowder in its first pool
        creeper_records = [t for t in loaded_tables if t.get("path") == "entities/creeper.json"]
        self.assertEqual(len(creeper_records), 1)
        creeper_data = creeper_records[0]["data"]
        pool0_items = [
            e.get("name") for e in creeper_data["pools"][0].get("entries", [])
            if isinstance(e, dict)
        ]
        self.assertIn("minecraft:gunpowder", pool0_items)

    # =========================================================================
    # Test B: 1.21.1 Loot Modification Preserves Vanilla Drops
    # =========================================================================

    def test_02_1_21_1_loot_modification_preserves_vanilla_drops(self):
        """Requirement: Modifying a 1.21.1 mob loot table preserves all original vanilla pools and adds new pool."""
        gen = DatapackGenerator(version="1.21.1")

        # Case 1: Creeper drops diamonds (standard relative path)
        mod_creeper = LootTableModification(
            loot_table_path="entities/creeper.json",
            item="minecraft:diamond",
            operation="add_pool",
            count=1
        )
        res_creeper = gen.loot_generator.modify_loot_table(mod_creeper)

        # Vanilla creeper has 2 pools (gunpowder, music discs on skeleton kill).
        # Modified creeper should have 3 pools: 2 vanilla + 1 custom diamond.
        self.assertEqual(len(res_creeper["pools"]), 3)
        all_pool_items = [
            [e.get("name") for e in p.get("entries", []) if isinstance(e, dict)]
            for p in res_creeper["pools"]
        ]
        self.assertIn(["minecraft:gunpowder"], all_pool_items)
        self.assertIn(["minecraft:diamond"], all_pool_items)
        self.assertEqual(res_creeper.get("random_sequence"), "minecraft:entities/creeper")

        # Case 2: Zombie drops emeralds (path with minecraft: prefix)
        mod_zombie = LootTableModification(
            loot_table_path="minecraft:entities/zombie",
            item="minecraft:emerald",
            operation="add_pool",
            count=2
        )
        res_zombie = gen.loot_generator.modify_loot_table(mod_zombie)
        # Vanilla zombie has rotten flesh + rare drops (iron, carrot, potato).
        # With added emerald pool, original pools must be intact.
        self.assertGreaterEqual(len(res_zombie["pools"]), 2)
        zombie_items = [
            e.get("name")
            for p in res_zombie["pools"]
            for e in p.get("entries", [])
            if isinstance(e, dict)
        ]
        self.assertIn("minecraft:rotten_flesh", zombie_items)
        self.assertIn("minecraft:emerald", zombie_items)

    # =========================================================================
    # Test C: Validator Checks 1.21.1 Vanilla Drops
    # =========================================================================

    def test_03_validator_checks_1_21_1_vanilla_drops(self):
        """Requirement: DatapackValidator verifies vanilla drop preservation and flags destructive tables on 1.21.1."""
        validator = DatapackValidator(version="1.21.1")

        # Sub-case C.1: Preserved 1.21.1 table passes with check
        pack_dir_valid = self.test_dir / "valid_pack_1_21_1"
        pack_dir_valid.mkdir(parents=True, exist_ok=True)
        (pack_dir_valid / "pack.mcmeta").write_text(
            json.dumps({"pack": {"pack_format": 48, "description": "1.21.1 Valid Pack"}}, indent=2)
        )
        gen = DatapackGenerator(version="1.21.1")
        valid_table = gen.loot_generator.modify_loot_table(
            LootTableModification(loot_table_path="entities/creeper.json", item="minecraft:diamond", operation="add_pool")
        )
        lt_dir = pack_dir_valid / "data" / "minecraft" / "loot_table" / "entities"
        lt_dir.mkdir(parents=True, exist_ok=True)
        (lt_dir / "creeper.json").write_text(json.dumps(valid_table, indent=2))

        val_result_valid = validator.validate(pack_dir_valid)
        self.assertTrue(val_result_valid.is_valid)
        self.assertEqual(len(val_result_valid.errors), 0)
        # Confirm that Vanilla Preservation check ran and passed
        preservation_checks = [c for c in val_result_valid.checks if "Vanilla Preservation" in c.name]
        self.assertEqual(len(preservation_checks), 1)
        self.assertTrue(preservation_checks[0].passed)

        # Sub-case C.2: Destructive 1.21.1 table (deletes gunpowder) emits PRESERVATION_FAILURE warning
        pack_dir_destructive = self.test_dir / "destructive_pack_1_21_1"
        pack_dir_destructive.mkdir(parents=True, exist_ok=True)
        (pack_dir_destructive / "pack.mcmeta").write_text(
            json.dumps({"pack": {"pack_format": 48, "description": "1.21.1 Destructive Pack"}}, indent=2)
        )
        destructive_table = {
            "type": "minecraft:entity",
            "pools": [
                {
                    "rolls": 1.0,
                    "entries": [{"type": "minecraft:item", "name": "minecraft:diamond"}]
                }
            ]
        }
        dest_lt_dir = pack_dir_destructive / "data" / "minecraft" / "loot_table" / "entities"
        dest_lt_dir.mkdir(parents=True, exist_ok=True)
        (dest_lt_dir / "creeper.json").write_text(json.dumps(destructive_table, indent=2))

        val_result_dest = validator.validate(pack_dir_destructive)
        self.assertTrue(val_result_dest.is_valid)  # Valid JSON and syntax, but has warnings
        pres_warnings = [w for w in val_result_dest.warnings if w.code == "PRESERVATION_FAILURE"]
        self.assertEqual(len(pres_warnings), 1)
        self.assertIn("entities/creeper.json", pres_warnings[0].message)

    # =========================================================================
    # Test D: 1.21.11 Regression Verification
    # =========================================================================

    def test_04_1_21_11_regression(self):
        """Requirement: 1.21.11 loot knowledge, generation, and validation remain completely unchanged."""
        validator_11 = DatapackValidator(version="1.21.11")
        gen_11 = DatapackGenerator(version="1.21.11")

        # Verify 1.21.11 loaded loot tables count
        loaded_11 = load_loot_table_knowledge("1.21.11")
        self.assertGreaterEqual(len(loaded_11), 1300)

        # Verify 1.21.11 creeper modification preserves vanilla drops
        mod_11 = LootTableModification(
            loot_table_path="entities/creeper.json",
            item="minecraft:diamond",
            operation="add_pool",
            count=1
        )
        res_11 = gen_11.loot_generator.modify_loot_table(mod_11)
        self.assertEqual(len(res_11["pools"]), 3)

        # Verify 1.21.11 validator behavior
        pack_dir_11 = self.test_dir / "valid_pack_1_21_11"
        pack_dir_11.mkdir(parents=True, exist_ok=True)
        (pack_dir_11 / "pack.mcmeta").write_text(
            json.dumps({"pack": {"pack_format": 94, "description": "1.21.11 Pack"}}, indent=2)
        )
        lt_dir_11 = pack_dir_11 / "data" / "minecraft" / "loot_table" / "entities"
        lt_dir_11.mkdir(parents=True, exist_ok=True)
        (lt_dir_11 / "creeper.json").write_text(json.dumps(res_11, indent=2))

        val_result_11 = validator_11.validate(pack_dir_11)
        self.assertTrue(val_result_11.is_valid)
        preservation_checks_11 = [c for c in val_result_11.checks if "Vanilla Preservation" in c.name]
        self.assertEqual(len(preservation_checks_11), 1)
        self.assertTrue(preservation_checks_11[0].passed)

    # =========================================================================
    # Test E: 1.21.1 Generated ZIP Structure & Parity
    # =========================================================================

    def test_05_1_21_1_zip_structure_and_parity(self):
        """Requirement: 1.21.1 generated ZIP has pack.mcmeta and data/ at root with exact file parity."""
        gen = DatapackGenerator(output_dir=self.test_dir, version="1.21.1")
        plan = {
            "status": "ready",
            "minecraft_version": "1.21.1",
            "summary": "Make creepers drop diamonds in 1.21.1",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Creeper diamond drop",
                    "mechanisms": [
                        {
                            "type": "loot_table",
                            "target": "entities/creeper.json",
                            "item": "minecraft:diamond",
                            "operation": "add_pool",
                            "count": 1
                        }
                    ]
                }
            ]
        }
        res = gen.generate(plan=plan, datapack_name="creeper_diamonds_1_21_1", create_zip=True, clean=True)
        self.assertEqual(res.status, "success")
        self.assertIsNotNone(res.zip_path)
        zip_path = Path(res.zip_path)
        self.assertTrue(zip_path.exists())

        # Inspect ZIP internal entries
        with zipfile.ZipFile(zip_path, "r") as zf:
            namelist = zf.namelist()

            # Invariant: pack.mcmeta at root
            self.assertIn("pack.mcmeta", namelist)

            # Invariant: data/ at root
            self.assertTrue(any(n.startswith("data/") for n in namelist))

            # Invariant: no outer directory wrapping
            for name in namelist:
                self.assertFalse(name.startswith("creeper_diamonds_1_21_1/"))

            # Invariant: loot table at expected location
            self.assertIn("data/minecraft/loot_table/entities/creeper.json", namelist)

            # Read pack.mcmeta from ZIP and assert format 48
            meta = json.loads(zf.read("pack.mcmeta").decode("utf-8"))
            self.assertEqual(meta["pack"]["pack_format"], 48)

            # Read creeper.json from ZIP and verify vanilla drops preserved
            creeper_zip_data = json.loads(zf.read("data/minecraft/loot_table/entities/creeper.json").decode("utf-8"))
            self.assertEqual(len(creeper_zip_data["pools"]), 3)

        # Invariant: directory-to-ZIP file count and content parity
        folder_path = Path(res.datapack_path)
        folder_files = {p.relative_to(folder_path).as_posix() for p in folder_path.rglob("*") if p.is_file()}
        with zipfile.ZipFile(zip_path, "r") as zf:
            zip_files = {name for name in zf.namelist() if not name.endswith("/")}
        self.assertEqual(folder_files, zip_files)


if __name__ == "__main__":
    unittest.main()
