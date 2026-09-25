"""
test_step16_generator.py - Step 16.3 Deterministic Scoreboard Command Generation Tests
Authoritative target: Minecraft Java 1.21.11

Tests all 27 required scoreboard generator capabilities:
1. objective creation
2. objective creation with display name
3. objective display slot
4. duplicate objective consolidation
5. conflicting objective definitions
6. set_score
7. add_score
8. remove_score
9. reset_score
10-18. all 9 operations (=, +=, -=, *=, /=, %=, <, >, ><)
19. score range condition
20. inverted score range condition
21. score-to-score >=
22. inverted score-to-score comparison
23. global holder #global
24. per-player selector @a/@s
25. scoreboard action inside state-machine on_enter
26. deterministic function/objective deduplication
27. existing rain datapack generation remains unchanged
28. focused regression test proving @a -> @s transformation only occurs in state machine context
"""

import json
import shutil
import unittest
from pathlib import Path

from generator.datapack_generator import DatapackGenerator, generate_datapack
from generator.mechanisms.function_mech import FunctionMechanismGenerator
from generator.mechanisms.state_machine_mech import StateMachineMechanismGenerator
from generator.models import (
    ActionSpecification,
    FunctionDefinition,
    MechanismSpecification,
    ScoreboardObjectiveDefinition,
    ScoreCompareCondition,
)


class TestStep16Generator(unittest.TestCase):
    def setUp(self):
        self.func_gen = FunctionMechanismGenerator(version="1.21.11")
        self.sm_gen = StateMachineMechanismGenerator(version="1.21.11")
        self.test_output_dir = Path("generated") / "test_s16_generator"
        if self.test_output_dir.exists():
            shutil.rmtree(self.test_output_dir)
        self.test_output_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self.test_output_dir.exists():
            shutil.rmtree(self.test_output_dir)

    # 1. Objective creation
    def test_01_objective_creation(self):
        obj = ScoreboardObjectiveDefinition(objective="deaths", criteria="deathCount")
        cmds = self.func_gen.synthesize_objective_command(obj)
        self.assertEqual(cmds, ["scoreboard objectives add deaths deathCount"])

    # 2. Objective creation with display name
    def test_02_objective_creation_with_display_name(self):
        # Plain string display name
        obj_str = ScoreboardObjectiveDefinition(
            objective="deaths",
            criteria="deathCount",
            display_name="Player Deaths"
        )
        cmds_str = self.func_gen.synthesize_objective_command(obj_str)
        self.assertEqual(cmds_str, ['scoreboard objectives add deaths deathCount "Player Deaths"'])

        # Dict / JSON text component display name
        obj_json = ScoreboardObjectiveDefinition(
            objective="kills",
            criteria="playerKillCount",
            display_name={"text": "Kills", "color": "red"}
        )
        cmds_json = self.func_gen.synthesize_objective_command(obj_json)
        self.assertEqual(len(cmds_json), 1)
        self.assertTrue(cmds_json[0].startswith("scoreboard objectives add kills playerKillCount "))
        self.assertIn('"text": "Kills"', cmds_json[0])

    # 3. Objective display slot
    def test_03_objective_display_slot(self):
        obj = ScoreboardObjectiveDefinition(
            objective="deaths",
            criteria="deathCount",
            display_name="Player Deaths",
            display_slot="sidebar"
        )
        cmds = self.func_gen.synthesize_objective_command(obj)
        self.assertEqual(cmds, [
            'scoreboard objectives add deaths deathCount "Player Deaths"',
            "scoreboard objectives setdisplay sidebar deaths"
        ])

        # Team color display slot
        obj_team = ScoreboardObjectiveDefinition(
            objective="red_kills",
            criteria="dummy",
            display_slot="sidebar.team.red"
        )
        cmds_team = self.func_gen.synthesize_objective_command(obj_team)
        self.assertEqual(cmds_team, [
            "scoreboard objectives add red_kills dummy",
            "scoreboard objectives setdisplay sidebar.team.red red_kills"
        ])

    # 4. Duplicate objective consolidation
    def test_04_duplicate_objective_consolidation(self):
        plan = {
            "status": "ready",
            "summary": "Duplicate objective consolidation test",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Setup coins",
                    "mechanisms": [
                        {
                            "type": "scoreboard_objective",
                            "objective": "coins",
                            "criteria": "dummy",
                            "display_name": "Coins",
                            "display_slot": "sidebar"
                        },
                        {
                            "type": "scoreboard_objective",
                            "objective": "coins",
                            "criteria": "dummy",
                            "display_name": "Coins",
                            "display_slot": "sidebar"
                        }
                    ]
                }
            ]
        }
        gen = DatapackGenerator(output_dir=self.test_output_dir)
        res = gen.generate(plan=plan, datapack_name="dup_obj_pack", create_zip=False)
        load_path = res.datapack_path / "data" / "minecraft_ai" / "function" / "load.mcfunction"
        self.assertTrue(load_path.exists())
        content = load_path.read_text(encoding="utf-8")
        # Objective add must appear exactly once
        self.assertEqual(content.count('scoreboard objectives add coins dummy "Coins"'), 1)
        self.assertEqual(content.count("scoreboard objectives setdisplay sidebar coins"), 1)

    # 5. Conflicting objective definitions
    def test_05_conflicting_objective_definitions(self):
        # Criteria conflict
        plan_crit = {
            "scoreboard_objectives": [
                ScoreboardObjectiveDefinition(objective="coins", criteria="dummy"),
                ScoreboardObjectiveDefinition(objective="coins", criteria="deathCount")
            ]
        }
        gen = DatapackGenerator(output_dir=self.test_output_dir)
        with self.assertRaises(ValueError) as ctx:
            gen.generate(plan=plan_crit, datapack_name="conflict_crit", create_zip=False)
        self.assertIn("Conflicting criteria", str(ctx.exception))

        # Display name conflict
        plan_disp = {
            "scoreboard_objectives": [
                ScoreboardObjectiveDefinition(objective="coins", criteria="dummy", display_name="Coins"),
                ScoreboardObjectiveDefinition(objective="coins", criteria="dummy", display_name="Gold")
            ]
        }
        with self.assertRaises(ValueError) as ctx:
            gen.generate(plan=plan_disp, datapack_name="conflict_disp", create_zip=False)
        self.assertIn("Conflicting display_name", str(ctx.exception))

        # Display slot conflict
        plan_slot = {
            "scoreboard_objectives": [
                ScoreboardObjectiveDefinition(objective="coins", criteria="dummy", display_slot="sidebar"),
                ScoreboardObjectiveDefinition(objective="coins", criteria="dummy", display_slot="list")
            ]
        }
        with self.assertRaises(ValueError) as ctx:
            gen.generate(plan=plan_slot, datapack_name="conflict_slot", create_zip=False)
        self.assertIn("Conflicting display_slot", str(ctx.exception))

    # 6. set_score
    def test_06_set_score(self):
        act = ActionSpecification(
            action_type="set_score",
            target="@s",
            objective="coins",
            score_value=50
        )
        cmd = self.func_gen.synthesize_action(act)
        self.assertEqual(cmd, "scoreboard players set @s coins 50")

    # 7. add_score
    def test_07_add_score(self):
        act = ActionSpecification(
            action_type="add_score",
            target="@s",
            objective="coins",
            score_value=10
        )
        cmd = self.func_gen.synthesize_action(act)
        self.assertEqual(cmd, "scoreboard players add @s coins 10")

    # 8. remove_score
    def test_08_remove_score(self):
        act = ActionSpecification(
            action_type="remove_score",
            target="@s",
            objective="coins",
            score_value=10
        )
        cmd = self.func_gen.synthesize_action(act)
        self.assertEqual(cmd, "scoreboard players remove @s coins 10")

    # 9. reset_score
    def test_09_reset_score(self):
        # With objective
        act_with_obj = ActionSpecification(
            action_type="reset_score",
            target="@s",
            objective="coins"
        )
        cmd_with = self.func_gen.synthesize_action(act_with_obj)
        self.assertEqual(cmd_with, "scoreboard players reset @s coins")

        # Without objective (resets all objectives for target)
        act_no_obj = ActionSpecification(
            action_type="reset_score",
            target="@s"
        )
        cmd_no = self.func_gen.synthesize_action(act_no_obj)
        self.assertEqual(cmd_no, "scoreboard players reset @s")

    # 10. operation_score =
    def test_10_operation_score_assign(self):
        act = ActionSpecification(
            action_type="operation_score",
            target="@s",
            objective="total_score",
            operation="=",
            source_holder="@s",
            source_objective="bonus_points"
        )
        self.assertEqual(self.func_gen.synthesize_action(act), "scoreboard players operation @s total_score = @s bonus_points")

    # 11. operation_score +=
    def test_11_operation_score_add(self):
        act = ActionSpecification(
            action_type="operation_score",
            target="@s",
            objective="total_score",
            operation="+=",
            source_holder="@s",
            source_objective="bonus_points"
        )
        self.assertEqual(self.func_gen.synthesize_action(act), "scoreboard players operation @s total_score += @s bonus_points")

    # 12. operation_score -=
    def test_12_operation_score_subtract(self):
        act = ActionSpecification(
            action_type="operation_score",
            target="@s",
            objective="total_score",
            operation="-=",
            source_holder="@s",
            source_objective="bonus_points"
        )
        self.assertEqual(self.func_gen.synthesize_action(act), "scoreboard players operation @s total_score -= @s bonus_points")

    # 13. operation_score *=
    def test_13_operation_score_multiply(self):
        act = ActionSpecification(
            action_type="operation_score",
            target="@s",
            objective="total_score",
            operation="*=",
            source_holder="@s",
            source_objective="multiplier"
        )
        self.assertEqual(self.func_gen.synthesize_action(act), "scoreboard players operation @s total_score *= @s multiplier")

    # 14. operation_score /=
    def test_14_operation_score_divide(self):
        act = ActionSpecification(
            action_type="operation_score",
            target="@s",
            objective="total_score",
            operation="/=",
            source_holder="@s",
            source_objective="divisor"
        )
        self.assertEqual(self.func_gen.synthesize_action(act), "scoreboard players operation @s total_score /= @s divisor")

    # 15. operation_score %=
    def test_15_operation_score_modulo(self):
        act = ActionSpecification(
            action_type="operation_score",
            target="@s",
            objective="total_score",
            operation="%=",
            source_holder="@s",
            source_objective="mod_base"
        )
        self.assertEqual(self.func_gen.synthesize_action(act), "scoreboard players operation @s total_score %= @s mod_base")

    # 16. operation_score <
    def test_16_operation_score_min(self):
        act = ActionSpecification(
            action_type="operation_score",
            target="@s",
            objective="cap",
            operation="<",
            source_holder="#global",
            source_objective="max_limit"
        )
        self.assertEqual(self.func_gen.synthesize_action(act), "scoreboard players operation @s cap < #global max_limit")

    # 17. operation_score >
    def test_17_operation_score_max(self):
        act = ActionSpecification(
            action_type="operation_score",
            target="@s",
            objective="floor",
            operation=">",
            source_holder="#global",
            source_objective="min_limit"
        )
        self.assertEqual(self.func_gen.synthesize_action(act), "scoreboard players operation @s floor > #global min_limit")

    # 18. operation_score ><
    def test_18_operation_score_swap(self):
        act = ActionSpecification(
            action_type="operation_score",
            target="@s",
            objective="score_a",
            operation="><",
            source_holder="@s",
            source_objective="score_b"
        )
        self.assertEqual(self.func_gen.synthesize_action(act), "scoreboard players operation @s score_a >< @s score_b")

    # 19. score range condition
    def test_19_score_range_condition(self):
        act = ActionSpecification(
            action_type="send_message",
            target="@s",
            message="Level 10 reached",
            conditions=[{
                "type": "score",
                "holder": "@s",
                "objective": "player_level",
                "matches": "10.."
            }]
        )
        cmd = self.func_gen.synthesize_action(act)
        self.assertEqual(
            cmd,
            'execute if score @s player_level matches 10.. run tellraw @s {"text": "Level 10 reached"}'
        )

    # 20. inverted score range condition
    def test_20_inverted_score_range_condition(self):
        act = ActionSpecification(
            action_type="send_message",
            target="@s",
            message="Below level 10",
            conditions=[{
                "type": "score",
                "holder": "@s",
                "objective": "player_level",
                "matches": "10..",
                "inverted": True
            }]
        )
        cmd = self.func_gen.synthesize_action(act)
        self.assertEqual(
            cmd,
            'execute unless score @s player_level matches 10.. run tellraw @s {"text": "Below level 10"}'
        )

    # 21. score-to-score >=
    def test_21_score_to_score_comparison_ge(self):
        cond = ScoreCompareCondition(
            target="@s",
            target_objective="player_score",
            operator=">=",
            source="#global",
            source_objective="high_score",
            inverted=False
        )
        act = ActionSpecification(
            action_type="send_message",
            target="@s",
            message="High score beaten",
            conditions=[cond]
        )
        cmd = self.func_gen.synthesize_action(act)
        self.assertEqual(
            cmd,
            'execute if score @s player_score >= #global high_score run tellraw @s {"text": "High score beaten"}'
        )

    # 22. inverted score-to-score comparison
    def test_22_inverted_score_to_score_comparison(self):
        cond = ScoreCompareCondition(
            target="@s",
            target_objective="player_score",
            operator="<",
            source="#global",
            source_objective="high_score",
            inverted=True
        )
        act = ActionSpecification(
            action_type="send_message",
            target="@s",
            message="Not lower",
            conditions=[cond]
        )
        cmd = self.func_gen.synthesize_action(act)
        self.assertEqual(
            cmd,
            'execute unless score @s player_score < #global high_score run tellraw @s {"text": "Not lower"}'
        )

    # 23. global score holder #global
    def test_23_global_score_holder(self):
        # Set score on #global
        act = ActionSpecification(
            action_type="set_score",
            score_holder="#global",
            objective="game_state",
            score_value=0
        )
        cmd = self.func_gen.synthesize_action(act)
        self.assertEqual(cmd, "scoreboard players set #global game_state 0")
        # Ensure #global is preserved without prepending @
        self.assertNotIn("@#global", cmd)
        self.assertNotIn("@global", cmd)

        # Non-selector score holders like #state and #timer
        act_timer = ActionSpecification(
            action_type="add_score",
            score_holder="#timer",
            objective="ticks",
            score_value=1
        )
        self.assertEqual(self.func_gen.synthesize_action(act_timer), "scoreboard players add #timer ticks 1")

    # 24. per-player selector @a/@s
    def test_24_per_player_selector(self):
        act_a = ActionSpecification(
            action_type="add_score",
            target="@a",
            objective="points",
            score_value=1
        )
        self.assertEqual(self.func_gen.synthesize_action(act_a), "scoreboard players add @a points 1")

        act_s = ActionSpecification(
            action_type="add_score",
            target="@s",
            objective="points",
            score_value=1
        )
        self.assertEqual(self.func_gen.synthesize_action(act_s), "scoreboard players add @s points 1")

    # 25. scoreboard action inside state-machine on_enter
    def test_25_scoreboard_action_in_state_machine_on_enter(self):
        spec = MechanismSpecification(
            type="state_machine",
            objective="reward_state",
            condition_predicate="minecraft_ai:is_raining",
            state_scope="global",
            on_enter=[
                ActionSpecification(
                    action_type="add_score",
                    target="@s",
                    objective="coins",
                    score_value=10
                )
            ]
        )
        resources = self.sm_gen.generate(spec)
        rel_paths = {r.relative_path: r.content for r in resources}
        tick_content = rel_paths["data/minecraft_ai/function/tick.mcfunction"]

        self.assertIn("as @a at @s run scoreboard players add @s coins 10", tick_content)

    # 26. deterministic function/objective deduplication
    def test_26_deterministic_function_and_objective_deduplication(self):
        gen = DatapackGenerator(output_dir=self.test_output_dir)

        # Same non-lifecycle function path with identical content is kept cleanly
        func1 = FunctionDefinition(
            function_path="helper",
            commands=["say helper line 1", "say helper line 2"]
        )
        func2 = FunctionDefinition(
            function_path="helper",
            commands=["say helper line 1", "say helper line 2"]
        )
        res = gen.generate(functions=[func1, func2], datapack_name="dedup_pack", create_zip=False)
        helper_path = res.datapack_path / "data" / "minecraft" / "function" / "helper.mcfunction"
        self.assertTrue(helper_path.exists())
        content = helper_path.read_text(encoding="utf-8")
        self.assertEqual(content.count("say helper line 1"), 1)

        # Same non-lifecycle function path with differing content raises ValueError
        func_conflict = FunctionDefinition(
            function_path="helper",
            commands=["say different content"]
        )
        with self.assertRaises(ValueError) as ctx:
            gen.generate(functions=[func1, func_conflict], datapack_name="conflict_pack", create_zip=False)
        self.assertIn("Conflicting function content", str(ctx.exception))

    # 27. existing rain datapack generation remains unchanged
    def test_27_existing_rain_datapack_unchanged(self):
        plan = {
            "status": "ready",
            "summary": "Give diamond once when rain starts",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Reward diamond on rain start",
                    "mechanisms": [
                        {
                            "type": "predicate",
                            "namespace": "minecraft_ai",
                            "path": "is_raining",
                            "condition_type": "minecraft:weather_check",
                            "condition_params": {"raining": True}
                        },
                        {
                            "type": "state_machine",
                            "namespace": "minecraft_ai",
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
        gen = DatapackGenerator(output_dir=self.test_output_dir)
        res = gen.generate(plan=plan, datapack_name="rain_pack", create_zip=True)

        load_path = res.datapack_path / "data" / "minecraft_ai" / "function" / "load.mcfunction"
        tick_path = res.datapack_path / "data" / "minecraft_ai" / "function" / "tick.mcfunction"
        mcmeta_path = res.datapack_path / "pack.mcmeta"

        self.assertTrue(load_path.exists())
        self.assertTrue(tick_path.exists())
        self.assertTrue(mcmeta_path.exists())

        load_content = load_path.read_text(encoding="utf-8")
        tick_content = tick_path.read_text(encoding="utf-8")
        mcmeta_data = json.loads(mcmeta_path.read_text(encoding="utf-8"))

        self.assertIn("scoreboard objectives add rain_state dummy", load_content)
        self.assertIn("scoreboard players set #global rain_state 0", load_content)
        self.assertIn("give @s minecraft:diamond 1", tick_content)
        self.assertEqual(mcmeta_data["pack"]["pack_format"], 94)
        self.assertEqual(mcmeta_data["pack"]["max_format"], [94, 1])

    # 28. focused regression test for @a -> @s transformation context
    def test_28_regression_at_a_to_at_s_only_in_state_machine_context(self):
        act_a = ActionSpecification(
            action_type="add_score",
            target="@a",
            objective="coins",
            score_value=10
        )
        # Direct synthesis outside state machine must NOT transform @a to @s
        direct_cmd = self.func_gen.synthesize_action(act_a)
        self.assertEqual(direct_cmd, "scoreboard players add @a coins 10")

        # Extraction inside StateMachineMechanismGenerator transforms @a to @s for execution under 'as @a at @s'
        sm_cmd = self.sm_gen._extract_action_command(act_a)
        self.assertEqual(sm_cmd, "scoreboard players add @s coins 10")

        # Explicit non-@a targets must NOT be rewritten by _extract_action_command
        act_global = ActionSpecification(
            action_type="set_score",
            score_holder="#global",
            objective="coins",
            score_value=0
        )
        self.assertEqual(self.sm_gen._extract_action_command(act_global), "scoreboard players set #global coins 0")

        act_p = ActionSpecification(
            action_type="add_score",
            target="@p",
            objective="coins",
            score_value=5
        )
        self.assertEqual(self.sm_gen._extract_action_command(act_p), "scoreboard players add @p coins 5")


if __name__ == "__main__":
    unittest.main()
