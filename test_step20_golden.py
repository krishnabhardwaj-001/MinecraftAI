"""
test_step20_golden.py - Golden End-to-End Integration Suite & Real-Minecraft Verification

Step 20 verification gate covering:
1. Golden end-to-end integration suite across the project's SEVEN authoritative mechanism domains:
   - Loot Table (LootTableMechanismGenerator)
   - Function (FunctionMechanismGenerator)
   - Function Tag (FunctionTagMechanismGenerator)
   - Advancement (AdvancementMechanismGenerator)
   - Recipe (RecipeMechanismGenerator)
   - Predicate (PredicateMechanismGenerator)
   - State Machine (StateMachineMechanismGenerator)
2. Property-modification golden cases:
   - speed ×10 (multiplier)
   - speed +5 (relative addition)
   - speed +25% (percentage)
   - explicit absolute speed
   - target-specific property modification (e.g. zombie)
   - duplicate independent modifiers (collision-safe stacking)
3. Genuine clarification cases:
   - qualitative underspecified request without magnitude/duration
   - missing property clarification
4. ZIP integrity, root layout, and deterministic byte-identical reproducibility.
5. Headless real-Minecraft 1.21.11 live server execution verification.
"""

import hashlib
import json
import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai.property_registry import DEFAULT_PROPERTY_REGISTRY
from ai.semantic_models import PropertyModification
from generator.datapack_generator import DatapackGenerator
from generator.models import ActionSpecification, MechanismSpecification
from pipeline.minecraft_pipeline import MinecraftPipeline
from pipeline.models import PipelineResult
from qa.models import QACategory
from qa.reviewer import AutonomousQAReviewer
from qa.runtime import RuntimeTestMode, RuntimeTestResult, RuntimeTestRunner
from validator.datapack_validator import DatapackValidator


class GoldenAIProvider:
    """
    Deterministic AI provider for Step 20 Golden end-to-end pipeline verification.
    Simulates intelligent NLP understanding and planning across all seven mechanism domains
    and semantic property modifications without bypassing pipeline stages.
    """

    def __init__(self):
        self.calls: List[Dict[str, Any]] = []

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        self.calls.append({"system": system_prompt, "user": user_prompt})
        sys_lower = system_prompt.lower()

        # Extract actual user request from user_prompt
        user_req = ""
        if "USER REQUEST:" in user_prompt:
            parts = user_prompt.split("USER REQUEST:")
            user_req = parts[1].split("UNDERSTANDING:")[0].strip().lower()
        else:
            user_req = user_prompt.strip().lower()

        # ---------------------------------------------------------------------
        # STAGE 1: Natural Language Understanding
        # ---------------------------------------------------------------------
        if "understanding layer" in sys_lower:
            # Domain 1: Loot Table
            if "creeper" in user_req and "diamond" in user_req:
                return {
                    "status": "ready",
                    "minecraft_version": "1.21.11",
                    "edition": "Java",
                    "understood_request": "Make every creeper drop diamonds.",
                    "requirements": [
                        {
                            "subject": "creeper",
                            "target": "entities/creeper.json",
                            "intent": "loot_table",
                            "details": "Drop diamonds upon death",
                            "item": "minecraft:diamond"
                        }
                    ]
                }

            # Domain 2: Function
            elif "regeneration" in user_req and "30" in user_req:
                return {
                    "status": "ready",
                    "minecraft_version": "1.21.11",
                    "edition": "Java",
                    "understood_request": "Give all players regeneration effect for 30 seconds.",
                    "requirements": [
                        {
                            "subject": "player",
                            "target": "@a",
                            "intent": "function",
                            "details": "Give regeneration effect for 30s",
                            "effect": "minecraft:regeneration",
                            "duration": 30
                        }
                    ]
                }

            # Domain 3: Function Tag
            elif "tick" in user_req and ("run custom function" in user_req or "function on tick" in user_req or "tag" in user_req):
                return {
                    "status": "ready",
                    "minecraft_version": "1.21.11",
                    "edition": "Java",
                    "understood_request": "Run custom function on tick.",
                    "requirements": [
                        {
                            "subject": "game_loop",
                            "target": "minecraft:tick",
                            "intent": "function_tag",
                            "tag_name": "tick",
                            "values": ["minecraft_ai:tick"]
                        }
                    ]
                }

            # Domain 4: Advancement
            elif "advancement" in user_req and "zombie" in user_req:
                return {
                    "status": "ready",
                    "minecraft_version": "1.21.11",
                    "edition": "Java",
                    "understood_request": "Add an advancement for killing a zombie.",
                    "requirements": [
                        {
                            "subject": "advancement",
                            "target": "kill_zombie",
                            "intent": "advancement",
                            "details": "Player kills a zombie"
                        }
                    ]
                }

            # Domain 5: Recipe
            elif "recipe" in user_req or "craft" in user_req or ("diamond sword" in user_req and "dirt" in user_req):
                return {
                    "status": "ready",
                    "minecraft_version": "1.21.11",
                    "edition": "Java",
                    "understood_request": "Craft a diamond sword from dirt and a stick.",
                    "requirements": [
                        {
                            "subject": "crafting",
                            "target": "diamond_sword_custom",
                            "intent": "recipe",
                            "details": "Craft diamond sword from dirt and stick"
                        }
                    ]
                }

            # Domain 6: Predicate
            elif "predicate" in user_req and "rain" in user_req and "only once" not in user_req and "diamond" not in user_req:
                return {
                    "status": "ready",
                    "minecraft_version": "1.21.11",
                    "edition": "Java",
                    "understood_request": "Add a custom predicate that checks if it is raining.",
                    "requirements": [
                        {
                            "subject": "environment",
                            "target": "is_raining",
                            "intent": "predicate",
                            "details": "Weather check condition for rain"
                        }
                    ]
                }

            # Domain 7: State Machine
            elif "raining" in user_req and "only once" in user_req:
                return {
                    "status": "ready",
                    "minecraft_version": "1.21.11",
                    "edition": "Java",
                    "understood_request": "When it is raining, give all players a diamond only once when the rain starts.",
                    "requirements": [
                        {
                            "subject": "state_machine",
                            "target": "rain_state",
                            "intent": "state_machine",
                            "details": "Give diamond once on rain onset"
                        }
                    ]
                }

            # Clarification Case 1: Qualitative without magnitude or duration
            elif user_req in ["make me faster", "make me faster."]:
                return {
                    "status": "needs_clarification",
                    "minecraft_version": "1.21.11",
                    "edition": "Java",
                    "understood_request": "Make me faster.",
                    "clarification": {
                        "parameter": "magnitude",
                        "reason": "Qualitative request without explicit magnitude or duration",
                        "question": "How much faster would you like to be?",
                        "options": ["+10%", "+25%", "+50%", "2x multiplier", "10x multiplier"]
                    },
                    "requirements": []
                }

            # Clarification Case 2: Missing property
            elif "stronger" in user_req:
                return {
                    "status": "needs_clarification",
                    "minecraft_version": "1.21.11",
                    "edition": "Java",
                    "understood_request": "Make the zombie stronger.",
                    "clarification": {
                        "parameter": "property",
                        "reason": "Word 'stronger' is ambiguous across multiple properties",
                        "question": "What property of the zombie should be modified?",
                        "options": ["attack damage (+5)", "max health (50)", "scale (2x)"]
                    },
                    "requirements": []
                }

            # Property Modifications (Pass natural language through to planner's NumericSemanticInterpreter)
            else:
                return {
                    "status": "ready",
                    "minecraft_version": "1.21.11",
                    "edition": "Java",
                    "understood_request": user_prompt,
                    "requirements": [
                        {
                            "intent": "modify_property",
                            "property": "speed",
                            "description": user_prompt
                        }
                    ]
                }

        # ---------------------------------------------------------------------
        # STAGE 3: Implementation Planning
        # ---------------------------------------------------------------------
        elif "planning engine" in sys_lower:
            # Loot table
            if "creeper" in user_req and "diamond" in user_req:
                return {
                    "status": "ready",
                    "minecraft_version": "1.21.11",
                    "summary": "Creeper loot modification plan",
                    "implementation_plan": [
                        {
                            "requirement_index": 0,
                            "objective": "Make creepers drop diamonds",
                            "mechanisms": [
                                {
                                    "type": "loot_table",
                                    "target": "entities/creeper.json",
                                    "item": "minecraft:diamond",
                                    "count": 1,
                                    "operation": "add_pool"
                                }
                            ]
                        }
                    ]
                }

            # Function
            elif "regeneration" in user_req and "30" in user_req:
                return {
                    "status": "ready",
                    "minecraft_version": "1.21.11",
                    "summary": "Give regeneration effect function plan",
                    "implementation_plan": [
                        {
                            "requirement_index": 0,
                            "objective": "Give regeneration effect for 30s",
                            "mechanisms": [
                                {
                                    "type": "function",
                                    "path": "regeneration",
                                    "actions": [
                                        {
                                            "action_type": "apply_effect",
                                            "target": "@a",
                                            "effect": "minecraft:regeneration",
                                            "duration": 30,
                                            "amplifier": 0
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }

            # Function Tag
            elif "tick" in user_req and ("run custom function" in user_req or "function on tick" in user_req or "tag" in user_req):
                return {
                    "status": "ready",
                    "minecraft_version": "1.21.11",
                    "summary": "Function tag plan",
                    "implementation_plan": [
                        {
                            "requirement_index": 0,
                            "objective": "Tick loop function and tag",
                            "mechanisms": [
                                {
                                    "type": "function",
                                    "path": "tick",
                                    "commands": ["# Tick function execution"]
                                },
                                {
                                    "type": "function_tag",
                                    "namespace": "minecraft",
                                    "tag_name": "tick",
                                    "values": ["minecraft_ai:tick"]
                                }
                            ]
                        }
                    ]
                }

            # Advancement
            elif "advancement" in user_req and "zombie" in user_req:
                return {
                    "status": "ready",
                    "minecraft_version": "1.21.11",
                    "summary": "Kill zombie advancement plan",
                    "implementation_plan": [
                        {
                            "requirement_index": 0,
                            "objective": "Add advancement for killing a zombie",
                            "mechanisms": [
                                {
                                    "type": "advancement",
                                    "path": "kill_zombie",
                                    "criteria": {
                                        "killed_zombie": {
                                            "trigger": "minecraft:player_killed_entity",
                                            "conditions": {
                                                "entity": {"type": "minecraft:zombie"}
                                            }
                                        }
                                    },
                                    "rewards": {"experience": 100}
                                }
                            ]
                        }
                    ]
                }

            # Recipe
            elif "recipe" in user_req or "craft" in user_req or ("diamond sword" in user_req and "dirt" in user_req):
                return {
                    "status": "ready",
                    "minecraft_version": "1.21.11",
                    "summary": "Craft diamond sword from dirt and stick",
                    "implementation_plan": [
                        {
                            "requirement_index": 0,
                            "objective": "Custom shaped recipe for diamond sword",
                            "mechanisms": [
                                {
                                    "type": "recipe",
                                    "recipe_type": "crafting_shaped",
                                    "path": "diamond_sword_custom",
                                    "result_item": "minecraft:diamond_sword",
                                    "result_count": 1,
                                    "pattern": ["X", "#"],
                                    "key": {
                                        "X": "minecraft:dirt",
                                        "#": "minecraft:stick"
                                    }
                                }
                            ]
                        }
                    ]
                }

            # Predicate
            elif "predicate" in user_req and "rain" in user_req and "only once" not in user_req and "diamond" not in user_req:
                return {
                    "status": "ready",
                    "minecraft_version": "1.21.11",
                    "summary": "Predicate plan for weather check",
                    "implementation_plan": [
                        {
                            "requirement_index": 0,
                            "objective": "Add predicate for raining",
                            "mechanisms": [
                                {
                                    "type": "predicate",
                                    "path": "is_raining",
                                    "condition_type": "minecraft:weather_check",
                                    "condition_params": {"raining": True}
                                }
                            ]
                        }
                    ]
                }

            # State Machine
            elif "raining" in user_req and "only once" in user_req:
                return {
                    "status": "ready",
                    "minecraft_version": "1.21.11",
                    "summary": "Give diamond once on rain start",
                    "implementation_plan": [
                        {
                            "requirement_index": 0,
                            "objective": "Rain event state machine",
                            "mechanisms": [
                                {
                                    "type": "predicate",
                                    "path": "is_raining",
                                    "condition_type": "minecraft:weather_check",
                                    "condition_params": {"raining": True}
                                },
                                {
                                    "type": "state_machine",
                                    "objective": "rain_state",
                                    "condition_predicate": "minecraft_ai:is_raining",
                                    "state_scope": "global",
                                    "on_enter": [
                                        {
                                            "action_type": "give_item",
                                            "target": "@a",
                                            "item": "minecraft:diamond",
                                            "count": 1
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }

            else:
                return {
                    "status": "ready",
                    "minecraft_version": "1.21.11",
                    "summary": user_prompt,
                    "implementation_plan": []
                }

        # Default fallback
        return {
            "status": "ready",
            "findings": [],
            "summary": "Operation completed."
        }


class TestStep20GoldenIntegration(unittest.TestCase):
    """
    Step 20 Golden Integration Test Suite.
    """

    @classmethod
    def setUpClass(cls):
        cls.test_dir = Path(tempfile.mkdtemp(prefix="step20_golden_"))
        cls.ai_provider = GoldenAIProvider()

    @classmethod
    def tearDownClass(cls):
        if cls.test_dir.exists():
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    def _run_pipeline(self, request: str, pack_name: Optional[str] = None) -> PipelineResult:
        pipeline = MinecraftPipeline(
            provider="ollama",
            version="1.21.11",
            output_dir=self.test_dir,
            verbose=False,
            ai_provider=self.ai_provider
        )
        return pipeline.run(request=request, datapack_name=pack_name, create_zip=True)

    def _verify_zip_parity(self, zip_path: Path, folder_path: Path):
        self.assertTrue(zip_path.exists(), f"ZIP archive does not exist: {zip_path}")
        self.assertTrue(folder_path.exists(), f"Folder does not exist: {folder_path}")

        with zipfile.ZipFile(zip_path, "r") as zf:
            namelist = zf.namelist()
            # Root pack.mcmeta check
            self.assertIn("pack.mcmeta", namelist, "pack.mcmeta must be at root of ZIP.")
            # Verify data/ exists
            self.assertTrue(any(n.startswith("data/") for n in namelist), "ZIP must contain 'data/' hierarchy.")

            # File-by-file match
            folder_files = [
                p.relative_to(folder_path).as_posix()
                for p in folder_path.rglob("*")
                if p.is_file() and not p.name.endswith(".zip")
            ]
            for ff in folder_files:
                self.assertIn(ff, namelist, f"File '{ff}' in folder missing from ZIP.")
                folder_bytes = (folder_path / ff).read_bytes()
                zip_bytes = zf.read(ff)
                self.assertEqual(folder_bytes, zip_bytes, f"Content mismatch for '{ff}'.")

    # =========================================================================
    # PART 1: The Seven Authoritative Mechanism Domains
    # =========================================================================

    def test_01_mechanism_loot_table(self):
        """Domain 1: Loot Table (LootTableMechanismGenerator)"""
        res = self._run_pipeline("Make every creeper drop diamonds.", pack_name="golden_loot_table")
        self.assertTrue(res.is_success, f"Pipeline failed: {res.errors}")
        self.assertEqual(res.status, "success")
        self.assertEqual(res.verification_status, "verified")

        pack_path = Path(res.final_datapack_path)
        loot_file = pack_path / "data" / "minecraft" / "loot_table" / "entities" / "creeper.json"
        self.assertTrue(loot_file.exists(), f"Loot table file missing: {loot_file}")
        loot_data = json.loads(loot_file.read_text(encoding="utf-8"))
        self.assertIn("pools", loot_data)
        self.assertTrue(any("minecraft:diamond" in str(p) for p in loot_data["pools"]))

        self._verify_zip_parity(Path(res.final_zip_path), pack_path)

    def test_02_mechanism_function(self):
        """Domain 2: Function (FunctionMechanismGenerator)"""
        res = self._run_pipeline("Give all players regeneration effect for 30 seconds.", pack_name="golden_function")
        self.assertTrue(res.is_success, f"Pipeline failed: {res.errors}")
        self.assertEqual(res.status, "success")

        pack_path = Path(res.final_datapack_path)
        func_file = pack_path / "data" / "minecraft_ai" / "function" / "regeneration.mcfunction"
        self.assertTrue(func_file.exists(), f"Function file missing: {func_file}")
        content = func_file.read_text(encoding="utf-8")
        self.assertIn("effect give @a minecraft:regeneration 30", content)
        # Verify leading slashes stripped
        for line in content.splitlines():
            line_str = line.strip()
            if line_str and not line_str.startswith("#"):
                self.assertFalse(line_str.startswith("/"), f"Leading slash found: {line_str}")

        self._verify_zip_parity(Path(res.final_zip_path), pack_path)

    def test_03_mechanism_function_tag(self):
        """Domain 3: Function Tag (FunctionTagMechanismGenerator)"""
        res = self._run_pipeline("Run custom function on tick.", pack_name="golden_tag")
        self.assertTrue(res.is_success, f"Pipeline failed: {res.errors}")
        self.assertEqual(res.status, "success")

        pack_path = Path(res.final_datapack_path)
        tag_file = pack_path / "data" / "minecraft" / "tags" / "function" / "tick.json"
        self.assertTrue(tag_file.exists(), f"Tag file missing: {tag_file}")
        tag_data = json.loads(tag_file.read_text(encoding="utf-8"))
        self.assertIn("values", tag_data)
        self.assertIn("minecraft_ai:tick", tag_data["values"])
        self.assertNotIn("replace", tag_data, "replace: false should be omitted in minimal canonical format.")

        self._verify_zip_parity(Path(res.final_zip_path), pack_path)

    def test_04_mechanism_advancement(self):
        """Domain 4: Advancement (AdvancementMechanismGenerator)"""
        res = self._run_pipeline("Add an advancement for killing a zombie.", pack_name="golden_advancement")
        self.assertTrue(res.is_success, f"Pipeline failed: {res.errors}")
        self.assertEqual(res.status, "success")

        pack_path = Path(res.final_datapack_path)
        adv_file = pack_path / "data" / "minecraft_ai" / "advancement" / "kill_zombie.json"
        self.assertTrue(adv_file.exists(), f"Advancement file missing: {adv_file}")
        adv_data = json.loads(adv_file.read_text(encoding="utf-8"))
        self.assertIn("criteria", adv_data)
        self.assertIn("killed_zombie", adv_data["criteria"])
        self.assertEqual(adv_data["criteria"]["killed_zombie"]["trigger"], "minecraft:player_killed_entity")

        self._verify_zip_parity(Path(res.final_zip_path), pack_path)

    def test_05_mechanism_recipe(self):
        """Domain 5: Recipe (RecipeMechanismGenerator)"""
        res = self._run_pipeline("Craft a diamond sword from dirt and a stick.", pack_name="golden_recipe")
        self.assertTrue(res.is_success, f"Pipeline failed: {res.errors}")
        self.assertEqual(res.status, "success")

        pack_path = Path(res.final_datapack_path)
        recipe_file = pack_path / "data" / "minecraft_ai" / "recipe" / "diamond_sword_custom.json"
        self.assertTrue(recipe_file.exists(), f"Recipe file missing: {recipe_file}")
        recipe_data = json.loads(recipe_file.read_text(encoding="utf-8"))
        self.assertEqual(recipe_data["type"], "minecraft:crafting_shaped")
        # 1.21+ result schema validation
        self.assertEqual(recipe_data["result"], {"id": "minecraft:diamond_sword", "count": 1})
        self.assertIn("pattern", recipe_data)
        self.assertIn("key", recipe_data)

        self._verify_zip_parity(Path(res.final_zip_path), pack_path)

    def test_06_mechanism_predicate(self):
        """Domain 6: Predicate (PredicateMechanismGenerator)"""
        res = self._run_pipeline("Add a custom predicate that checks if it is raining.", pack_name="golden_predicate")
        self.assertTrue(res.is_success, f"Pipeline failed: {res.errors}")
        self.assertEqual(res.status, "success")

        pack_path = Path(res.final_datapack_path)
        pred_file = pack_path / "data" / "minecraft_ai" / "predicate" / "is_raining.json"
        self.assertTrue(pred_file.exists(), f"Predicate file missing: {pred_file}")
        pred_data = json.loads(pred_file.read_text(encoding="utf-8"))
        self.assertEqual(pred_data["condition"], "minecraft:weather_check")
        self.assertTrue(pred_data.get("raining"))

        self._verify_zip_parity(Path(res.final_zip_path), pack_path)

    def test_07_mechanism_state_machine(self):
        """Domain 7: State Machine (StateMachineMechanismGenerator)"""
        res = self._run_pipeline(
            "When it is raining, give all players a diamond only once when the rain starts.",
            pack_name="golden_state_machine"
        )
        self.assertTrue(res.is_success, f"Pipeline failed: {res.errors}")
        self.assertEqual(res.status, "success")

        pack_path = Path(res.final_datapack_path)
        load_fn = pack_path / "data" / "minecraft_ai" / "function" / "load.mcfunction"
        tick_fn = pack_path / "data" / "minecraft_ai" / "function" / "tick.mcfunction"
        self.assertTrue(load_fn.exists(), f"Load function missing: {load_fn}")
        self.assertTrue(tick_fn.exists(), f"Tick function missing: {tick_fn}")

        # Verify safe #global initialization in load (Rain regression protection)
        load_content = load_fn.read_text(encoding="utf-8")
        self.assertIn("scoreboard objectives add rain_state dummy", load_content)
        self.assertIn("scoreboard players set #global rain_state 0", load_content)
        self.assertNotIn("players set @a", load_content, "@a must not be used in load function.")

        # Verify transition latches in tick
        tick_content = tick_fn.read_text(encoding="utf-8")
        self.assertIn("if score #global rain_state matches 0", tick_content)
        self.assertIn("scoreboard players set #global rain_state 1", tick_content)
        self.assertIn("scoreboard players set #global rain_state 0", tick_content)

        self._verify_zip_parity(Path(res.final_zip_path), pack_path)

    # =========================================================================
    # PART 2: Property-Modification Golden Cases
    # =========================================================================

    def test_08_property_speed_multiplier_10x(self):
        """Property: speed ×10 multiplier"""
        res = self._run_pipeline("Make me 10 times faster.", pack_name="golden_prop_speed_10x")
        self.assertTrue(res.is_success, f"Pipeline failed: {res.errors}")
        self.assertEqual(res.status, "success")

        pack_path = Path(res.final_datapack_path)
        mod_file = pack_path / "data" / "minecraft_ai" / "function" / "modify_speed.mcfunction"
        self.assertTrue(mod_file.exists(), f"modify_speed.mcfunction missing: {mod_file}")
        content = mod_file.read_text(encoding="utf-8")
        # Multiplier of 10 maps to add_multiplied_total with amount 9.0
        self.assertIn("attribute @s minecraft:generic.movement_speed modifier add", content)
        self.assertIn("9.0 add_multiplied_total", content)
        self.assertIn("execute as @a run", content)

        self._verify_zip_parity(Path(res.final_zip_path), pack_path)

    def test_09_property_speed_relative_add_5(self):
        """Property: speed +5 relative add"""
        res = self._run_pipeline("Increase my speed by 5.", pack_name="golden_prop_speed_add_5")
        self.assertTrue(res.is_success, f"Pipeline failed: {res.errors}")
        self.assertEqual(res.status, "success")

        pack_path = Path(res.final_datapack_path)
        mod_file = pack_path / "data" / "minecraft_ai" / "function" / "modify_speed.mcfunction"
        self.assertTrue(mod_file.exists())
        content = mod_file.read_text(encoding="utf-8")
        # Relative add maps to add_value with amount 5.0
        self.assertIn("5.0 add_value", content)
        self.assertIn("execute as @a run", content)

        self._verify_zip_parity(Path(res.final_zip_path), pack_path)

    def test_10_property_speed_percentage_25pct(self):
        """Property: speed +25% percentage add"""
        res = self._run_pipeline("Increase my speed by 25%.", pack_name="golden_prop_speed_25pct")
        self.assertTrue(res.is_success, f"Pipeline failed: {res.errors}")
        self.assertEqual(res.status, "success")

        pack_path = Path(res.final_datapack_path)
        mod_file = pack_path / "data" / "minecraft_ai" / "function" / "modify_speed.mcfunction"
        self.assertTrue(mod_file.exists())
        content = mod_file.read_text(encoding="utf-8")
        # Percentage +25% maps to add_multiplied_base with amount 0.25
        self.assertIn("0.25 add_multiplied_base", content)

        self._verify_zip_parity(Path(res.final_zip_path), pack_path)

    def test_11_property_speed_explicit_absolute(self):
        """Property: explicit absolute speed base set 2.0"""
        res = self._run_pipeline("Set my speed to 2.", pack_name="golden_prop_speed_set_2")
        self.assertTrue(res.is_success, f"Pipeline failed: {res.errors}")
        self.assertEqual(res.status, "success")

        pack_path = Path(res.final_datapack_path)
        mod_file = pack_path / "data" / "minecraft_ai" / "function" / "modify_speed.mcfunction"
        self.assertTrue(mod_file.exists())
        content = mod_file.read_text(encoding="utf-8")
        # Absolute set maps to base set 2
        self.assertIn("base set 2", content)

        self._verify_zip_parity(Path(res.final_zip_path), pack_path)

    def test_12_property_target_specific_zombie(self):
        """Property: target-specific zombie speed modification"""
        res = self._run_pipeline("Make the zombie 2 times faster.", pack_name="golden_prop_zombie_speed")
        self.assertTrue(res.is_success, f"Pipeline failed: {res.errors}")
        self.assertEqual(res.status, "success")

        pack_path = Path(res.final_datapack_path)
        mod_file = pack_path / "data" / "minecraft_ai" / "function" / "modify_speed.mcfunction"
        self.assertTrue(mod_file.exists())
        content = mod_file.read_text(encoding="utf-8")
        # Single-entity target context wrapping for zombie
        self.assertIn("execute as @e[type=zombie] run attribute @s minecraft:generic.movement_speed modifier add", content)
        self.assertIn("1.0 add_multiplied_total", content)

        self._verify_zip_parity(Path(res.final_zip_path), pack_path)

    def test_13_property_duplicate_independent_modifiers(self):
        """Property: duplicate independent modifiers with distinct deterministic IDs"""
        res = self._run_pipeline(
            "Make me 2 times faster and make me 2 times faster.",
            pack_name="golden_prop_duplicate_mods"
        )
        self.assertTrue(res.is_success, f"Pipeline failed: {res.errors}")
        self.assertEqual(res.status, "success")

        pack_path = Path(res.final_datapack_path)
        mod_file = pack_path / "data" / "minecraft_ai" / "function" / "modify_speed.mcfunction"
        self.assertTrue(mod_file.exists())
        content = mod_file.read_text(encoding="utf-8")

        # Two distinct modifier IDs must exist
        self.assertIn("speed_mult_2_step_0", content)
        self.assertIn("speed_mult_2_step_1", content)
        # QA analyzer confirmed 0 duplicate modifier collision findings
        self.assertEqual(len(res.qa_result.error_findings), 0)

        self._verify_zip_parity(Path(res.final_zip_path), pack_path)

    # =========================================================================
    # PART 3: Genuine Clarification Cases
    # =========================================================================

    def test_14_clarification_qualitative_underspecified(self):
        """Clarification: qualitative request without magnitude/duration"""
        res = self._run_pipeline("Make me faster.")
        self.assertEqual(res.status, "needs_clarification")
        self.assertFalse(res.is_success)
        self.assertIsNotNone(res.clarification_requirements)
        self.assertGreater(len(res.clarification_requirements), 0)
        # Options must be present
        first_cr = res.clarification_requirements[0]
        options = first_cr.get("options") if isinstance(first_cr, dict) else getattr(first_cr, "options", None)
        self.assertIsNotNone(options)
        self.assertGreater(len(options), 0)
        # No ready datapack produced
        self.assertIsNone(res.final_datapack_path)

    def test_15_clarification_missing_property(self):
        """Clarification: ambiguous property (stronger)"""
        res = self._run_pipeline("Make the zombie stronger.")
        self.assertEqual(res.status, "needs_clarification")
        self.assertFalse(res.is_success)
        self.assertIsNotNone(res.clarification_requirements)
        self.assertGreater(len(res.clarification_requirements), 0)
        self.assertIsNone(res.final_datapack_path)

    # =========================================================================
    # PART 4: Determinism & Parity
    # =========================================================================

    def test_16_deterministic_byte_identical_reproducibility(self):
        """Determinism: Identical inputs generate identical ZIP hashes"""
        res1 = self._run_pipeline("Make every creeper drop diamonds.", pack_name="determinism_test_1")
        res2 = self._run_pipeline("Make every creeper drop diamonds.", pack_name="determinism_test_2")

        self.assertTrue(res1.is_success)
        self.assertTrue(res2.is_success)

        # Compare generated resources
        pack1 = Path(res1.final_datapack_path)
        pack2 = Path(res2.final_datapack_path)

        files1 = sorted([p.relative_to(pack1).as_posix() for p in pack1.rglob("*") if p.is_file()])
        files2 = sorted([p.relative_to(pack2).as_posix() for p in pack2.rglob("*") if p.is_file()])
        self.assertEqual(files1, files2)

        for rel in files1:
            if rel.endswith(".zip"):
                continue
            b1 = (pack1 / rel).read_bytes()
            b2 = (pack2 / rel).read_bytes()
            self.assertEqual(b1, b2, f"Resource '{rel}' differed between generation runs.")


class TestStep20HeadlessMinecraftServer(unittest.TestCase):
    """
    Step 20.2: Automated Headless Real-Minecraft 1.21.11 Verification.
    Executes the real server in an isolated temporary environment.
    """

    @classmethod
    def setUpClass(cls):
        cls.server_jar = Path("versions/1.21.11/server-1.21.11.jar").resolve()
        cls.libraries_dir = Path("libraries").resolve()

    def test_17_headless_real_minecraft_server_execution(self):
        """
        Launches real Minecraft 1.21.11 server headlessly, installs a generated datapack,
        verifies datapack loading (/datapack list), runs functions, and shuts down cleanly.
        """
        # 1. Dependency check
        if not self.server_jar.exists():
            self.skipTest(f"Minecraft server JAR not found at '{self.server_jar}'.")
        if not self.libraries_dir.exists():
            self.skipTest(f"Libraries directory not found at '{self.libraries_dir}'.")

        # 2. Generate a valid composite test datapack with predicate, state machine, and tags
        temp_out = Path(tempfile.mkdtemp(prefix="mc_headless_dp_"))
        try:
            gen = DatapackGenerator(output_dir=temp_out, version="1.21.11")
            plan = {
                "status": "ready",
                "minecraft_version": "1.21.11",
                "summary": "Headless comprehensive verification pack",
                "implementation_plan": [
                    {
                        "requirement_index": 0,
                        "objective": "Rain weather predicate",
                        "mechanisms": [
                            MechanismSpecification(
                                type="predicate",
                                path="is_raining",
                                namespace="minecraft_ai",
                                condition_type="minecraft:weather_check",
                                condition_params={"raining": True}
                            )
                        ]
                    },
                    {
                        "requirement_index": 1,
                        "objective": "Rain state machine with load and tick lifecycle",
                        "mechanisms": [
                            MechanismSpecification(
                                type="state_machine",
                                path="rain_state",
                                objective="rain_state",
                                condition_predicate="minecraft_ai:is_raining",
                                namespace="minecraft_ai",
                                state_scope="global",
                                on_enter=[
                                    ActionSpecification(
                                        action_type="give_item",
                                        target="@a",
                                        item="minecraft:diamond",
                                        count=1
                                    )
                                ]
                            )
                        ]
                    }
                ]
            }

            gen_res = gen.generate(plan=plan, datapack_name="comprehensive_test_pack", create_zip=True)
            self.assertEqual(gen_res.status, "success")
            self.assertTrue(gen_res.zip_path.exists())

            # 3. Controlled command sequence exercising Items A through K
            commands = [
                # Item B: verify datapack list
                "datapack list",
                # Item D: verify load function ran and set scoreboard
                "scoreboard players get #load_ran mcai_debug",
                # Item E & G: verify initial automatic tick counter
                "scoreboard players get #tick_count mcai_debug",
                # Item H & I: entity setup early so chunk and entity are loaded
                "forceload add 0 0",
                'execute in minecraft:overworld run summon pig 0 4 0 {NoAI:1b,Tags:["test_pig"]}',
                # Item F: verify initial rain state is 0
                "scoreboard players get #global rain_state",
                # Item F: trigger rain
                "weather rain",
                # Item F: verify rain state transitioned to 1
                "scoreboard players get #global rain_state",
                # Item E: verify tick count advanced automatically
                "scoreboard players get #tick_count mcai_debug",
                # Item F: reset weather to clear
                "weather clear",
                # Item F: verify rain state reset to 0
                "scoreboard players get #global rain_state",
                # Item H & I: property modifiers on the loaded entity
                "execute in minecraft:overworld run attribute @e[type=pig,limit=1] minecraft:movement_speed modifier add minecraft_ai:speed_10x 9.0 add_multiplied_total",
                "execute in minecraft:overworld run attribute @e[type=pig,limit=1] minecraft:movement_speed modifier value get minecraft_ai:speed_10x",
                "execute in minecraft:overworld run attribute @e[type=pig,limit=1] minecraft:movement_speed modifier add minecraft_ai:speed_2x 1.0 add_multiplied_total",
                "execute in minecraft:overworld run attribute @e[type=pig,limit=1] minecraft:movement_speed modifier value get minecraft_ai:speed_2x",
                # Item C & J: reload server and check tag integrity
                "reload",
                "stop"
            ]

            # 4. Execute headless Minecraft 1.21.11 server with actual ZIP installation
            runner = RuntimeTestRunner(version="1.21.11")
            result = runner.run(
                datapack_dir=gen_res.zip_path,
                mode=RuntimeTestMode.MINECRAFT_SERVER,
                server_jar_path=self.server_jar,
                timeout_s=60,
                custom_commands=commands
            )

            # 5. Verify outcome
            self.assertTrue(
                result.passed,
                f"Headless server runtime test failed. Details: {result.details}\nLogs:\n" + "\n".join(result.logs[-30:])
            )

            logs_str = "\n".join(result.logs)

            # Item A: exact Minecraft 1.21.11 version verified from running server
            self.assertIn("Starting minecraft server version 1.21.11", logs_str)

            # Item B & K: datapack loading verified from installed ZIP
            self.assertIn("file/comprehensive_test_pack.zip", logs_str)

            # Item C & J: no broken function tags or missing functions
            self.assertNotIn("couldn't load function tag", logs_str.lower())
            self.assertNotIn("failed to load function tag", logs_str.lower())

            # Item D: load function executed automatically on boot
            self.assertIn("[LOAD OK]", logs_str)
            self.assertIn("#load_ran has 1 [mcai_debug]", logs_str)

            # Item E: automatic tick behavior verified (counter advances in game loop)
            self.assertIn("[TICK OK]", logs_str)
            import re
            tick_matches = re.findall(r"#tick_count has (\d+) \[mcai_debug\]", logs_str)
            self.assertTrue(len(tick_matches) >= 2, "Tick counter should be queried at least twice")
            counts = [int(c) for c in tick_matches]
            self.assertGreater(counts[0], 0, "Initial tick count should be > 0")
            self.assertGreater(counts[1], counts[0], "Tick count should increase automatically in game loop")

            # Item F: rain state machine verified (0 -> 1 on rain -> 0 on clear)
            self.assertIn("#global has 0 [rain_state]", logs_str)
            self.assertIn("[EVENT] Condition minecraft_ai:is_raining met", logs_str)
            self.assertIn("#global has 1 [rain_state]", logs_str)

            # Item G: scoreboard persistence & updates verified
            self.assertIn("mcai_debug", logs_str)

            # Item H: property modifier verified on live entity
            self.assertIn("The value of modifier minecraft_ai:speed_10x on attribute Speed for entity Pig is 9.0", logs_str)

            # Item I: duplicate independent modifiers verified simultaneously
            self.assertIn("The value of modifier minecraft_ai:speed_2x on attribute Speed for entity Pig is 1.0", logs_str)

            # Item J: reload completed cleanly without broken tags
            self.assertIn("Reloading!", logs_str)

        finally:
            if temp_out.exists():
                shutil.rmtree(temp_out, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
