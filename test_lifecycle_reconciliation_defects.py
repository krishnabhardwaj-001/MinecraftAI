"""
test_lifecycle_reconciliation_defects.py - Regression tests for lifecycle reconciler and QA simulator

Covers:
1. Defect 1: State machines with empty on_enter are not misclassified as reset machines.
2. Defect 2: Scoreboard objective names never exceed 16 characters and disambiguate cleanly without collisions.
3. Defect 3: DatapackGenerator merges debug.mcfunction cleanly across multiple state machines without throwing conflicts.
4. Defect 4: Temporal QA simulation properly evaluates compound non-contradictory predicates without false STATE_EVENT_UNREACHABLE.
"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from ai.lifecycle_reconciler import MechanismLifecycleReconciler, format_safe_objective_name
from ai.version_registry import VersionContext
from generator.datapack_generator import DatapackGenerator
from generator.models import ActionSpecification, MechanismSpecification, PredicateDefinition
from qa.scoreboard_semantics import ScoreboardSemanticSimulator


class TestLifecycleReconciliationDefects(unittest.TestCase):
    def setUp(self):
        self.reconciler = MechanismLifecycleReconciler()
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_defect_1_empty_on_enter_not_treated_as_reset_machine(self):
        """
        Verify that a secondary state machine with empty on_enter is NOT classified
        as a reset machine and absorbed into on_exit.
        """
        sms = [
            {
                "type": "state_machine",
                "objective": "player_event",
                "condition_predicate": "custom:pred_a",
                "on_enter": [
                    {"type": "command", "command": "give @a diamond 1"}
                ],
                "on_exit": []
            },
            {
                "type": "state_machine",
                "objective": "player_event",
                "condition_predicate": "custom:pred_b",
                "on_enter": [],  # Empty on_enter: previously all() returned True!
                "on_exit": [
                    {"type": "command", "command": "say exited b"}
                ]
            }
        ]

        reconciled = self.reconciler.reconcile(sms, predicates_info={})
        reconciled_sms = [m for m in reconciled if m.get("type") == "state_machine"]
        # Must retain 2 state machines, not collapse into 1
        self.assertEqual(len(reconciled_sms), 2)
        # Objectives must be distinct and <= 16 chars
        obj1 = reconciled_sms[0]["objective"]
        obj2 = reconciled_sms[1]["objective"]
        self.assertNotEqual(obj1, obj2)
        self.assertLessEqual(len(obj1), 16)
        self.assertLessEqual(len(obj2), 16)

    def test_defect_2_objective_name_length_and_disambiguation(self):
        """
        Verify that objective names never exceed 16 characters, valid characters only,
        and disambiguate deterministically.
        """
        long_name = "extremely_long_player_objective_event"
        safe1 = format_safe_objective_name(long_name)
        self.assertLessEqual(len(safe1), 16)
        self.assertRegex(safe1, r"^[a-zA-Z0-9_]+$")

        used = {safe1}
        safe2 = format_safe_objective_name(long_name, used_objectives=used)
        self.assertLessEqual(len(safe2), 16)
        self.assertNotEqual(safe1, safe2)
        self.assertRegex(safe2, r"^[a-zA-Z0-9_]+$")

        # Disambiguating multiple state machines targeting the same long objective
        sms = [
            {
                "type": "state_machine",
                "objective": "super_lengthy_objective_target_name",
                "condition_predicate": "ns:pred_alpha",
                "on_enter": [{"type": "command", "command": "say 1"}],
            },
            {
                "type": "state_machine",
                "objective": "super_lengthy_objective_target_name",
                "condition_predicate": "ns:pred_beta",
                "on_enter": [{"type": "command", "command": "say 2"}],
            }
        ]
        result = self.reconciler.reconcile(sms, predicates_info={})
        reconciled_sms = [m for m in result if m.get("type") == "state_machine"]
        for sm in reconciled_sms:
            obj = sm["objective"]
            self.assertLessEqual(len(obj), 16)
            self.assertRegex(obj, r"^[a-zA-Z0-9_]+$")
        self.assertNotEqual(
            reconciled_sms[0]["objective"],
            reconciled_sms[1]["objective"]
        )

    def test_defect_3_debug_mcfunction_merging(self):
        """
        Verify DatapackGenerator merges debug.mcfunction cleanly across multiple
        state machines without throwing duplicate function conflicts.
        """
        generator = DatapackGenerator(output_dir=Path(self.tmp_dir), version="1.21.11")

        sm1 = MechanismSpecification(
            type="state_machine",
            name="sm_rain",
            objective="rain_state",
            condition_predicate="demo:is_raining",
            on_enter=[ActionSpecification(action_type="give_item", target="@a", item="minecraft:diamond", count=1)],
            on_exit=[]
        )
        sm2 = MechanismSpecification(
            type="state_machine",
            name="sm_night",
            objective="night_state",
            condition_predicate="demo:is_night",
            on_enter=[ActionSpecification(action_type="give_item", target="@a", item="minecraft:emerald", count=1)],
            on_exit=[]
        )
        pred1 = PredicateDefinition(
            predicate_path="is_raining",
            namespace="demo",
            conditions={"condition": "minecraft:weather_check", "raining": True}
        )
        pred2 = PredicateDefinition(
            predicate_path="is_night",
            namespace="demo",
            conditions={"condition": "minecraft:time_check", "value": {"min": 13000, "max": 23000}}
        )

        res = generator.generate(
            datapack_name="test_merge_debug",
            state_machines=[sm1, sm2],
            predicates=[pred1, pred2],
            create_zip=False
        )

        debug_file = Path(res.datapack_path) / "data" / "minecraft_ai" / "function" / "debug.mcfunction"
        self.assertTrue(debug_file.exists())
        with open(debug_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Both state machines' diagnostics must be present
        self.assertIn("rain_state", content)
        self.assertIn("night_state", content)
        # Ends with border line
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        self.assertEqual(lines[-1], "say ========================================")

    def _create_synthetic_pack(self, name: str, functions: dict, predicates: dict) -> Path:
        pack_dir = Path(self.tmp_dir) / name
        pack_dir.mkdir(parents=True, exist_ok=True)
        mcmeta = pack_dir / "pack.mcmeta"
        with open(mcmeta, "w", encoding="utf-8") as f:
            json.dump({"pack": {"pack_format": 48, "description": "QA test"}}, f)

        for fn_id, content in functions.items():
            ns, fn_path = fn_id.split(":", 1)
            fn_file = pack_dir / "data" / ns / "function" / f"{fn_path}.mcfunction"
            fn_file.parent.mkdir(parents=True, exist_ok=True)
            with open(fn_file, "w", encoding="utf-8") as f:
                f.write(content)

        for pred_id, pred_data in predicates.items():
            ns, pred_path = pred_id.split(":", 1)
            pred_file = pack_dir / "data" / ns / "predicate" / f"{pred_path}.json"
            pred_file.parent.mkdir(parents=True, exist_ok=True)
            with open(pred_file, "w", encoding="utf-8") as f:
                json.dump(pred_data, f)

        return pack_dir

    def test_defect_4_temporal_qa_compound_predicates_reachability(self):
        """
        Verify that ScoreboardSemanticSimulator properly evaluates compound non-contradictory
        predicates without false STATE_EVENT_UNREACHABLE, while flagging contradictory predicates.
        """
        sim = ScoreboardSemanticSimulator(version="1.21.11")

        # Valid compound predicates (rain + night): should NOT flag unreachable
        valid_dir = self._create_synthetic_pack(
            name="valid_compound",
            functions={
                "valid_compound:load": (
                    "scoreboard objectives add rn_state dummy\n"
                    "scoreboard players set #global rn_state 0\n"
                ),
                "valid_compound:tick": (
                    "execute if score #global rn_state matches 0 if predicate demo:is_raining if predicate demo:is_night run give @a diamond 1\n"
                    "execute if predicate demo:is_raining if predicate demo:is_night run scoreboard players set #global rn_state 1\n"
                    "execute unless predicate demo:is_raining run scoreboard players set #global rn_state 0\n"
                )
            },
            predicates={
                "demo:is_raining": {"condition": "minecraft:weather_check", "raining": True},
                "demo:is_night": {"condition": "minecraft:time_check", "value": {"min": 13000, "max": 23000}}
            }
        )
        findings_valid = sim.analyze_datapack(valid_dir)
        unreachable_valid = [f for f in findings_valid if f.id == "STATE_EVENT_UNREACHABLE"]
        self.assertEqual(len(unreachable_valid), 0)

        # Contradictory compound predicates (raining + inverted raining): SHOULD flag unreachable
        contra_dir = self._create_synthetic_pack(
            name="contra_compound",
            functions={
                "contra_compound:load": (
                    "scoreboard objectives add bad_state dummy\n"
                    "scoreboard players set #global bad_state 0\n"
                ),
                "contra_compound:tick": (
                    "execute if score #global bad_state matches 0 if predicate demo:is_raining if predicate demo:not_raining run give @a diamond 1\n"
                    "execute if predicate demo:is_raining if predicate demo:not_raining run scoreboard players set #global bad_state 1\n"
                    "execute unless predicate demo:is_raining run scoreboard players set #global bad_state 0\n"
                )
            },
            predicates={
                "demo:is_raining": {"condition": "minecraft:weather_check", "raining": True},
                "demo:not_raining": {"condition": "minecraft:inverted", "term": {"condition": "minecraft:weather_check", "raining": True}}
            }
        )
        findings_contra = sim.analyze_datapack(contra_dir)
        unreachable_contra = [f for f in findings_contra if f.id == "STATE_EVENT_UNREACHABLE"]
        self.assertGreaterEqual(len(unreachable_contra), 1)


if __name__ == "__main__":
    unittest.main()
