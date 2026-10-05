"""
test_step26_2_generator.py - Step 26.2 Deterministic Interaction Mechanism Generator Tests
Authoritative target: Minecraft Java 1.21.11 and 1.21.1

Tests all 16 interaction generator capabilities:
1. Basic interaction generation (lifecycle functions, triggers, tags)
2. Deterministic output (byte-identical repeated generation)
3. Multiple options (arbitrary option counts and actions)
4. Option ordering (deterministic sorting by ID)
5. Deterministic, collision-resistant 16-character objective naming (1-16 chars limit)
6. Resource path generation (singular function/ layout, custom namespace)
7. Interaction plus another mechanism (coexistence with recipe / loot / func)
8. Multiple interactions without collisions (isolated objectives and paths)
9. Load and tick game-loop integration
10. No dangling generated function references
11. Correct ZIP root assembly (pack.mcmeta and data/ at root)
12. Both supported Minecraft versions (1.21.11 and 1.21.1)
13. Timeout handling and timer loop generation
14. Item-trigger activation check generation
15. Cancellation disabling (allow_cancel=False)
16. Option condition predicate synthesis
"""

import hashlib
import json
import shutil
import unittest
import zipfile
from pathlib import Path

from ai.version_registry import VersionContext
from generator.datapack_generator import DatapackGenerator, generate_datapack
from generator.mechanisms.interaction_mech import (
    InteractionMechanismGenerator,
    derive_objective_name,
)
from generator.models import (
    ActionSpecification,
    DatapackResource,
    InteractionOption,
    InteractionSpecification,
    MechanismSpecification,
    RecipeDefinition,
)


class TestStep262Generator(unittest.TestCase):
    def setUp(self):
        self.output_dir = Path("generated") / "test_s26_2_generator"
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.mech_gen = InteractionMechanismGenerator(version="1.21.11")

    def tearDown(self):
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)

    def test_01_basic_interaction_generation(self):
        spec = InteractionSpecification(
            name="teleport_menu",
            interaction_type="chat_menu",
            prompt="Choose a destination",
            options=[
                InteractionOption(
                    id=1,
                    label="Spawn",
                    actions=[
                        ActionSpecification(action_type="send_message", target="@s", message="Teleporting to Spawn")
                    ]
                ),
                InteractionOption(
                    id=2,
                    label="Home",
                    actions=[
                        ActionSpecification(action_type="send_message", target="@s", message="Teleporting Home")
                    ]
                )
            ]
        )
        resources = self.mech_gen.generate(spec)
        rel_paths = {r.relative_path for r in resources}

        # Expected functions
        expected = {
            "data/minecraft_ai/function/interaction/teleport_menu/init.mcfunction",
            "data/minecraft_ai/function/interaction/teleport_menu/open.mcfunction",
            "data/minecraft_ai/function/interaction/teleport_menu/tick.mcfunction",
            "data/minecraft_ai/function/interaction/teleport_menu/select_1.mcfunction",
            "data/minecraft_ai/function/interaction/teleport_menu/select_2.mcfunction",
            "data/minecraft_ai/function/interaction/teleport_menu/cancel.mcfunction",
            "data/minecraft/tags/function/load.json",
            "data/minecraft/tags/function/tick.json",
        }
        self.assertTrue(expected.issubset(rel_paths), f"Missing paths: {expected - rel_paths}")

    def test_02_deterministic_resource_output(self):
        spec = InteractionSpecification(
            name="confirm_box",
            options=[
                InteractionOption(id=1, label="Yes"),
                InteractionOption(id=2, label="No")
            ]
        )
        res1 = self.mech_gen.generate(spec)
        res2 = self.mech_gen.generate(spec)

        self.assertEqual(len(res1), len(res2))
        for r1, r2 in zip(res1, res2):
            self.assertEqual(r1.relative_path, r2.relative_path)
            self.assertEqual(r1.content, r2.content)

    def test_03_multiple_options_arbitrary_counts(self):
        options = [
            InteractionOption(id=i, label=f"Option {i}", actions=[
                ActionSpecification(action_type="send_message", target="@s", message=f"Selected {i}")
            ])
            for i in range(1, 6)
        ]
        spec = InteractionSpecification(
            name="five_choices",
            options=options
        )
        resources = self.mech_gen.generate(spec)
        paths = {r.relative_path for r in resources}

        for i in range(1, 6):
            self.assertIn(f"data/minecraft_ai/function/interaction/five_choices/select_{i}.mcfunction", paths)

        # Check tick loop checks all 5 options
        tick_res = next(r for r in resources if r.relative_path.endswith("tick.mcfunction"))
        for i in range(1, 6):
            self.assertIn(f"scores={{trg_five_choices={i}}}", tick_res.content)

    def test_04_option_ordering(self):
        # Options provided out of numerical order
        spec = InteractionSpecification(
            name="out_of_order",
            options=[
                InteractionOption(id=3, label="Three"),
                InteractionOption(id=1, label="One"),
                InteractionOption(id=2, label="Two"),
            ]
        )
        resources = self.mech_gen.generate(spec)
        open_res = next(r for r in resources if r.relative_path.endswith("open.mcfunction"))

        # In tellraw, option 1 should appear before option 2, which appears before option 3
        idx_1 = open_res.content.find("One")
        idx_2 = open_res.content.find("Two")
        idx_3 = open_res.content.find("Three")
        self.assertTrue(idx_1 < idx_2 < idx_3, "Options in tellraw presentation must be sorted by ID")

    def test_05_deterministic_objective_naming(self):
        # Short name
        short_obj = derive_objective_name("menu", prefix="trg_")
        self.assertEqual(short_obj, "trg_menu")
        self.assertTrue(len(short_obj) <= 16)

        # Very long name
        long_name = "extremely_long_interaction_menu_dialogue"
        long_obj = derive_objective_name(long_name, prefix="trg_")
        self.assertTrue(len(long_obj) <= 16, f"Objective '{long_obj}' exceeds 16 chars: {len(long_obj)}")
        self.assertTrue(long_obj.startswith("trg_"))

        # Collision avoidance for distinct long names
        other_long = "extremely_long_interaction_menu_settings"
        other_obj = derive_objective_name(other_long, prefix="trg_")
        self.assertNotEqual(long_obj, other_obj, "Distinct long interaction names must yield distinct objective names")

    def test_06_resource_path_generation(self):
        mech = MechanismSpecification(
            type="interaction",
            namespace="custom_pack",
            interaction=InteractionSpecification(
                name="dialogue_one",
                options=[InteractionOption(id=1, label="Continue")]
            )
        )
        resources = self.mech_gen.generate(mech)
        paths = [r.relative_path for r in resources]

        self.assertTrue(any(p.startswith("data/custom_pack/function/interaction/dialogue_one/") for p in paths))
        self.assertIn("data/minecraft/tags/function/load.json", paths)
        self.assertIn("data/minecraft/tags/function/tick.json", paths)

    def test_07_interaction_plus_another_mechanism(self):
        gen = DatapackGenerator(output_dir=self.output_dir, version="1.21.11")
        interaction_spec = InteractionSpecification(
            name="kit_menu",
            options=[
                InteractionOption(
                    id=1,
                    label="Starter Kit",
                    actions=[ActionSpecification(action_type="give_item", target="@s", item="minecraft:bread", count=5)]
                )
            ]
        )
        recipe_def = RecipeDefinition(
            recipe_path="custom_bread",
            recipe_type="crafting_shapeless",
            result_item="minecraft:bread",
            result_count=2,
            ingredients=["minecraft:wheat"],
            namespace="minecraft_ai"
        )


        res = gen.generate(
            datapack_name="hybrid_pack",
            recipes=[recipe_def],
            interactions=[interaction_spec],
            create_zip=True
        )

        self.assertEqual(res.status, "success")
        self.assertTrue(res.zip_path.exists())

        # Inspect generated files
        dp_dir = res.datapack_path
        self.assertTrue((dp_dir / "data" / "minecraft_ai" / "recipe" / "custom_bread.json").exists())
        self.assertTrue((dp_dir / "data" / "minecraft_ai" / "function" / "interaction" / "kit_menu" / "init.mcfunction").exists())
        self.assertTrue((dp_dir / "data" / "minecraft_ai" / "function" / "interaction" / "kit_menu" / "open.mcfunction").exists())

    def test_08_multiple_interactions_without_collisions(self):
        gen = DatapackGenerator(output_dir=self.output_dir, version="1.21.11")
        int_a = InteractionSpecification(
            name="menu_a",
            options=[InteractionOption(id=1, label="A1")]
        )
        int_b = InteractionSpecification(
            name="menu_b",
            options=[InteractionOption(id=1, label="B1")]
        )

        res = gen.generate(
            datapack_name="dual_menu_pack",
            interactions=[int_a, int_b],
            create_zip=True
        )

        dp_dir = res.datapack_path
        self.assertTrue((dp_dir / "data" / "minecraft_ai" / "function" / "interaction" / "menu_a" / "init.mcfunction").exists())
        self.assertTrue((dp_dir / "data" / "minecraft_ai" / "function" / "interaction" / "menu_b" / "init.mcfunction").exists())

        # Inspect load tag: must reference BOTH init functions
        load_tag = json.loads((dp_dir / "data" / "minecraft" / "tags" / "function" / "load.json").read_text(encoding="utf-8"))
        self.assertIn("minecraft_ai:interaction/menu_a/init", load_tag["values"])
        self.assertIn("minecraft_ai:interaction/menu_b/init", load_tag["values"])

    def test_09_load_tick_integration(self):
        spec = InteractionSpecification(
            name="test_loop",
            options=[InteractionOption(id=1, label="Click")]
        )
        resources = self.mech_gen.generate(spec)

        load_res = next(r for r in resources if r.relative_path == "data/minecraft/tags/function/load.json")
        tick_res = next(r for r in resources if r.relative_path == "data/minecraft/tags/function/tick.json")

        load_data = json.loads(load_res.content)
        tick_data = json.loads(tick_res.content)

        self.assertIn("minecraft_ai:interaction/test_loop/init", load_data["values"])
        self.assertIn("minecraft_ai:interaction/test_loop/tick", tick_data["values"])

    def test_10_no_dangling_generated_function_references(self):
        gen = DatapackGenerator(output_dir=self.output_dir, version="1.21.11")
        spec = InteractionSpecification(
            name="nodangle",
            options=[InteractionOption(id=1, label="OK")]
        )
        res = gen.generate(
            datapack_name="nodangle_pack",
            interactions=[spec],
            create_zip=False
        )

        dp_dir = res.datapack_path
        # Check all function tags on disk
        for tag_file in dp_dir.glob("data/*/tags/function/**/*.json"):
            tag_json = json.loads(tag_file.read_text(encoding="utf-8"))
            for val in tag_json.get("values", []):
                val_str = val if isinstance(val, str) else val.get("id", "")
                if val_str.startswith("#"):
                    continue
                parts = val_str.split(":", 1)
                ns, path = parts[0], parts[1]
                expected_func_file = dp_dir / "data" / ns / "function" / f"{path}.mcfunction"
                self.assertTrue(
                    expected_func_file.exists(),
                    f"Dangling function reference '{val_str}' in tag '{tag_file.name}'"
                )

    def test_11_zip_root_assembly(self):
        gen = DatapackGenerator(output_dir=self.output_dir, version="1.21.11")
        spec = InteractionSpecification(
            name="ziptest",
            options=[InteractionOption(id=1, label="Go")]
        )
        res1 = gen.generate(datapack_name="zip_root_pack", interactions=[spec], create_zip=True)
        hash1 = hashlib.sha256(res1.zip_path.read_bytes()).hexdigest()

        # Check ZIP root layout
        with zipfile.ZipFile(res1.zip_path, "r") as zf:
            names = zf.namelist()
            self.assertIn("pack.mcmeta", names)
            self.assertTrue(any(n.startswith("data/") for n in names))
            # Must NOT have nested root like 'zip_root_pack/pack.mcmeta'
            self.assertFalse(any(n.startswith("zip_root_pack/") for n in names))

        # Check determinism: run 2 must produce byte-identical hash
        res2 = gen.generate(datapack_name="zip_root_pack", interactions=[spec], create_zip=True)
        hash2 = hashlib.sha256(res2.zip_path.read_bytes()).hexdigest()
        self.assertEqual(hash1, hash2, "Repeated generation of identical interaction must produce byte-identical ZIPs")

    def test_12_both_supported_minecraft_versions(self):
        spec = InteractionSpecification(
            name="vtest",
            options=[InteractionOption(id=1, label="Play")]
        )
        # 1.21.11
        gen_11 = DatapackGenerator(output_dir=self.output_dir, version="1.21.11")
        res_11 = gen_11.generate(datapack_name="pack_11", interactions=[spec], create_zip=False)
        mcmeta_11 = json.loads((res_11.datapack_path / "pack.mcmeta").read_text(encoding="utf-8"))
        self.assertEqual(mcmeta_11["pack"]["pack_format"], 94)

        # 1.21.1
        gen_1 = DatapackGenerator(output_dir=self.output_dir, version="1.21.1")
        res_1 = gen_1.generate(datapack_name="pack_1", interactions=[spec], create_zip=False)
        mcmeta_1 = json.loads((res_1.datapack_path / "pack.mcmeta").read_text(encoding="utf-8"))
        self.assertEqual(mcmeta_1["pack"]["pack_format"], 48)

    def test_13_timeout_generation(self):
        spec = InteractionSpecification(
            name="timed_quiz",
            timeout_seconds=5,
            options=[InteractionOption(id=1, label="Answer A")]
        )
        resources = self.mech_gen.generate(spec)
        paths = {r.relative_path for r in resources}

        self.assertIn("data/minecraft_ai/function/interaction/timed_quiz/timeout.mcfunction", paths)

        init_res = next(r for r in resources if r.relative_path.endswith("init.mcfunction"))
        self.assertIn("scoreboard objectives add tmr_timed_quiz dummy", init_res.content)

        tick_res = next(r for r in resources if r.relative_path.endswith("tick.mcfunction"))
        # 5 seconds * 20 = 100 ticks
        self.assertIn("scoreboard players add @s tmr_timed_quiz 1", tick_res.content)
        self.assertIn("tmr_timed_quiz=100..", tick_res.content)

    def test_14_item_trigger_generation(self):
        spec = InteractionSpecification(
            name="compass_menu",
            interaction_type="item_trigger",
            trigger_item="minecraft:compass",
            options=[InteractionOption(id=1, label="Navigate")]
        )
        resources = self.mech_gen.generate(spec)
        tick_res = next(r for r in resources if r.relative_path.endswith("tick.mcfunction"))

        self.assertIn('SelectedItem:{id:"minecraft:compass"}', tick_res.content)
        self.assertIn("run function minecraft_ai:interaction/compass_menu/open", tick_res.content)

    def test_15_cancellation_disabled(self):
        spec = InteractionSpecification(
            name="mandatory_choice",
            allow_cancel=False,
            options=[InteractionOption(id=1, label="Proceed")]
        )
        resources = self.mech_gen.generate(spec)
        paths = {r.relative_path for r in resources}

        self.assertNotIn("data/minecraft_ai/function/interaction/mandatory_choice/cancel.mcfunction", paths)

        open_res = next(r for r in resources if r.relative_path.endswith("open.mcfunction"))
        self.assertNotIn("Cancel", open_res.content)

    def test_16_action_condition_predicate(self):
        spec = InteractionSpecification(
            name="rain_option",
            options=[
                InteractionOption(
                    id=1,
                    label="Give Umbrella",
                    condition_predicate="minecraft_ai:is_raining",
                    actions=[ActionSpecification(action_type="give_item", target="@s", item="minecraft:stick")]
                )
            ]
        )
        resources = self.mech_gen.generate(spec)
        select_res = next(r for r in resources if r.relative_path.endswith("select_1.mcfunction"))

        self.assertIn("execute if predicate minecraft_ai:is_raining run", select_res.content)


if __name__ == "__main__":
    unittest.main()
