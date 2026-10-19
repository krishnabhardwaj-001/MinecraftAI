"""
Unit tests for B17: Generic state-machine latch initialization from condition at load time.

Verifies:
1. State-machine mechanism derives initial latch state from the active condition at load time
   (e.g., 'execute if predicate <cond> run scoreboard players set #global <obj> 1')
   so that /reload or world load while the condition is active does NOT re-trigger the action.
2. Verified on a non-rain condition (e.g. night time) to prove it is fully generic.
3. QA temporal simulation and semantic analysis pass cleanly.
"""

import tempfile
import unittest
from pathlib import Path

from generator.mechanisms.state_machine_mech import StateMachineMechanismGenerator
from generator.models import ActionSpecification, MechanismSpecification
from qa.analyzer import StaticSemanticAnalyzer
from qa.scoreboard_semantics import ScoreboardSemanticSimulator


class TestAuditB17StateLatch(unittest.TestCase):

    def test_state_machine_derives_initial_state_generically_at_load_time(self):
        """Generates state machine for night time (non-rain), verifying load-time condition derivation."""
        sm_gen = StateMachineMechanismGenerator(version="1.21.11")

        spec = MechanismSpecification(
            type="state_machine",
            namespace="custom_pack",
            objective="night_latch",
            condition_predicate="custom_pack:is_night",
            state_scope="global",
            on_enter=[
                ActionSpecification(
                    action_type="effect",
                    target="@a",
                    effect="minecraft:night_vision",
                    duration=60,
                    amplifier=0
                )
            ]
        )

        resources = sm_gen.generate(spec)
        resource_map = {r.relative_path: r.content for r in resources}

        load_path = "data/custom_pack/function/load.mcfunction"
        tick_path = "data/custom_pack/function/tick.mcfunction"

        self.assertIn(load_path, resource_map)
        self.assertIn(tick_path, resource_map)

        load_content = resource_map[load_path]
        tick_content = resource_map[tick_path]

        # 1. Verify load.mcfunction initializes objective and sets baseline to 0
        self.assertIn("scoreboard objectives add night_latch dummy", load_content)
        self.assertIn("scoreboard players set #global night_latch 0", load_content)

        # 2. Verify load.mcfunction derives active state from predicate to prevent reload re-trigger
        expected_latch_init = "execute if predicate custom_pack:is_night run scoreboard players set #global night_latch 1"
        self.assertIn(expected_latch_init, load_content)

        # 3. Verify tick.mcfunction contains transition logic
        self.assertIn("execute if score #global night_latch matches 0 if predicate custom_pack:is_night", tick_content)
        self.assertIn("execute if predicate custom_pack:is_night run scoreboard players set #global night_latch 1", tick_content)
        self.assertIn("execute unless predicate custom_pack:is_night run scoreboard players set #global night_latch 0", tick_content)

    def test_qa_temporal_simulation_passes_with_load_latch(self):
        """Validates that QA temporal simulation and semantic reviewer pass cleanly on the generic state machine."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_dir = Path(tmp_dir) / "night_pack"
            sm_gen = StateMachineMechanismGenerator(version="1.21.11")

            spec = MechanismSpecification(
                type="state_machine",
                namespace="night_ai",
                objective="night_state",
                condition_predicate="night_ai:is_night",
                state_scope="global",
                on_enter=[
                    ActionSpecification(
                        action_type="give_item",
                        target="@a",
                        item="minecraft:clock",
                        count=1
                    )
                ]
            )

            resources = sm_gen.generate(spec)

            # Write files to disk
            for res in resources:
                target_file = pack_dir / res.relative_path
                target_file.parent.mkdir(parents=True, exist_ok=True)
                target_file.write_text(res.content, encoding="utf-8")

            # Write minimal pack.mcmeta and predicate
            (pack_dir / "pack.mcmeta").write_text(
                '{"pack": {"pack_format": 94, "description": "Night State Pack"}}',
                encoding="utf-8"
            )
            pred_file = pack_dir / "data" / "night_ai" / "predicate" / "is_night.json"
            pred_file.parent.mkdir(parents=True, exist_ok=True)
            pred_file.write_text(
                '{"condition": "minecraft:time_check", "value": {"min": 13000, "max": 23000}}',
                encoding="utf-8"
            )

            # Run ScoreboardSemanticSimulator
            reviewer = ScoreboardSemanticSimulator(version="1.21.11")
            findings = reviewer.analyze_datapack(pack_dir)
            err_findings = [f for f in findings if f.severity.value == "error"]
            self.assertEqual(len(err_findings), 0, f"Unexpected QA errors in scoreboard review: {err_findings}")


if __name__ == "__main__":
    unittest.main()
