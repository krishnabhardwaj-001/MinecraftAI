"""
test_step16_validator.py - Step 16.4 Static Validation & Scoreboard Safety Tests
Authoritative target: Minecraft Java 1.21.11

Tests all 40 required static validation capabilities:
 1. valid objective declaration
 2. objective name too long (>16 chars)
 3. invalid objective name (characters)
 4. valid criteria (built-in and stats)
 5. invalid criteria
 6. valid display slot (sidebar, list, below_name)
 7. invalid display slot
 8. valid team-color display slot (sidebar.team.<color>)
 9. invalid team-color display slot
10. scoreboard players set
11. scoreboard players add
12. scoreboard players remove
13. scoreboard players reset
14. scoreboard objectives remove
15. all nine scoreboard operations (=, +=, -=, *=, /=, %=, <, >, ><)
16. invalid scoreboard operation
17. valid negative set value
18. invalid negative add value
19. invalid negative remove value
20. valid 32-bit minimum (-2147483648)
21. valid 32-bit maximum (2147483647)
22. overflow above 32-bit maximum (2147483648)
23. underflow below 32-bit minimum (-2147483649)
24. valid score range comparison (exact, min..max, min.., ..max)
25. valid score-to-score comparison (<, <=, =, >=, >)
26. invalid score comparison
27. undeclared objective reference
28. declared objective used across load/tick
29. missing function tag reference
30. valid function tag
31. valid replace: true
32. valid replace: false
33. omitted replace
34. invalid non-boolean replace
35. state-machine scoreboard validation
36. lifecycle load/tick validation (load-only, tick-only, both)
37. multiple mechanisms contributing scoreboard objectives
38. multiple mechanisms contributing load/tick
39. existing Step 15 regressions
40. deterministic validation of the same generated datapack
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

from generator.datapack_generator import DatapackGenerator
from validator.datapack_validator import DatapackValidator, MIN_SCORE_32, MAX_SCORE_32


class TestStep16Validator(unittest.TestCase):
    def setUp(self):
        self.validator = DatapackValidator(version="1.21.11", expected_pack_format=94)
        self.test_dir = Path("generated") / "test_s16_validator"
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def _create_synthetic_pack(
        self,
        pack_name: str,
        functions: Dict[str, str],
        tags: Optional[Dict[str, Any]] = None,
        pack_format: int = 94,
        description: str = "Test Datapack"
    ) -> Path:
        """
        Creates a synthetic datapack on disk following Minecraft 1.21+ singular conventions:
          data/<namespace>/function/<name>.mcfunction
          data/<namespace>/tags/function/<name>.json
          pack.mcmeta
        """
        pack_dir = self.test_dir / pack_name
        if pack_dir.exists():
            shutil.rmtree(pack_dir)
        pack_dir.mkdir(parents=True, exist_ok=True)

        mcmeta = pack_dir / "pack.mcmeta"
        mcmeta_data = {
            "pack": {
                "pack_format": pack_format,
                "description": description
            }
        }
        with open(mcmeta, "w", encoding="utf-8") as f:
            json.dump(mcmeta_data, f, indent=2)

        # Write functions
        for fn_id, content in functions.items():
            if ":" in fn_id:
                ns, fn_path = fn_id.split(":", 1)
            else:
                ns, fn_path = "test", fn_id
            fn_file = pack_dir / "data" / ns / "function" / f"{fn_path}.mcfunction"
            fn_file.parent.mkdir(parents=True, exist_ok=True)
            with open(fn_file, "w", encoding="utf-8") as f:
                f.write(content)

        # Write function tags
        if tags:
            for tag_id, tag_val in tags.items():
                if ":" in tag_id:
                    ns, tag_path = tag_id.split(":", 1)
                else:
                    ns, tag_path = "minecraft", tag_id
                tag_file = pack_dir / "data" / ns / "tags" / "function" / f"{tag_path}.json"
                tag_file.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(tag_val, list):
                    tag_content = {"values": tag_val}
                elif isinstance(tag_val, dict):
                    tag_content = tag_val
                else:
                    tag_content = {"values": [str(tag_val)]}
                with open(tag_file, "w", encoding="utf-8") as f:
                    json.dump(tag_content, f, indent=2)

        return pack_dir

    # --------------------------------------------------------------------------
    # 1. Valid Objective Declaration
    # --------------------------------------------------------------------------
    def test_01_valid_objective_declaration(self):
        pack = self._create_synthetic_pack(
            "p01_valid_obj",
            functions={
                "test:load": 'scoreboard objectives add deaths deathCount "Player Deaths"\n'
            }
        )
        res = self.validator.validate(pack)
        self.assertTrue(res.is_valid, f"Expected valid objective declaration, got errors: {res.errors}")
        self.assertEqual(len(res.errors), 0)

    # --------------------------------------------------------------------------
    # 2. Objective Name Too Long (>16 chars)
    # --------------------------------------------------------------------------
    def test_02_objective_name_too_long(self):
        long_name = "objective_17chars"  # 17 chars
        pack = self._create_synthetic_pack(
            "p02_obj_too_long",
            functions={
                "test:load": f"scoreboard objectives add {long_name} dummy\n"
            }
        )
        res = self.validator.validate(pack)
        self.assertFalse(res.is_valid)
        error_codes = [e.code for e in res.errors]
        self.assertIn("INVALID_SCOREBOARD_OBJECTIVE", error_codes)
        self.assertTrue(any("exceeds maximum length of 16" in e.message for e in res.errors))

    # --------------------------------------------------------------------------
    # 3. Invalid Objective Name (Characters)
    # --------------------------------------------------------------------------
    def test_03_invalid_objective_name(self):
        bad_name = "bad$name"
        pack = self._create_synthetic_pack(
            "p03_obj_bad_char",
            functions={
                "test:load": f"scoreboard objectives add {bad_name} dummy\n"
            }
        )
        res = self.validator.validate(pack)
        self.assertFalse(res.is_valid)
        error_codes = [e.code for e in res.errors]
        self.assertIn("INVALID_SCOREBOARD_OBJECTIVE", error_codes)

    # --------------------------------------------------------------------------
    # 4. Valid Criteria (Built-in and Statistic)
    # --------------------------------------------------------------------------
    def test_04_valid_criteria(self):
        lines = [
            "scoreboard objectives add c_dummy dummy\n",
            "scoreboard objectives add c_death deathCount\n",
            "scoreboard objectives add c_kills playerKillCount\n",
            "scoreboard objectives add c_health health\n",
            "scoreboard objectives add c_mine minecraft.mined:minecraft.stone\n",
        ]
        pack = self._create_synthetic_pack(
            "p04_valid_crit",
            functions={"test:load": "".join(lines)}
        )
        res = self.validator.validate(pack)
        self.assertTrue(res.is_valid, f"Expected valid criteria, got: {res.errors}")

    # --------------------------------------------------------------------------
    # 5. Invalid Criteria
    # --------------------------------------------------------------------------
    def test_05_invalid_criteria(self):
        pack = self._create_synthetic_pack(
            "p05_invalid_crit",
            functions={
                "test:load": "scoreboard objectives add bad_crit totally_fake_criteria\n"
            }
        )
        res = self.validator.validate(pack)
        self.assertFalse(res.is_valid)
        error_codes = [e.code for e in res.errors]
        self.assertIn("INVALID_SCOREBOARD_CRITERIA", error_codes)

    # --------------------------------------------------------------------------
    # 6. Valid Display Slot
    # --------------------------------------------------------------------------
    def test_06_valid_display_slot(self):
        pack = self._create_synthetic_pack(
            "p06_valid_slot",
            functions={
                "test:load": (
                    "scoreboard objectives add my_obj dummy\n"
                    "scoreboard objectives setdisplay sidebar my_obj\n"
                )
            }
        )
        res = self.validator.validate(pack)
        self.assertTrue(res.is_valid, f"Expected valid display slot, got: {res.errors}")

    # --------------------------------------------------------------------------
    # 7. Invalid Display Slot
    # --------------------------------------------------------------------------
    def test_07_invalid_display_slot(self):
        pack = self._create_synthetic_pack(
            "p07_invalid_slot",
            functions={
                "test:load": (
                    "scoreboard objectives add my_obj dummy\n"
                    "scoreboard objectives setdisplay above_player my_obj\n"
                )
            }
        )
        res = self.validator.validate(pack)
        self.assertFalse(res.is_valid)
        error_codes = [e.code for e in res.errors]
        self.assertIn("INVALID_DISPLAY_SLOT", error_codes)

    # --------------------------------------------------------------------------
    # 8. Valid Team-Color Display Slot
    # --------------------------------------------------------------------------
    def test_08_valid_team_color_display_slot(self):
        pack = self._create_synthetic_pack(
            "p08_team_slot",
            functions={
                "test:load": (
                    "scoreboard objectives add red_obj dummy\n"
                    "scoreboard objectives setdisplay sidebar.team.red red_obj\n"
                )
            }
        )
        res = self.validator.validate(pack)
        self.assertTrue(res.is_valid, f"Expected valid team slot, got: {res.errors}")

    # --------------------------------------------------------------------------
    # 9. Invalid Team-Color Display Slot
    # --------------------------------------------------------------------------
    def test_09_invalid_team_color_display_slot(self):
        pack = self._create_synthetic_pack(
            "p09_bad_team_slot",
            functions={
                "test:load": (
                    "scoreboard objectives add my_obj dummy\n"
                    "scoreboard objectives setdisplay sidebar.team.neon_pink my_obj\n"
                )
            }
        )
        res = self.validator.validate(pack)
        self.assertFalse(res.is_valid)
        error_codes = [e.code for e in res.errors]
        self.assertIn("INVALID_DISPLAY_SLOT", error_codes)

    # --------------------------------------------------------------------------
    # 10. scoreboard players set
    # --------------------------------------------------------------------------
    def test_10_scoreboard_players_set(self):
        pack = self._create_synthetic_pack(
            "p10_players_set",
            functions={
                "test:load": (
                    "scoreboard objectives add score dummy\n"
                    "scoreboard players set #global score 10\n"
                )
            }
        )
        res = self.validator.validate(pack)
        self.assertTrue(res.is_valid, f"Expected valid players set, got: {res.errors}")

    # --------------------------------------------------------------------------
    # 11. scoreboard players add
    # --------------------------------------------------------------------------
    def test_11_scoreboard_players_add(self):
        pack = self._create_synthetic_pack(
            "p11_players_add",
            functions={
                "test:load": (
                    "scoreboard objectives add score dummy\n"
                    "scoreboard players add #global score 5\n"
                )
            }
        )
        res = self.validator.validate(pack)
        self.assertTrue(res.is_valid, f"Expected valid players add, got: {res.errors}")

    # --------------------------------------------------------------------------
    # 12. scoreboard players remove
    # --------------------------------------------------------------------------
    def test_12_scoreboard_players_remove(self):
        pack = self._create_synthetic_pack(
            "p12_players_remove",
            functions={
                "test:load": (
                    "scoreboard objectives add score dummy\n"
                    "scoreboard players remove #global score 3\n"
                )
            }
        )
        res = self.validator.validate(pack)
        self.assertTrue(res.is_valid, f"Expected valid players remove, got: {res.errors}")

    # --------------------------------------------------------------------------
    # 13. scoreboard players reset
    # --------------------------------------------------------------------------
    def test_13_scoreboard_players_reset(self):
        pack = self._create_synthetic_pack(
            "p13_players_reset",
            functions={
                "test:load": (
                    "scoreboard objectives add score dummy\n"
                    "scoreboard players reset #global score\n"
                    "scoreboard players reset @a\n"
                )
            }
        )
        res = self.validator.validate(pack)
        self.assertTrue(res.is_valid, f"Expected valid players reset, got: {res.errors}")

    # --------------------------------------------------------------------------
    # 14. scoreboard objectives remove
    # --------------------------------------------------------------------------
    def test_14_scoreboard_objectives_remove(self):
        pack = self._create_synthetic_pack(
            "p14_obj_remove",
            functions={
                "test:load": (
                    "scoreboard objectives add temp_obj dummy\n"
                    "scoreboard objectives remove temp_obj\n"
                )
            }
        )
        res = self.validator.validate(pack)
        self.assertTrue(res.is_valid, f"Expected valid objectives remove, got: {res.errors}")

    # --------------------------------------------------------------------------
    # 15. All Nine Scoreboard Operations (=, +=, -=, *=, /=, %=, <, >, ><)
    # --------------------------------------------------------------------------
    def test_15_all_nine_scoreboard_operations(self):
        ops = ["=", "+=", "-=", "*=", "/=", "%=", "<", ">", "><"]
        lines = [
            "scoreboard objectives add target_obj dummy\n",
            "scoreboard objectives add source_obj dummy\n",
        ]
        for op in ops:
            lines.append(f"scoreboard players operation #global target_obj {op} #global source_obj\n")

        pack = self._create_synthetic_pack(
            "p15_all_9_ops",
            functions={"test:load": "".join(lines)}
        )
        res = self.validator.validate(pack)
        self.assertTrue(res.is_valid, f"Expected all 9 operations valid, got: {res.errors}")

    # --------------------------------------------------------------------------
    # 16. Invalid Scoreboard Operation
    # --------------------------------------------------------------------------
    def test_16_invalid_scoreboard_operation(self):
        pack = self._create_synthetic_pack(
            "p16_invalid_op",
            functions={
                "test:load": (
                    "scoreboard objectives add target_obj dummy\n"
                    "scoreboard objectives add source_obj dummy\n"
                    "scoreboard players operation #global target_obj **= #global source_obj\n"
                )
            }
        )
        res = self.validator.validate(pack)
        self.assertFalse(res.is_valid)
        error_codes = [e.code for e in res.errors]
        self.assertIn("INVALID_SCORE_OPERATION", error_codes)

    # --------------------------------------------------------------------------
    # 17. Valid Negative Set Value
    # --------------------------------------------------------------------------
    def test_17_valid_negative_set_value(self):
        pack = self._create_synthetic_pack(
            "p17_neg_set",
            functions={
                "test:load": (
                    "scoreboard objectives add score dummy\n"
                    "scoreboard players set #global score -500\n"
                )
            }
        )
        res = self.validator.validate(pack)
        self.assertTrue(res.is_valid, f"Expected negative set value to be valid, got: {res.errors}")

    # --------------------------------------------------------------------------
    # 18. Invalid Negative Add Value
    # --------------------------------------------------------------------------
    def test_18_invalid_negative_add_value(self):
        pack = self._create_synthetic_pack(
            "p18_neg_add",
            functions={
                "test:load": (
                    "scoreboard objectives add score dummy\n"
                    "scoreboard players add #global score -10\n"
                )
            }
        )
        res = self.validator.validate(pack)
        self.assertFalse(res.is_valid)
        error_codes = [e.code for e in res.errors]
        self.assertIn("INVALID_SCORE_VALUE", error_codes)

    # --------------------------------------------------------------------------
    # 19. Invalid Negative Remove Value
    # --------------------------------------------------------------------------
    def test_19_invalid_negative_remove_value(self):
        pack = self._create_synthetic_pack(
            "p19_neg_remove",
            functions={
                "test:load": (
                    "scoreboard objectives add score dummy\n"
                    "scoreboard players remove #global score -5\n"
                )
            }
        )
        res = self.validator.validate(pack)
        self.assertFalse(res.is_valid)
        error_codes = [e.code for e in res.errors]
        self.assertIn("INVALID_SCORE_VALUE", error_codes)

    # --------------------------------------------------------------------------
    # 20. Valid 32-bit Minimum (-2147483648)
    # --------------------------------------------------------------------------
    def test_20_valid_32bit_minimum(self):
        pack = self._create_synthetic_pack(
            "p20_32bit_min",
            functions={
                "test:load": (
                    "scoreboard objectives add score dummy\n"
                    f"scoreboard players set #global score {MIN_SCORE_32}\n"
                )
            }
        )
        res = self.validator.validate(pack)
        self.assertTrue(res.is_valid, f"Expected 32-bit min valid, got: {res.errors}")

    # --------------------------------------------------------------------------
    # 21. Valid 32-bit Maximum (2147483647)
    # --------------------------------------------------------------------------
    def test_21_valid_32bit_maximum(self):
        pack = self._create_synthetic_pack(
            "p21_32bit_max",
            functions={
                "test:load": (
                    "scoreboard objectives add score dummy\n"
                    f"scoreboard players set #global score {MAX_SCORE_32}\n"
                )
            }
        )
        res = self.validator.validate(pack)
        self.assertTrue(res.is_valid, f"Expected 32-bit max valid, got: {res.errors}")

    # --------------------------------------------------------------------------
    # 22. Overflow Above 32-bit Maximum (2147483648)
    # --------------------------------------------------------------------------
    def test_22_overflow_above_32bit_maximum(self):
        pack = self._create_synthetic_pack(
            "p22_overflow",
            functions={
                "test:load": (
                    "scoreboard objectives add score dummy\n"
                    f"scoreboard players set #global score {MAX_SCORE_32 + 1}\n"
                )
            }
        )
        res = self.validator.validate(pack)
        self.assertFalse(res.is_valid)
        error_codes = [e.code for e in res.errors]
        self.assertIn("INVALID_SCORE_VALUE", error_codes)

    # --------------------------------------------------------------------------
    # 23. Underflow Below 32-bit Minimum (-2147483649)
    # --------------------------------------------------------------------------
    def test_23_underflow_below_32bit_minimum(self):
        pack = self._create_synthetic_pack(
            "p23_underflow",
            functions={
                "test:load": (
                    "scoreboard objectives add score dummy\n"
                    f"scoreboard players set #global score {MIN_SCORE_32 - 1}\n"
                )
            }
        )
        res = self.validator.validate(pack)
        self.assertFalse(res.is_valid)
        error_codes = [e.code for e in res.errors]
        self.assertIn("INVALID_SCORE_VALUE", error_codes)

    # --------------------------------------------------------------------------
    # 24. Valid Score Range Comparison
    # --------------------------------------------------------------------------
    def test_24_valid_score_range_comparison(self):
        pack = self._create_synthetic_pack(
            "p24_range_comp",
            functions={
                "test:load": (
                    "scoreboard objectives add timer dummy\n"
                    "execute if score @s timer matches 10 run say 10\n"
                    "execute if score @s timer matches 5..20 run say 5 to 20\n"
                    "execute if score @s timer matches 100.. run say 100 or more\n"
                    "execute if score @s timer matches ..50 run say 50 or less\n"
                    "execute unless score @s timer matches 0 run say not zero\n"
                )
            }
        )
        res = self.validator.validate(pack)
        self.assertTrue(res.is_valid, f"Expected valid range comparisons, got: {res.errors}")

    # --------------------------------------------------------------------------
    # 25. Valid Score-to-Score Comparison (<, <=, =, >=, >)
    # --------------------------------------------------------------------------
    def test_25_valid_score_to_score_comparison(self):
        pack = self._create_synthetic_pack(
            "p25_score_to_score",
            functions={
                "test:load": (
                    "scoreboard objectives add player_score dummy\n"
                    "scoreboard objectives add req_score dummy\n"
                    "execute if score @s player_score < #global req_score run say less\n"
                    "execute if score @s player_score <= #global req_score run say less or eq\n"
                    "execute if score @s player_score = #global req_score run say equal\n"
                    "execute if score @s player_score >= #global req_score run say greater or eq\n"
                    "execute if score @s player_score > #global req_score run say greater\n"
                )
            }
        )
        res = self.validator.validate(pack)
        self.assertTrue(res.is_valid, f"Expected valid score-to-score comparisons, got: {res.errors}")

    # --------------------------------------------------------------------------
    # 26. Invalid Score Comparison
    # --------------------------------------------------------------------------
    def test_26_invalid_score_comparison(self):
        # 1. Invalid comparison operator '!='
        pack1 = self._create_synthetic_pack(
            "p26_invalid_op",
            functions={
                "test:load": (
                    "scoreboard objectives add s1 dummy\n"
                    "scoreboard objectives add s2 dummy\n"
                    "execute if score @s s1 != #global s2 run say invalid\n"
                )
            }
        )
        res1 = self.validator.validate(pack1)
        self.assertFalse(res1.is_valid)
        self.assertIn("INVALID_SCORE_COMPARISON", [e.code for e in res1.errors])

        # 2. Inverted range bounds (lower > upper)
        pack2 = self._create_synthetic_pack(
            "p26_inverted_range",
            functions={
                "test:load": (
                    "scoreboard objectives add s1 dummy\n"
                    "execute if score @s s1 matches 20..10 run say inverted\n"
                )
            }
        )
        res2 = self.validator.validate(pack2)
        self.assertFalse(res2.is_valid)
        self.assertIn("INVALID_SCORE_COMPARISON", [e.code for e in res2.errors])

    # --------------------------------------------------------------------------
    # 27. Undeclared Objective Reference
    # --------------------------------------------------------------------------
    def test_27_undeclared_objective_reference(self):
        pack = self._create_synthetic_pack(
            "p27_undeclared_obj",
            functions={
                "test:load": "scoreboard players set #global never_declared 10\n"
            }
        )
        res = self.validator.validate(pack)
        self.assertFalse(res.is_valid)
        error_codes = [e.code for e in res.errors]
        self.assertIn("UNDECLARED_SCOREBOARD_OBJECTIVE", error_codes)

    # --------------------------------------------------------------------------
    # 28. Declared Objective Used Across load/tick
    # --------------------------------------------------------------------------
    def test_28_declared_objective_used_across_load_tick(self):
        pack = self._create_synthetic_pack(
            "p28_across_load_tick",
            functions={
                "test:load": "scoreboard objectives add points dummy\n",
                "test:tick": "scoreboard players add @a points 1\n"
            }
        )
        res = self.validator.validate(pack)
        self.assertTrue(res.is_valid, f"Expected cross-file objective usage valid, got: {res.errors}")

    # --------------------------------------------------------------------------
    # 29. Missing Function Tag Reference
    # --------------------------------------------------------------------------
    def test_29_missing_function_tag_reference(self):
        pack = self._create_synthetic_pack(
            "p29_missing_tag_ref",
            functions={
                "test:load": "scoreboard objectives add s dummy\n"
            },
            tags={
                "minecraft:load": ["test:nonexistent_func"]
            }
        )
        res = self.validator.validate(pack)
        self.assertFalse(res.is_valid)
        error_codes = [e.code for e in res.errors]
        self.assertIn("MISSING_TAG_REFERENCE", error_codes)

    # --------------------------------------------------------------------------
    # 30. Valid Function Tag
    # --------------------------------------------------------------------------
    def test_30_valid_function_tag(self):
        pack = self._create_synthetic_pack(
            "p30_valid_tag",
            functions={
                "test:load": "scoreboard objectives add s dummy\n"
            },
            tags={
                "minecraft:load": ["test:load"]
            }
        )
        res = self.validator.validate(pack)
        self.assertTrue(res.is_valid, f"Expected valid tag, got: {res.errors}")

    # --------------------------------------------------------------------------
    # 31. Valid replace: true
    # --------------------------------------------------------------------------
    def test_31_valid_replace_true(self):
        pack = self._create_synthetic_pack(
            "p31_replace_true",
            functions={
                "test:load": "scoreboard objectives add s dummy\n"
            },
            tags={
                "minecraft:load": {
                    "replace": True,
                    "values": ["test:load"]
                }
            }
        )
        res = self.validator.validate(pack)
        self.assertTrue(res.is_valid, f"Expected replace: true to be valid, got: {res.errors}")

    # --------------------------------------------------------------------------
    # 32. Valid replace: false
    # --------------------------------------------------------------------------
    def test_32_valid_replace_false(self):
        pack = self._create_synthetic_pack(
            "p32_replace_false",
            functions={
                "test:load": "scoreboard objectives add s dummy\n"
            },
            tags={
                "minecraft:load": {
                    "replace": False,
                    "values": ["test:load"]
                }
            }
        )
        res = self.validator.validate(pack)
        self.assertTrue(res.is_valid, f"Expected replace: false to be valid without errors, got: {res.errors}")

    # --------------------------------------------------------------------------
    # 33. Omitted replace (Default False)
    # --------------------------------------------------------------------------
    def test_33_omitted_replace(self):
        pack = self._create_synthetic_pack(
            "p33_omitted_replace",
            functions={
                "test:load": "scoreboard objectives add s dummy\n"
            },
            tags={
                "minecraft:load": {
                    "values": ["test:load"]
                }
            }
        )
        res = self.validator.validate(pack)
        self.assertTrue(res.is_valid, f"Expected omitted replace to be valid, got: {res.errors}")

    # --------------------------------------------------------------------------
    # 34. Invalid Non-Boolean replace
    # --------------------------------------------------------------------------
    def test_34_invalid_non_boolean_replace(self):
        pack = self._create_synthetic_pack(
            "p34_bad_replace",
            functions={
                "test:load": "scoreboard objectives add s dummy\n"
            },
            tags={
                "minecraft:load": {
                    "replace": "true",  # string instead of boolean
                    "values": ["test:load"]
                }
            }
        )
        res = self.validator.validate(pack)
        self.assertFalse(res.is_valid)
        error_codes = [e.code for e in res.errors]
        self.assertIn("MALFORMED_TAG", error_codes)

    # --------------------------------------------------------------------------
    # 35. State-Machine Scoreboard Validation
    # --------------------------------------------------------------------------
    def test_35_state_machine_scoreboard_validation(self):
        pack = self._create_synthetic_pack(
            "p35_state_machine",
            functions={
                "test:load": (
                    "scoreboard objectives add sm_state dummy\n"
                    "scoreboard objectives add sm_timer dummy\n"
                    "scoreboard players set #global sm_state 0\n"
                ),
                "test:tick": (
                    "execute as @a at @s if score @s sm_state matches 0 run scoreboard players add @s sm_timer 1\n"
                    "execute as @a at @s if score @s sm_timer matches 100.. run scoreboard players set @s sm_state 1\n"
                )
            },
            tags={
                "minecraft:load": ["test:load"],
                "minecraft:tick": ["test:tick"]
            }
        )
        res = self.validator.validate(pack)
        self.assertTrue(res.is_valid, f"Expected state-machine datapack to be valid, got: {res.errors}")
        warning_codes = [w.code for w in res.warnings]
        self.assertNotIn("EMPTY_SELECTOR_ON_LOAD", warning_codes)

    # --------------------------------------------------------------------------
    # 36. Lifecycle load/tick Validation
    # --------------------------------------------------------------------------
    def test_36_lifecycle_load_tick_validation(self):
        # 1. Load-only datapack
        pack_load = self._create_synthetic_pack(
            "p36_load_only",
            functions={"test:load": "scoreboard objectives add s dummy\n"},
            tags={"minecraft:load": ["test:load"]}
        )
        res_load = self.validator.validate(pack_load)
        self.assertTrue(res_load.is_valid, f"Load-only pack failed: {res_load.errors}")

        # 2. Tick-only datapack (no scoreboard objectives needed)
        pack_tick = self._create_synthetic_pack(
            "p36_tick_only",
            functions={"test:tick": "particle flame ~ ~ ~ 0.1 0.1 0.1 0.05 5\n"},
            tags={"minecraft:tick": ["test:tick"]}
        )
        res_tick = self.validator.validate(pack_tick)
        self.assertTrue(res_tick.is_valid, f"Tick-only pack failed: {res_tick.errors}")

        # 3. Both load and tick datapack
        pack_both = self._create_synthetic_pack(
            "p36_both",
            functions={
                "test:load": "scoreboard objectives add s dummy\n",
                "test:tick": "scoreboard players add #global s 1\n"
            },
            tags={
                "minecraft:load": ["test:load"],
                "minecraft:tick": ["test:tick"]
            }
        )
        res_both = self.validator.validate(pack_both)
        self.assertTrue(res_both.is_valid, f"Both load and tick failed: {res_both.errors}")

    # --------------------------------------------------------------------------
    # 37. Multiple Mechanisms Contributing Scoreboard Objectives
    # --------------------------------------------------------------------------
    def test_37_multiple_mechanisms_contributing_scoreboard_objectives(self):
        pack = self._create_synthetic_pack(
            "p37_multi_mechs_objs",
            functions={
                "test:load": (
                    "scoreboard objectives add deaths deathCount\n"
                    "scoreboard objectives add timer dummy\n"
                    "scoreboard objectives add points dummy\n"
                    "scoreboard objectives setdisplay sidebar points\n"
                ),
                "test:tick": (
                    "scoreboard players add #global timer 1\n"
                    "execute if score @s deaths matches 1.. run scoreboard players add @s points 10\n"
                )
            },
            tags={
                "minecraft:load": ["test:load"],
                "minecraft:tick": ["test:tick"]
            }
        )
        res = self.validator.validate(pack)
        self.assertTrue(res.is_valid, f"Expected multiple mechanisms valid, got: {res.errors}")

    # --------------------------------------------------------------------------
    # 38. Multiple Mechanisms Contributing load/tick
    # --------------------------------------------------------------------------
    def test_38_multiple_mechanisms_contributing_load_tick(self):
        pack = self._create_synthetic_pack(
            "p38_multi_mechs_load_tick",
            functions={
                "test:mech1_load": "scoreboard objectives add m1_obj dummy\n",
                "test:mech2_load": "scoreboard objectives add m2_obj dummy\n",
                "test:load": (
                    "function test:mech1_load\n"
                    "function test:mech2_load\n"
                ),
                "test:tick": (
                    "scoreboard players add #global m1_obj 1\n"
                    "scoreboard players add #global m2_obj 2\n"
                )
            },
            tags={
                "minecraft:load": ["test:load"],
                "minecraft:tick": ["test:tick"]
            }
        )
        res = self.validator.validate(pack)
        self.assertTrue(res.is_valid, f"Expected multiple mechanisms load/tick valid, got: {res.errors}")

    # --------------------------------------------------------------------------
    # 39. Existing Step 15 Regressions
    # --------------------------------------------------------------------------
    def test_39_existing_step15_regressions(self):
        # 1. Invalid item ID in loot table
        pack_bad_item = self._create_synthetic_pack(
            "p39_bad_item",
            functions={"test:load": "say hello\n"}
        )
        lt_file = pack_bad_item / "data" / "minecraft" / "loot_table" / "entities" / "zombie.json"
        lt_file.parent.mkdir(parents=True, exist_ok=True)
        lt_content = {
            "type": "minecraft:entity",
            "pools": [
                {
                    "rolls": 1,
                    "entries": [
                        {
                            "type": "minecraft:item",
                            "name": "minecraft:nonexistent_fake_item_999"
                        }
                    ]
                }
            ]
        }
        with open(lt_file, "w", encoding="utf-8") as f:
            json.dump(lt_content, f)

        res_bad_item = self.validator.validate(pack_bad_item)
        self.assertFalse(res_bad_item.is_valid)
        self.assertIn("INVALID_ITEM_ID", [e.code for e in res_bad_item.errors])

        # 2. Leading slash in function
        pack_slash = self._create_synthetic_pack(
            "p39_leading_slash",
            functions={"test:load": "/say hello\n"}
        )
        res_slash = self.validator.validate(pack_slash)
        self.assertFalse(res_slash.is_valid)
        self.assertIn("LEADING_SLASH_IN_FUNCTION", [e.code for e in res_slash.errors])

    # --------------------------------------------------------------------------
    # 40. Deterministic Validation of the Same Generated Datapack
    # --------------------------------------------------------------------------
    def test_40_deterministic_validation_same_datapack(self):
        pack = self._create_synthetic_pack(
            "p40_deterministic",
            functions={
                "test:load": (
                    "scoreboard objectives add score dummy\n"
                    "scoreboard players set #global score 10\n"
                ),
                "test:tick": (
                    "execute if score #global score matches 10.. run say high\n"
                )
            },
            tags={
                "minecraft:load": ["test:load"],
                "minecraft:tick": ["test:tick"]
            }
        )

        res1 = self.validator.validate(pack)
        res2 = self.validator.validate(pack)

        self.assertEqual(res1.is_valid, res2.is_valid)
        self.assertEqual(len(res1.errors), len(res2.errors))
        self.assertEqual(len(res1.warnings), len(res2.warnings))
        self.assertEqual(len(res1.checks), len(res2.checks))
        for c1, c2 in zip(res1.checks, res2.checks):
            self.assertEqual(c1.name, c2.name)
            self.assertEqual(c1.passed, c2.passed)

    # --------------------------------------------------------------------------
    # Extra: Conflicting Objective Declarations & Display Slots
    # --------------------------------------------------------------------------
    def test_conflicting_objective_definitions(self):
        pack = self._create_synthetic_pack(
            "p_conflict_obj",
            functions={
                "test:load": (
                    "scoreboard objectives add points dummy\n"
                    "scoreboard objectives add points deathCount\n"
                )
            }
        )
        res = self.validator.validate(pack)
        self.assertFalse(res.is_valid)
        self.assertIn("CONFLICTING_OBJECTIVE_DEFINITION", [e.code for e in res.errors])

    def test_conflicting_display_slots(self):
        pack = self._create_synthetic_pack(
            "p_conflict_slot",
            functions={
                "test:load": (
                    "scoreboard objectives add obj1 dummy\n"
                    "scoreboard objectives add obj2 dummy\n"
                    "scoreboard objectives setdisplay sidebar obj1\n"
                    "scoreboard objectives setdisplay sidebar obj2\n"
                )
            }
        )
        res = self.validator.validate(pack)
        self.assertFalse(res.is_valid)
        self.assertIn("CONFLICTING_OBJECTIVE_DEFINITION", [e.code for e in res.errors])


if __name__ == "__main__":
    unittest.main()
