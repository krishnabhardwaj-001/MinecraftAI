"""
Step 16.2 Test Suite: Structured Data Contracts & Models for Scoreboard Systems.
Validates:
1. Scoreboard objective model
2. deathCount objective
3. sidebar display slot
4. remove_score
5. operation_score with +=
6. operation_score with =
7. operation_score with ><
8. invalid scoreboard operation
9. score-to-score >= comparison
10. score-to-score < comparison
11. invalid comparison operator
12. invalid objective name
13. objective name over 16 characters
14. negative add_score rejected
15. negative remove_score rejected
16. float score rejected
17. boolean score rejected
18. existing set_score still works
19. existing add_score still works
20. existing reset_score still works
21. existing state-machine model still works
22. scoreboard mechanism validation in validate_mechanism_specification()
"""

import unittest
from pydantic import ValidationError

from generator.models import (
    ActionSpecification,
    MechanismSpecification,
    ScoreCompareCondition,
    ScoreboardObjectiveDefinition,
    validate_mechanism_specification,
    validate_objective_name,
    validate_criteria,
    validate_display_slot,
    validate_score_operation,
    validate_comparison_operator,
    VALID_SCORE_OPERATIONS,
    VALID_SCORE_COMPARISONS,
)


class TestStep16ScoreboardModels(unittest.TestCase):

    def test_01_scoreboard_objective_model(self):
        """1. Scoreboard objective model structured representation."""
        obj = ScoreboardObjectiveDefinition(
            objective="deaths",
            criteria="deathCount",
            display_name="Player Deaths",
            display_slot="sidebar"
        )
        self.assertEqual(obj.type, "scoreboard_objective")
        self.assertEqual(obj.objective, "deaths")
        self.assertEqual(obj.criteria, "deathCount")
        self.assertEqual(obj.display_name, "Player Deaths")
        self.assertEqual(obj.display_slot, "sidebar")

        # Test conversion from MechanismSpecification
        mech = MechanismSpecification(
            type="scoreboard_objective",
            objective="deaths",
            criteria="deathCount",
            display_name="Player Deaths",
            display_slot="sidebar"
        )
        mech.validate_completeness()
        obj_def = mech.to_scoreboard_objective_definition()
        self.assertIsInstance(obj_def, ScoreboardObjectiveDefinition)
        self.assertEqual(obj_def.objective, "deaths")
        self.assertEqual(obj_def.criteria, "deathCount")

    def test_02_deathcount_objective(self):
        """2. deathCount and other authoritative built-in criteria."""
        obj = ScoreboardObjectiveDefinition(objective="deaths", criteria="deathCount")
        self.assertEqual(obj.criteria, "deathCount")

        # Other built-ins
        builtins = ["dummy", "trigger", "playerKillCount", "totalKillCount", "health", "xp", "level", "food", "air", "armor"]
        for crit in builtins:
            o = ScoreboardObjectiveDefinition(objective="test_crit", criteria=crit)
            self.assertEqual(o.criteria, crit)

        # Statistic criteria prefixes
        stat_crit = ScoreboardObjectiveDefinition(objective="mined_dia", criteria="minecraft.mined:minecraft.diamond_ore")
        self.assertEqual(stat_crit.criteria, "minecraft.mined:minecraft.diamond_ore")

        # Invalid criteria rejected
        with self.assertRaises(ValidationError):
            ScoreboardObjectiveDefinition(objective="bad_crit", criteria="invalid_crit_type")

    def test_03_sidebar_display_slot(self):
        """3. sidebar display slot and valid variations."""
        for slot in ["sidebar", "list", "below_name", "sidebar.team.red", "sidebar.team.blue"]:
            obj = ScoreboardObjectiveDefinition(objective="score", criteria="dummy", display_slot=slot)
            self.assertEqual(obj.display_slot, slot)

        # Invalid slot rejected
        with self.assertRaises(ValidationError):
            ScoreboardObjectiveDefinition(objective="score", criteria="dummy", display_slot="top_hud")

        # Invalid team color rejected
        with self.assertRaises(ValidationError):
            ScoreboardObjectiveDefinition(objective="score", criteria="dummy", display_slot="sidebar.team.neon")

    def test_04_remove_score(self):
        """4. remove_score action specification."""
        act = ActionSpecification(
            action_type="remove_score",
            target="@s",
            objective="points",
            score_value=5
        )
        self.assertEqual(act.action_type, "remove_score")
        self.assertEqual(act.target, "@s")
        self.assertEqual(act.objective, "points")
        self.assertEqual(act.score_value, 5)

        # Missing score_value rejected for remove_score
        with self.assertRaises(ValidationError):
            ActionSpecification(action_type="remove_score", target="@s", objective="points")

    def test_05_operation_score_with_plus_equals(self):
        """5. operation_score with += operator."""
        act = ActionSpecification(
            action_type="operation_score",
            target="@s",
            objective="total_score",
            operation="+=",
            source_holder="@s",
            source_objective="bonus_points"
        )
        self.assertEqual(act.action_type, "operation_score")
        self.assertEqual(act.target, "@s")
        self.assertEqual(act.objective, "total_score")
        self.assertEqual(act.operation, "+=")
        self.assertEqual(act.source_holder, "@s")
        self.assertEqual(act.source_objective, "bonus_points")

    def test_06_operation_score_with_equals(self):
        """6. operation_score with = operator."""
        act = ActionSpecification(
            action_type="operation_score",
            target="@s",
            objective="total_score",
            operation="=",
            source_holder="#global",
            source_objective="high_score"
        )
        self.assertEqual(act.operation, "=")

    def test_07_operation_score_with_swap(self):
        """7. operation_score with >< swap operator and all valid operators."""
        act = ActionSpecification(
            action_type="operation_score",
            target="player1",
            objective="score",
            operation="><",
            source_holder="player2",
            source_objective="score"
        )
        self.assertEqual(act.operation, "><")

        # All 9 valid operators from knowledge
        for op in VALID_SCORE_OPERATIONS:
            a = ActionSpecification(
                action_type="operation_score",
                target="@s",
                objective="score1",
                operation=op,
                source_holder="#global",
                source_objective="score2"
            )
            self.assertEqual(a.operation, op)

    def test_08_invalid_scoreboard_operation(self):
        """8. invalid scoreboard operation rejected."""
        invalid_ops = ["++", "--", "**=", "assign", "unknown", "==", "!="]
        for bad_op in invalid_ops:
            with self.assertRaises(ValidationError):
                ActionSpecification(
                    action_type="operation_score",
                    target="@s",
                    objective="total_score",
                    operation=bad_op,
                    source_holder="@s",
                    source_objective="bonus_points"
                )

        # Missing required fields for operation_score
        with self.assertRaises(ValidationError):
            ActionSpecification(
                action_type="operation_score",
                target="@s",
                objective="total_score",
                operation="+="
                # missing source_holder and source_objective
            )

    def test_09_score_to_score_greater_than_or_equal(self):
        """9. score-to-score >= comparison condition."""
        cond = ScoreCompareCondition(
            target="@s",
            target_objective="player_score",
            operator=">=",
            source="#global",
            source_objective="high_score",
            inverted=False
        )
        self.assertEqual(cond.type, "score_compare")
        self.assertEqual(cond.target, "@s")
        self.assertEqual(cond.target_objective, "player_score")
        self.assertEqual(cond.operator, ">=")
        self.assertEqual(cond.source, "#global")
        self.assertEqual(cond.source_objective, "high_score")
        self.assertFalse(cond.inverted)

        # Embedded in ActionSpecification
        act = ActionSpecification(
            action_type="give_item",
            target="@s",
            item="minecraft:diamond",
            conditions=[cond]
        )
        self.assertEqual(len(act.conditions), 1)

    def test_10_score_to_score_less_than(self):
        """10. score-to-score < comparison condition."""
        cond = ScoreCompareCondition(
            target="@s",
            target_objective="player_score",
            operator="<",
            source="#global",
            source_objective="high_score",
            inverted=True
        )
        self.assertEqual(cond.operator, "<")
        self.assertTrue(cond.inverted)

        # Test as dict inside ActionSpecification conditions
        cond_dict = {
            "type": "score_compare",
            "target": "@s",
            "target_objective": "player_score",
            "operator": "<",
            "source": "#global",
            "source_objective": "high_score",
            "inverted": False
        }
        act = ActionSpecification(
            action_type="apply_effect",
            target="@s",
            effect="speed",
            conditions=[cond_dict]
        )
        self.assertEqual(len(act.conditions), 1)
        self.assertEqual(act.conditions[0]["operator"], "<")

    def test_11_invalid_comparison_operator(self):
        """11. invalid comparison operator rejected."""
        invalid_operators = ["!=", "<>", "==", "=>", "=<", "like", "in"]
        for bad_op in invalid_operators:
            with self.assertRaises(ValidationError):
                ScoreCompareCondition(
                    target="@s",
                    target_objective="player_score",
                    operator=bad_op,
                    source="#global",
                    source_objective="high_score"
                )

    def test_12_invalid_objective_name(self):
        """12. invalid objective name characters rejected."""
        bad_names = ["bad name", "bad!name", "bad@name", "bad#name", "bad$name", "", "   "]
        for bad in bad_names:
            with self.assertRaises(ValidationError):
                ScoreboardObjectiveDefinition(objective=bad, criteria="dummy")
            with self.assertRaises(ValidationError):
                ActionSpecification(action_type="set_score", target="@s", objective=bad, score_value=0)

    def test_13_objective_name_over_16_characters(self):
        """13. objective name over 16 characters rejected, <=16 accepted."""
        # Exactly 16 chars -> accepted
        valid_16 = "a" * 16
        obj = ScoreboardObjectiveDefinition(objective=valid_16, criteria="dummy")
        self.assertEqual(obj.objective, valid_16)

        # 17 chars -> rejected
        invalid_17 = "a" * 17
        with self.assertRaises(ValidationError):
            ScoreboardObjectiveDefinition(objective=invalid_17, criteria="dummy")
        with self.assertRaises(ValidationError):
            ActionSpecification(action_type="set_score", target="@s", objective=invalid_17, score_value=0)

    def test_14_negative_add_score_rejected(self):
        """14. negative add_score rejected."""
        with self.assertRaises(ValidationError):
            ActionSpecification(action_type="add_score", target="@s", objective="score", score_value=-1)
        with self.assertRaises(ValidationError):
            ActionSpecification(action_type="add_score", target="@s", objective="score", score_value=-10)

    def test_15_negative_remove_score_rejected(self):
        """15. negative remove_score rejected."""
        with self.assertRaises(ValidationError):
            ActionSpecification(action_type="remove_score", target="@s", objective="score", score_value=-1)
        with self.assertRaises(ValidationError):
            ActionSpecification(action_type="remove_score", target="@s", objective="score", score_value=-50)

    def test_16_float_score_rejected(self):
        """16. float scores strictly rejected (no silent conversion)."""
        rejected_values = [30.5, 0.5, 30.0, "30.0", "0.5", "-0.5", "12.34"]
        for val in rejected_values:
            with self.assertRaises(ValidationError):
                ActionSpecification(action_type="set_score", target="@s", objective="score", score_value=val)
            with self.assertRaises(ValidationError):
                ActionSpecification(action_type="add_score", target="@s", objective="score", score_value=val)
            with self.assertRaises(ValidationError):
                ActionSpecification(action_type="remove_score", target="@s", objective="score", score_value=val)

    def test_17_boolean_score_rejected(self):
        """17. boolean score strictly rejected."""
        for val in [True, False]:
            with self.assertRaises(ValidationError):
                ActionSpecification(action_type="set_score", target="@s", objective="score", score_value=val)
            with self.assertRaises(ValidationError):
                ActionSpecification(action_type="add_score", target="@s", objective="score", score_value=val)
            with self.assertRaises(ValidationError):
                ActionSpecification(action_type="remove_score", target="@s", objective="score", score_value=val)

    def test_18_existing_set_score_still_works(self):
        """18. existing set_score still works (including negative numbers)."""
        act = ActionSpecification(
            action_type="set_score",
            target="#global",
            objective="rain_state",
            score_value=0
        )
        self.assertEqual(act.action_type, "set_score")
        self.assertEqual(act.target, "#global")
        self.assertEqual(act.objective, "rain_state")
        self.assertEqual(act.score_value, 0)

        # Negative values are valid for scoreboard players set in Minecraft
        neg_set = ActionSpecification(
            action_type="set_score",
            target="@s",
            objective="temp",
            score_value=-5
        )
        self.assertEqual(neg_set.score_value, -5)

    def test_19_existing_add_score_still_works(self):
        """19. existing add_score still works for non-negative integers."""
        act = ActionSpecification(
            action_type="add_score",
            target="@s",
            objective="player_score",
            score_value=1
        )
        self.assertEqual(act.score_value, 1)

        act0 = ActionSpecification(
            action_type="add_score",
            target="@s",
            objective="player_score",
            score_value=0
        )
        self.assertEqual(act0.score_value, 0)

    def test_20_existing_reset_score_still_works(self):
        """20. existing reset_score still works."""
        act = ActionSpecification(
            action_type="reset_score",
            target="@s",
            objective="player_score"
        )
        self.assertEqual(act.action_type, "reset_score")
        self.assertEqual(act.target, "@s")
        self.assertEqual(act.objective, "player_score")

        # Global target reset
        act_global = ActionSpecification(
            action_type="reset_score",
            target="#global",
            objective="rain_state"
        )
        self.assertEqual(act_global.target, "#global")

    def test_21_existing_state_machine_model_still_works(self):
        """21. existing state-machine model continues working."""
        mech = MechanismSpecification(
            type="state_machine",
            objective="weather_tracker",
            condition_predicate="minecraft_ai:is_raining",
            on_enter=[
                ActionSpecification(
                    action_type="set_score",
                    target="#global",
                    objective="rain_state",
                    score_value=1
                )
            ]
        )
        validate_mechanism_specification(mech)
        mech.validate_completeness()

    def test_22_validate_mechanism_specification_scoreboard(self):
        """22. validate_mechanism_specification handles scoreboard_objective."""
        # Valid dict specification
        valid_dict = {
            "type": "scoreboard_objective",
            "objective": "deaths",
            "criteria": "deathCount",
            "display_name": "Player Deaths",
            "display_slot": "sidebar"
        }
        validate_mechanism_specification(valid_dict)

        # Valid MechanismSpecification
        mech = MechanismSpecification(
            type="scoreboard_objective",
            objective="deaths",
            criteria="deathCount",
            display_name="Player Deaths",
            display_slot="sidebar"
        )
        validate_mechanism_specification(mech)

        # Valid ScoreboardObjectiveDefinition
        obj_def = ScoreboardObjectiveDefinition(
            objective="deaths",
            criteria="deathCount"
        )
        validate_mechanism_specification(obj_def)

        # Incomplete: missing objective
        with self.assertRaises(ValueError):
            validate_mechanism_specification({"type": "scoreboard_objective", "criteria": "dummy"})

        # Incomplete: missing criteria
        with self.assertRaises(ValueError):
            validate_mechanism_specification({"type": "scoreboard_objective", "objective": "test"})

        # Invalid: criteria is dict
        with self.assertRaises(ValueError):
            validate_mechanism_specification({"type": "scoreboard_objective", "objective": "test", "criteria": {"bad": "dict"}})

        # Invalid: display slot
        with self.assertRaises(ValueError):
            validate_mechanism_specification({"type": "scoreboard_objective", "objective": "test", "criteria": "dummy", "display_slot": "invalid_slot"})


if __name__ == "__main__":
    unittest.main()
