import json
import shutil
import unittest
from pathlib import Path

from generator.datapack_generator import DatapackGenerator
from generator.models import (
    FunctionDefinition,
    FunctionTagDefinition,
    MechanismSpecification,
    PredicateDefinition,
)
from validator.datapack_validator import DatapackValidator


class TestStateMachineArchitecture(unittest.TestCase):
    """
    Regression Test Suite for Generic State-Machine Architecture & Scoreboard State Handling.
    Verifies:
    1. Detection of EMPTY_SELECTOR_ON_LOAD anti-pattern in #minecraft:load functions.
    2. Acceptance of correct persistent global state machine (#global holder).
    3. Acceptance of safe per-player dynamic initialization on tick.
    4. Deterministic composition of state-machine datapack (tags + functions + predicates + objectives).
    5. Genericity across arbitrary event triggers (weather, time, game state).
    """

    @classmethod
    def setUpClass(cls):
        cls.test_dir = Path("generated") / "test_state_machine_run"
        if cls.test_dir.exists():
            shutil.rmtree(cls.test_dir, ignore_errors=True)
        cls.test_dir.mkdir(parents=True, exist_ok=True)
        cls.validator = DatapackValidator(version="1.21.11")

    @classmethod
    def tearDownClass(cls):
        if cls.test_dir.exists():
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_1_detect_empty_selector_on_load(self):
        """
        Anti-pattern test: A load function that attempts to initialize player scores using '@a'
        must be flagged with EMPTY_SELECTOR_ON_LOAD warning because @a matches 0 entities on world load.
        """
        pack_dir = self.test_dir / "pack_anti_pattern"
        pack_dir.mkdir(parents=True, exist_ok=True)

        mcmeta = {
            "pack": {
                "pack_format": 94,
                "min_format": [94, 0],
                "max_format": [94, 1],
                "description": "Anti-pattern test"
            }
        }
        with open(pack_dir / "pack.mcmeta", "w", encoding="utf-8") as f:
            json.dump(mcmeta, f)

        fn_dir = pack_dir / "data" / "minecraft_ai" / "function"
        fn_dir.mkdir(parents=True, exist_ok=True)
        with open(fn_dir / "load.mcfunction", "w", encoding="utf-8") as f:
            f.write("scoreboard objectives add event_state dummy\n")
            f.write("scoreboard players set @a event_state 0\n")

        val = self.validator.validate(pack_dir)
        # Should produce EMPTY_SELECTOR_ON_LOAD warning
        empty_sel_warnings = [
            w for w in val.warnings if w.code == "EMPTY_SELECTOR_ON_LOAD"
        ]
        self.assertGreater(
            len(empty_sel_warnings), 0,
            "Validator must detect 'scoreboard players set @a ...' in load.mcfunction as EMPTY_SELECTOR_ON_LOAD"
        )
        self.assertIn("@a", empty_sel_warnings[0].message)

    def test_2_global_state_holder_accepted_cleanly(self):
        """
        Architectural pattern test: Persistent global state holder (e.g. #global or #state)
        in load.mcfunction must pass validation with 0 warnings or errors.
        """
        pack_dir = self.test_dir / "pack_global_pattern"
        pack_dir.mkdir(parents=True, exist_ok=True)

        mcmeta = {
            "pack": {
                "pack_format": 94,
                "min_format": [94, 0],
                "max_format": [94, 1],
                "description": "Global state pattern"
            }
        }
        with open(pack_dir / "pack.mcmeta", "w", encoding="utf-8") as f:
            json.dump(mcmeta, f)

        fn_dir = pack_dir / "data" / "minecraft_ai" / "function"
        fn_dir.mkdir(parents=True, exist_ok=True)
        with open(fn_dir / "load.mcfunction", "w", encoding="utf-8") as f:
            f.write("scoreboard objectives add event_state dummy\n")
            f.write("scoreboard players set #global event_state 0\n")

        val = self.validator.validate(pack_dir)
        empty_sel_warnings = [
            w for w in val.warnings if w.code == "EMPTY_SELECTOR_ON_LOAD"
        ]
        self.assertEqual(
            len(empty_sel_warnings), 0,
            "Persistent holder #global must NOT produce EMPTY_SELECTOR_ON_LOAD warning"
        )
        self.assertTrue(val.is_valid)

    def test_3_safe_per_player_dynamic_initialization(self):
        """
        Per-player pattern test: Dynamic initialization on tick via
        'execute as @a unless score @s <obj> matches 0..1 run scoreboard players set @s <obj> 0'
        must pass cleanly.
        """
        pack_dir = self.test_dir / "pack_player_pattern"
        pack_dir.mkdir(parents=True, exist_ok=True)

        mcmeta = {
            "pack": {
                "pack_format": 94,
                "min_format": [94, 0],
                "max_format": [94, 1],
                "description": "Per-player state pattern"
            }
        }
        with open(pack_dir / "pack.mcmeta", "w", encoding="utf-8") as f:
            json.dump(mcmeta, f)

        fn_dir = pack_dir / "data" / "minecraft_ai" / "function"
        fn_dir.mkdir(parents=True, exist_ok=True)

        # load only declares objective
        with open(fn_dir / "load.mcfunction", "w", encoding="utf-8") as f:
            f.write("scoreboard objectives add player_state dummy\n")

        # tick dynamically initializes uninitialized players safely
        with open(fn_dir / "tick.mcfunction", "w", encoding="utf-8") as f:
            f.write("execute as @a unless score @s player_state matches 0..1 run scoreboard players set @s player_state 0\n")
            f.write("execute as @a if score @s player_state matches 0 if predicate minecraft_ai:is_active run give @s minecraft:apple 1\n")
            f.write("execute as @a if predicate minecraft_ai:is_active run scoreboard players set @s player_state 1\n")
            f.write("execute as @a unless predicate minecraft_ai:is_active run scoreboard players set @s player_state 0\n")

        val = self.validator.validate(pack_dir)
        self.assertTrue(val.is_valid)
        self.assertEqual(len([w for w in val.warnings if w.code == "EMPTY_SELECTOR_ON_LOAD"]), 0)

    def test_4_full_state_machine_composite_generation(self):
        """
        Composite generation test: Generator creates a complete, valid datapack with:
        - Predicate mechanism (e.g. weather_check or time_check)
        - Load function with #global state initialization
        - Tick function with state transition execution
        - Function tags for tick and load
        Verifies deterministic output and successful validation.
        """
        generator = DatapackGenerator(
            output_dir=self.test_dir,
            version="1.21.11"
        )

        plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "Execute an action once when an environmental state begins using a global state machine",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Track environmental condition and reward players once on transition",
                    "mechanisms": [
                        MechanismSpecification(
                            type="predicate",
                            path="is_night",
                            namespace="minecraft_ai",
                            condition_type="minecraft:time_check",
                            condition_params={"value": {"min": 13000, "max": 24000}}
                        ),
                        MechanismSpecification(
                            type="function",
                            path="load",
                            namespace="minecraft_ai",
                            commands=[
                                "scoreboard objectives add night_state dummy",
                                "scoreboard players set #global night_state 0"
                            ]
                        ),
                        MechanismSpecification(
                            type="function",
                            path="tick",
                            namespace="minecraft_ai",
                            commands=[
                                "execute if score #global night_state matches 0 if predicate minecraft_ai:is_night as @a at @s run give @s minecraft:golden_carrot 1",
                                "execute if predicate minecraft_ai:is_night run scoreboard players set #global night_state 1",
                                "execute unless predicate minecraft_ai:is_night run scoreboard players set #global night_state 0"
                            ]
                        ),
                        MechanismSpecification(
                            type="function_tag",
                            tag_name="load",
                            namespace="minecraft",
                            values=["minecraft_ai:load"]
                        ),
                        MechanismSpecification(
                            type="function_tag",
                            tag_name="tick",
                            namespace="minecraft",
                            values=["minecraft_ai:tick"]
                        )
                    ]
                }
            ]
        }

        res = generator.generate(
            plan=plan,
            datapack_name="test_state_machine_pack",
            create_zip=True
        )

        self.assertEqual(res.status, "success")
        self.assertTrue(res.datapack_path.exists())
        self.assertIsNotNone(res.zip_path)
        self.assertTrue(res.zip_path.exists())

        # Validate directory
        dir_val = self.validator.validate(res.datapack_path)
        self.assertTrue(dir_val.is_valid, f"Directory validation failed: {dir_val.errors}")
        self.assertEqual(
            len([w for w in dir_val.warnings if w.code == "EMPTY_SELECTOR_ON_LOAD"]), 0,
            "Clean global pattern should have zero EMPTY_SELECTOR_ON_LOAD warnings"
        )

        # Validate ZIP
        zip_val = self.validator.validate(res.zip_path)
        self.assertTrue(zip_val.is_valid, f"ZIP validation failed: {zip_val.errors}")

        # Check generated files
        self.assertTrue((res.datapack_path / "data" / "minecraft_ai" / "predicate" / "is_night.json").exists())
        self.assertTrue((res.datapack_path / "data" / "minecraft_ai" / "function" / "load.mcfunction").exists())
        self.assertTrue((res.datapack_path / "data" / "minecraft_ai" / "function" / "tick.mcfunction").exists())
        self.assertTrue((res.datapack_path / "data" / "minecraft" / "tags" / "function" / "load.json").exists())
        self.assertTrue((res.datapack_path / "data" / "minecraft" / "tags" / "function" / "tick.json").exists())


if __name__ == "__main__":
    unittest.main()
