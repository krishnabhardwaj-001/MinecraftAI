import io
import json
import logging
import shutil
from pathlib import Path

from pydantic import ValidationError
from ai.planner import MinecraftPlanner
from generator.datapack_generator import DatapackGenerator, generate_datapack
from generator.mechanisms.function_mech import FunctionMechanismGenerator
from generator.mechanisms.state_machine_mech import StateMachineMechanismGenerator
from generator.models import (
    ActionSpecification,
    FunctionDefinition,
    MechanismSpecification,
    validate_mechanism_specification,
)
from pipeline import run_minecraft_pipeline
from qa.analyzer import StaticSemanticAnalyzer
from validator import DatapackValidator


def test_1_action_specification_validation():
    print("=" * 70)
    print("TEST 1: ACTION SPECIFICATION VALIDATION")
    print("=" * 70)

    # 1. Effect Action - Finite duration
    eff_action = ActionSpecification(
        action_type="apply_effect",
        target="@a",
        effect="speed",
        duration=15,
        amplifier=1,
        show_particles=False
    )
    assert eff_action.action_type == "apply_effect"
    assert eff_action.target == "@a"
    assert eff_action.duration == 15

    # 1a. Effect Action - duration=30 -> accepted as integer 30
    eff_30 = ActionSpecification(action_type="apply_effect", effect="speed", duration=30)
    assert eff_30.duration == 30
    assert isinstance(eff_30.duration, int)

    # 1b. Effect Action - duration="30" -> accepted and normalized to 30
    eff_str30 = ActionSpecification(action_type="apply_effect", effect="speed", duration="30")
    assert eff_str30.duration == 30
    assert isinstance(eff_str30.duration, int)

    # 1c. Effect Action - duration="infinite" -> accepted
    eff_inf = ActionSpecification(action_type="apply_effect", effect="night_vision", duration="infinite")
    assert eff_inf.duration == "infinite"

    # 1d. Effect Action - duration="INFINITE" -> accepted/normalized appropriately
    eff_inf_upper = ActionSpecification(action_type="apply_effect", effect="night_vision", duration="INFINITE")
    assert eff_inf_upper.duration == "infinite"

    # 1e. Effect Action - duration=None -> accepted
    eff_none = ActionSpecification(action_type="apply_effect", effect="speed", duration=None)
    assert eff_none.duration is None

    # 1f. Rejections: 0, -1, "0", "-1", 30.5, 0.5, 30.0, True, "30.5", "abc", "forever", "long time"
    rejected_cases = [
        0, -1, "0", "-1",
        30.5, 0.5, 30.0, True,
        "30.5", "abc", "forever", "long time", "permanent forever"
    ]
    for bad_val in rejected_cases:
        try:
            ActionSpecification(action_type="apply_effect", effect="speed", duration=bad_val)
            assert False, f"Should have rejected invalid duration: {bad_val!r}"
        except ValidationError:
            pass

    # 2. Give Action
    give_action = ActionSpecification(
        action_type="give_item",
        target="@p",
        item="diamond",
        count=3
    )
    assert give_action.action_type == "give_item"
    assert give_action.count == 3

    # 3. Score Action
    score_action = ActionSpecification(
        action_type="set_score",
        target="#global",
        objective="rain_state",
        score_value=0
    )
    assert score_action.score_value == 0

    print("  [OK] All ActionSpecification types created, normalized, and validated cleanly.")
    return True


def test_2_deterministic_command_synthesis_effects():
    print("=" * 70)
    print("TEST 2: DETERMINISTIC COMMAND SYNTHESIS (EFFECTS)")
    print("=" * 70)

    gen = FunctionMechanismGenerator()

    # 1. Finite duration
    action_finite = ActionSpecification(
        action_type="apply_effect",
        target="@a",
        effect="speed",
        duration=20,
        amplifier=2,
        show_particles=True
    )
    cmd_finite = gen.synthesize_action(action_finite)
    assert cmd_finite == "effect give @a minecraft:speed 20 2 false", f"Got: {cmd_finite}"
    print(f"  [OK] Synthesized finite command: '{cmd_finite}'")

    # 2. Infinite duration
    action_inf = ActionSpecification(
        action_type="apply_effect",
        target="@a",
        effect="minecraft:night_vision",
        duration="infinite",
        amplifier=0,
        show_particles=False
    )
    cmd_inf = gen.synthesize_action(action_inf)
    assert cmd_inf == "effect give @a minecraft:night_vision infinite 0 true", f"Got: {cmd_inf}"
    print(f"  [OK] Synthesized infinite command: '{cmd_inf}'")

    # 3. Default (None) duration
    action_default = ActionSpecification(
        action_type="apply_effect",
        target="@a",
        effect="minecraft:speed",
        duration=None,
        amplifier=0,
        show_particles=True
    )
    cmd_default = gen.synthesize_action(action_default)
    assert cmd_default == "effect give @a minecraft:speed 30 0 false", f"Got: {cmd_default}"
    print(f"  [OK] Synthesized default (None) command: '{cmd_default}'")

    return True


def test_3_deterministic_command_synthesis_items():
    print("=" * 70)
    print("TEST 3: DETERMINISTIC COMMAND SYNTHESIS (ITEMS WITH CONTEXT)")
    print("=" * 70)

    gen = FunctionMechanismGenerator()
    action = ActionSpecification(
        action_type="give_item",
        target="@a",
        item="diamond",
        count=1
    )

    cmd = gen.synthesize_action(action)
    # Target @a automatically pairs with 'execute as @a at @s run give @s ...'
    assert cmd == "execute as @a at @s run give @s minecraft:diamond 1", f"Got: {cmd}"
    print(f"  [OK] Synthesized context-aware command: '{cmd}'")
    return True


def test_4_state_machine_deterministic_generation():
    print("=" * 70)
    print("TEST 4: STATE MACHINE DETERMINISTIC GENERATION")
    print("=" * 70)

    sm_gen = StateMachineMechanismGenerator()
    spec = MechanismSpecification(
        type="state_machine",
        objective="rain_state",
        condition_predicate="minecraft_ai:is_raining",
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

    resources = sm_gen.generate(spec)
    assert len(resources) == 5

    rel_paths = {r.relative_path: r.content for r in resources}
    assert "data/minecraft_ai/function/load.mcfunction" in rel_paths
    assert "data/minecraft_ai/function/tick.mcfunction" in rel_paths
    assert "data/minecraft_ai/function/debug.mcfunction" in rel_paths
    assert "data/minecraft/tags/function/load.json" in rel_paths
    assert "data/minecraft/tags/function/tick.json" in rel_paths

    load_content = rel_paths["data/minecraft_ai/function/load.mcfunction"]
    assert "scoreboard objectives add rain_state dummy" in load_content
    assert "scoreboard players set #global rain_state 0" in load_content

    tick_content = rel_paths["data/minecraft_ai/function/tick.mcfunction"]
    # Verify exact ordering: action check -> state latch -> reset
    assert "execute if score #global rain_state matches 0 if predicate minecraft_ai:is_raining as @a at @s run give @s minecraft:diamond 1" in tick_content
    assert "execute if predicate minecraft_ai:is_raining run scoreboard players set #global rain_state 1" in tick_content
    assert "execute unless predicate minecraft_ai:is_raining run scoreboard players set #global rain_state 0" in tick_content

    print("  [OK] State machine generated correct load/tick files and tags deterministically.")
    return True


def test_5_per_player_state_machine_generation():
    print("=" * 70)
    print("TEST 5: PER-PLAYER STATE MACHINE GENERATION")
    print("=" * 70)

    sm_gen = StateMachineMechanismGenerator()
    spec = MechanismSpecification(
        type="state_machine",
        objective="sneak_state",
        condition_predicate="minecraft_ai:is_sneaking",
        state_scope="player",
        on_enter=[
            ActionSpecification(
                action_type="apply_effect",
                target="@a",
                effect="invisibility",
                duration=5,
                amplifier=0
            )
        ]
    )

    resources = sm_gen.generate(spec)
    rel_paths = {r.relative_path: r.content for r in resources}

    tick_content = rel_paths["data/minecraft_ai/function/tick.mcfunction"]
    assert "execute as @a unless score @s sneak_state matches 0..1 run scoreboard players set @s sneak_state 0" in tick_content
    assert "execute as @a at @s if score @s sneak_state matches 0 if predicate minecraft_ai:is_sneaking run" in tick_content

    print("  [OK] Per-player state machine generated with dynamic tick initialization.")
    return True


def test_6_datapack_generator_with_structured_actions():
    print("=" * 70)
    print("TEST 6: DATAPACK GENERATOR WITH STRUCTURED ACTIONS")
    print("=" * 70)

    test_dir = Path("generated") / "test_s15_actions"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    plan = {
        "status": "ready",
        "summary": "Give speed effect via structured action",
        "implementation_plan": [
            {
                "requirement_index": 0,
                "objective": "Apply speed to all players",
                "mechanisms": [
                    {
                        "type": "function",
                        "namespace": "speed_pack",
                        "path": "speed_loop",
                        "actions": [
                            {
                                "action_type": "apply_effect",
                                "target": "@a",
                                "effect": "minecraft:speed",
                                "duration": 10,
                                "amplifier": 1,
                                "show_particles": True
                            }
                        ]
                    },
                    {
                        "type": "function_tag",
                        "namespace": "minecraft",
                        "tag_name": "tick",
                        "values": ["speed_pack:speed_loop"]
                    }
                ]
            }
        ]
    }

    gen = DatapackGenerator(output_dir=test_dir)
    res = gen.generate(plan=plan, datapack_name="speed_action_dp", create_zip=True)

    func_file = res.datapack_path / "data" / "speed_pack" / "function" / "speed_loop.mcfunction"
    assert func_file.exists()
    content = func_file.read_text(encoding="utf-8")
    assert "effect give @a minecraft:speed 10 1 false" in content

    validator = DatapackValidator()
    val_res = validator.validate(res.datapack_path)
    assert val_res.is_valid, f"Validation failed: {val_res.errors}"

    print("  [OK] Structured action compiled into validated function datapack.")
    shutil.rmtree(test_dir)
    return True


def test_7_datapack_generator_with_state_machine_and_qa():
    print("=" * 70)
    print("TEST 7: STATE MACHINE DATAPACK GENERATION & QA VERIFICATION")
    print("=" * 70)

    test_dir = Path("generated") / "test_s15_sm"
    if test_dir.exists():
        shutil.rmtree(test_dir)

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

    gen = DatapackGenerator(output_dir=test_dir)
    res = gen.generate(plan=plan, datapack_name="rain_sm_dp", create_zip=True)

    # 1. Validate structure
    validator = DatapackValidator()
    val_res = validator.validate(res.datapack_path)
    assert val_res.is_valid, f"Validation errors: {val_res.errors}"

    # 2. Run Autonomous QA review
    qa_analyzer = StaticSemanticAnalyzer()
    findings = qa_analyzer.analyze(res.datapack_path, plan=plan)
    error_findings = [f for f in findings if f.severity.value == "error"]
    assert len(error_findings) == 0, f"QA findings reported: {[f.problem for f in error_findings]}"

    print("  [OK] State machine datapack generated cleanly, passed structural validation and QA review (0 errors).")
    shutil.rmtree(test_dir)
    return True


def test_8_resource_consolidation_shared_files():
    print("=" * 70)
    print("TEST 8: RESOURCE CONSOLIDATION (SHARED FILES & TAGS)")
    print("=" * 70)

    test_dir = Path("generated") / "test_s15_consolidation"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    # Two separate mechanisms both contributing to tick function and tick tag
    plan = {
        "status": "ready",
        "summary": "Multiple mechanisms contributing to tick",
        "implementation_plan": [
            {
                "requirement_index": 0,
                "objective": "Action 1: Speed on tick",
                "mechanisms": [
                    {
                        "type": "function",
                        "namespace": "minecraft_ai",
                        "path": "tick",
                        "actions": [
                            {"action_type": "apply_effect", "target": "@a", "effect": "speed", "duration": 5, "amplifier": 0}
                        ]
                    },
                    {
                        "type": "function_tag",
                        "namespace": "minecraft",
                        "tag_name": "tick",
                        "values": ["minecraft_ai:tick"]
                    }
                ]
            },
            {
                "requirement_index": 1,
                "objective": "Action 2: Jump boost on tick",
                "mechanisms": [
                    {
                        "type": "function",
                        "namespace": "minecraft_ai",
                        "path": "tick",
                        "actions": [
                            {"action_type": "apply_effect", "target": "@a", "effect": "jump_boost", "duration": 5, "amplifier": 0}
                        ]
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

    gen = DatapackGenerator(output_dir=test_dir)
    res = gen.generate(plan=plan, datapack_name="consolidated_dp", create_zip=True)

    tick_func = res.datapack_path / "data" / "minecraft_ai" / "function" / "tick.mcfunction"
    assert tick_func.exists()
    content = tick_func.read_text(encoding="utf-8")
    assert "effect give @a minecraft:speed" in content
    assert "effect give @a minecraft:jump_boost" in content

    tick_tag = res.datapack_path / "data" / "minecraft" / "tags" / "function" / "tick.json"
    tag_data = json.loads(tick_tag.read_text(encoding="utf-8"))
    assert tag_data["values"] == ["minecraft_ai:tick"]

    print("  [OK] Shared .mcfunction and function tag JSON consolidated cleanly without clobbering.")
    shutil.rmtree(test_dir)
    return True


def test_9_raw_command_escape_hatch():
    print("=" * 70)
    print("TEST 9: RAW COMMAND ESCAPE HATCH AUDITING")
    print("=" * 70)

    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    logger = logging.getLogger("generator.mechanisms.function_mech")
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)

    try:
        gen = FunctionMechanismGenerator()
        action = ActionSpecification(
            action_type="raw_command",
            raw_command="/bossbar set minecraft:dragon_health name Dragon"
        )

        cmd = gen.synthesize_action(action)
        assert cmd == "bossbar set minecraft:dragon_health name Dragon", f"Got: {cmd}"
        assert not cmd.startswith("/")

        logs = log_stream.getvalue()
        assert "AUDIT: ActionSpecification used raw_command escape hatch" in logs, f"Audit log not found in: {logs}"
        assert "bossbar set minecraft:dragon_health name Dragon" in logs, f"Command not found in audit log: {logs}"
        print(f"  [OK] Raw command escape hatch normalized: '{cmd}'")
        print(f"  [OK] Captured audit log warning: {logs.strip()}")
    finally:
        logger.removeHandler(handler)

    return True


def test_10_function_tag_integrity_and_reload_diagnostics():
    print("=" * 70)
    print("TEST 10: FUNCTION TAG INTEGRITY & RELOAD DIAGNOSTICS")
    print("=" * 70)

    test_dir = Path("generated") / "test_s15_tag_diag"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    plan = {
        "status": "ready",
        "summary": "Give diamond once when rain starts with reload diagnostics",
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
                    },
                    # Simulate a hallucinated/dangling function tag entry from planner
                    {
                        "type": "function_tag",
                        "tag_name": "tick",
                        "namespace": "minecraft",
                        "values": ["minecraft_ai:rain_state_tick"]
                    }
                ]
            }
        ]
    }

    gen = DatapackGenerator(output_dir=test_dir)
    res = gen.generate(plan=plan, datapack_name="diag_pack", create_zip=True)

    # 1. Verify generator pruned the dangling "rain_state_tick" from tick.json
    tick_json_path = res.datapack_path / "data" / "minecraft" / "tags" / "function" / "tick.json"
    assert tick_json_path.exists(), "tick.json was not generated"
    tick_data = json.loads(tick_json_path.read_text(encoding="utf-8"))
    assert "minecraft_ai:rain_state_tick" not in tick_data["values"], "Dangling reference was not pruned!"
    assert "minecraft_ai:tick" in tick_data["values"], "Valid tick function was not registered!"

    # 2. Verify debug and diagnostic mechanisms
    load_content = (res.datapack_path / "data" / "minecraft_ai" / "function" / "load.mcfunction").read_text(encoding="utf-8")
    assert "mcai_debug" in load_content, "mcai_debug objective missing in load.mcfunction"
    assert "[LOAD OK]" in load_content, "Reload announcement missing in load.mcfunction"

    tick_content = (res.datapack_path / "data" / "minecraft_ai" / "function" / "tick.mcfunction").read_text(encoding="utf-8")
    assert "#tick_count mcai_debug 1" in tick_content, "Automatic tick counter missing in tick.mcfunction"
    assert "[TICK OK]" in tick_content, "Automatic tick execution indicator missing in tick.mcfunction"

    debug_func_path = res.datapack_path / "data" / "minecraft_ai" / "function" / "debug.mcfunction"
    assert debug_func_path.exists(), "debug.mcfunction was not generated!"
    debug_content = debug_func_path.read_text(encoding="utf-8")
    assert "[MinecraftAI Diagnostic Report]" in debug_content, "Diagnostic header missing"
    assert "NOT RUNNING! FAILURE IN TICK REGISTRATION / TAG" in debug_content, "Tick registration failure explanation missing"

    # 3. Verify DatapackValidator validates sanitized datapack cleanly
    validator = DatapackValidator()
    val_clean = validator.validate(res.datapack_path)
    assert val_clean.is_valid, f"Sanitized pack failed validation: {val_clean.errors}"

    # 4. Verify DatapackValidator REJECTS a pack with an injected dangling function tag reference
    with open(tick_json_path, "w", encoding="utf-8") as f:
        json.dump({"replace": False, "values": ["minecraft_ai:non_existent_func"]}, f)
    val_bad = validator.validate(res.datapack_path)
    assert not val_bad.is_valid, "Validator should have failed due to dangling tag reference"
    missing_tag_issues = [e for e in val_bad.errors if e.code == "MISSING_TAG_REFERENCE"]
    assert len(missing_tag_issues) > 0, "Expected MISSING_TAG_REFERENCE error code"
    print("  [OK] Validator successfully rejected dangling function tag reference with MISSING_TAG_REFERENCE.")

    shutil.rmtree(test_dir)
    print("  [OK] Function tag sanitization, reload diagnostics, and debug function verified.")
    return True


def test_11_state_machine_with_infinite_effect():
    print("=" * 70)
    print("TEST 11: STATE MACHINE WITH INFINITE EFFECT")
    print("=" * 70)

    test_dir = Path("generated") / "test_s15_infinite_effect"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    plan = {
        "status": "ready",
        "summary": "Give night vision once when night starts",
        "implementation_plan": [
            {
                "requirement_index": 0,
                "objective": "Apply infinite night vision when night starts",
                "mechanisms": [
                    {
                        "type": "predicate",
                        "namespace": "minecraft_ai",
                        "path": "is_night",
                        "condition_type": "minecraft:time_check",
                        "condition_params": {"value": {"min": 13000, "max": 23000}}
                    },
                    {
                        "type": "state_machine",
                        "namespace": "minecraft_ai",
                        "objective": "night_state",
                        "condition_predicate": "minecraft_ai:is_night",
                        "state_scope": "global",
                        "on_enter": [
                            {
                                "action_type": "apply_effect",
                                "target": "@a",
                                "effect": "minecraft:night_vision",
                                "duration": "infinite",
                                "amplifier": 0,
                                "show_particles": False
                            }
                        ]
                    }
                ]
            }
        ]
    }

    gen = DatapackGenerator(output_dir=test_dir)
    res = gen.generate(plan=plan, datapack_name="night_vision_dp", create_zip=True)

    # 1. Structural validation
    validator = DatapackValidator()
    val_res = validator.validate(res.datapack_path)
    assert val_res.is_valid, f"Validation errors: {val_res.errors}"

    # 2. Verify tick.mcfunction contains exact infinite effect command
    tick_file = res.datapack_path / "data" / "minecraft_ai" / "function" / "tick.mcfunction"
    assert tick_file.exists(), "tick.mcfunction was not generated!"
    tick_content = tick_file.read_text(encoding="utf-8")
    assert "effect give @s minecraft:night_vision infinite 0 true" in tick_content, f"Expected infinite command in tick.mcfunction, got:\n{tick_content}"

    # 3. Autonomous QA semantic analysis
    qa_analyzer = StaticSemanticAnalyzer()
    findings = qa_analyzer.analyze(res.datapack_path, plan=plan)
    error_findings = [f for f in findings if f.severity.value == "error"]
    assert len(error_findings) == 0, f"QA reported errors: {[f.problem for f in error_findings]}"

    print("  [OK] State machine with infinite effect generated, validated, and QA-verified cleanly.")
    shutil.rmtree(test_dir)
    return True


def test_12_structured_action_architectural_boundary():
    print("=" * 70)
    print("TEST 12: STRUCTURED ACTION ARCHITECTURAL BOUNDARY (NO RAW COMMAND)")
    print("=" * 70)

    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    logger = logging.getLogger("generator.mechanisms.function_mech")
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)

    try:
        gen = FunctionMechanismGenerator()
        # Normal structured effect action
        action = ActionSpecification(
            action_type="apply_effect",
            target="@a",
            effect="minecraft:night_vision",
            duration="infinite",
            amplifier=0,
            show_particles=False
        )

        cmd = gen.synthesize_action(action)
        assert cmd == "effect give @a minecraft:night_vision infinite 0 true", f"Got: {cmd}"
        assert action.raw_command is None, "Structured action should not have raw_command set"

        logs = log_stream.getvalue()
        assert "AUDIT" not in logs, f"Structured action unexpectedly triggered audit log: {logs}"
        print(f"  [OK] Normal structured action synthesized cleanly without raw_command: '{cmd}'")
        print("  [OK] Confirmed no audit warnings emitted for structured action.")
    finally:
        logger.removeHandler(handler)

    return True


def run_all_tests():
    print("RUNNING STEP 15 PLANNER -> GENERATOR BOUNDARY TESTS...\n")
    tests = [
        test_1_action_specification_validation,
        test_2_deterministic_command_synthesis_effects,
        test_3_deterministic_command_synthesis_items,
        test_4_state_machine_deterministic_generation,
        test_5_per_player_state_machine_generation,
        test_6_datapack_generator_with_structured_actions,
        test_7_datapack_generator_with_state_machine_and_qa,
        test_8_resource_consolidation_shared_files,
        test_9_raw_command_escape_hatch,
        test_10_function_tag_integrity_and_reload_diagnostics,
        test_11_state_machine_with_infinite_effect,
        test_12_structured_action_architectural_boundary,
    ]

    passed = 0
    for t in tests:
        if t():
            passed += 1

    print("=" * 70)
    print(f"ALL {passed}/{len(tests)} STEP 15 BOUNDARY TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_all_tests()
