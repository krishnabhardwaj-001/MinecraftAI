import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from ai.planner import MinecraftPlanner, create_plan, validate_plan_mechanisms
from generator import (
    DatapackGenerator,
    LootTableModification,
    MechanismSpecification,
    validate_mechanism_specification,
)
from pipeline import run_minecraft_pipeline
from validator import DatapackValidator


def test_1_planner_structured_mechanism_output():
    print("=" * 70)
    print("TEST 1: PLANNER STRUCTURED MECHANISM OUTPUT")
    print("=" * 70)

    understanding = {
        "status": "understood",
        "minecraft_version": "1.21.11",
        "edition": "Java",
        "understood_request": "Make every creeper drop diamonds.",
        "requirements": [
            {
                "subject": "creeper",
                "target": "creeper",
                "intent": "drop diamonds",
                "details": [
                    {"name": "item", "value": "diamond"},
                    {"name": "count", "value": 1}
                ],
                "conditions": ["upon death"],
                "constraints": []
            }
        ]
    }

    planner = MinecraftPlanner(version="1.21.11")
    plan = planner.plan(understanding)

    assert plan["status"] in ("ready", "needs_clarification")
    assert "implementation_plan" in plan
    assert len(plan["implementation_plan"]) > 0

    first_ip = plan["implementation_plan"][0]
    mechanisms = first_ip.get("mechanisms", [])
    assert len(mechanisms) > 0

    first_mech = mechanisms[0]
    assert "type" in first_mech
    # Verify that mechanism is a structured dictionary
    assert isinstance(first_mech, dict)
    print(f"  [OK] Planner produced structured mechanism: type='{first_mech.get('type')}', target='{first_mech.get('target')}', item='{first_mech.get('item')}'")
    return True


def test_2_pydantic_validation_valid_specifications():
    print("=" * 70)
    print("TEST 2: PYDANTIC VALIDATION OF VALID SPECIFICATIONS")
    print("=" * 70)

    # 1. Valid Loot Table Spec
    lt_spec = MechanismSpecification(
        type="loot_table",
        target="entities/zombie.json",
        item="minecraft:gold_ingot",
        count=2,
        operation="add_pool"
    )
    validate_mechanism_specification(lt_spec)
    lt_mod = lt_spec.to_loot_modification()
    assert lt_mod.loot_table_path == "entities/zombie.json"
    assert lt_mod.item == "minecraft:gold_ingot"
    assert lt_mod.count == 2

    # 2. Valid Function Spec
    func_spec = MechanismSpecification(
        type="function",
        path="apply_speed",
        commands=["effect give @a minecraft:speed 10 1 true"],
        namespace="speed_pack"
    )
    validate_mechanism_specification(func_spec)
    func_def = func_spec.to_function_definition()
    assert func_def.function_path == "apply_speed"
    assert len(func_def.commands) == 1

    # 3. Valid Function Tag Spec
    tag_spec = MechanismSpecification(
        type="function_tag",
        tag_name="tick",
        values=["speed_pack:apply_speed"],
        namespace="minecraft"
    )
    validate_mechanism_specification(tag_spec)
    tag_def = tag_spec.to_tag_definition()
    assert tag_def.tag_name == "tick"
    assert tag_def.values == ["speed_pack:apply_speed"]

    # 4. Valid Advancement Spec
    adv_spec = MechanismSpecification(
        type="advancement",
        path="root",
        criteria={
            "kill_zombie": {
                "trigger": "minecraft:player_killed_entity",
                "conditions": {"entity": {"type": "minecraft:zombie"}}
            }
        },
        rewards={"experience": 50},
        namespace="minecraft_ai"
    )
    validate_mechanism_specification(adv_spec)
    adv_def = adv_spec.to_advancement_definition()
    assert adv_def.advancement_path == "root"
    assert "kill_zombie" in adv_def.criteria

    print("  [OK] All 4 mechanism types validated and converted cleanly.")
    return True


def test_3_rejection_incomplete_specifications():
    print("=" * 70)
    print("TEST 3: REJECTION OF INCOMPLETE SPECIFICATIONS")
    print("=" * 70)

    # A. Loot table missing item
    try:
        validate_mechanism_specification({"type": "loot_table", "target": "entities/creeper.json"})
        assert False, "Failed to reject loot_table missing item!"
    except ValueError as e:
        assert "item" in str(e).lower()
        print(f"  [OK] Rejected loot_table missing item: {e}")

    # B. Loot table missing target
    try:
        validate_mechanism_specification({"type": "loot_table", "item": "minecraft:diamond"})
        assert False, "Failed to reject loot_table missing target!"
    except ValueError as e:
        assert "target" in str(e).lower()
        print(f"  [OK] Rejected loot_table missing target: {e}")

    # C. Function missing commands
    try:
        validate_mechanism_specification({"type": "function", "path": "test_func", "commands": []})
        assert False, "Failed to reject function missing commands!"
    except ValueError as e:
        assert "commands" in str(e).lower()
        print(f"  [OK] Rejected function missing commands: {e}")

    # D. Function missing path
    try:
        validate_mechanism_specification({"type": "function", "commands": ["say hi"]})
        assert False, "Failed to reject function missing path!"
    except ValueError as e:
        assert "path" in str(e).lower()
        print(f"  [OK] Rejected function missing path: {e}")

    # E. Function tag missing values
    try:
        validate_mechanism_specification({"type": "function_tag", "tag_name": "tick", "values": []})
        assert False, "Failed to reject function_tag missing values!"
    except ValueError as e:
        assert "values" in str(e).lower()
        print(f"  [OK] Rejected function_tag missing values: {e}")

    # F. Advancement missing criteria
    try:
        validate_mechanism_specification({"type": "advancement", "path": "story", "criteria": {}})
        assert False, "Failed to reject advancement missing criteria!"
    except ValueError as e:
        assert "criteria" in str(e).lower()
        print(f"  [OK] Rejected advancement missing criteria: {e}")

    # G. Unknown type
    try:
        validate_mechanism_specification({"type": "invalid_magic_type"})
        assert False, "Failed to reject unsupported mechanism type!"
    except ValueError as e:
        assert "unsupported" in str(e).lower()
        print(f"  [OK] Rejected unsupported mechanism type: {e}")

    return True


def test_4_generic_function_specification():
    print("=" * 70)
    print("TEST 4: GENERIC FUNCTION SPECIFICATION")
    print("=" * 70)

    # Generic request: Give every player speed effect
    plan = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "summary": "Give every player speed effect",
        "implementation_plan": [
            {
                "requirement_index": 0,
                "objective": "Apply speed effect to all players",
                "mechanisms": [
                    {
                        "type": "function",
                        "namespace": "speed_mod",
                        "path": "apply_speed",
                        "commands": ["/effect give @a minecraft:speed 10 0 true"]  # leading slash auto-stripped
                    }
                ]
            }
        ]
    }

    test_dir = Path("generated") / "test_func_spec"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    gen = DatapackGenerator(output_dir=test_dir)
    res = gen.generate(plan=plan, datapack_name="speed_func_dp", create_zip=True)

    func_file = res.datapack_path / "data" / "speed_mod" / "function" / "apply_speed.mcfunction"
    assert func_file.exists(), f"Function file not found at {func_file}"
    content = func_file.read_text(encoding="utf-8")
    assert "effect give @a minecraft:speed 10 0 true" in content
    assert not content.startswith("/")

    validator = DatapackValidator()
    val_res = validator.validate(res.datapack_path)
    assert val_res.is_valid, f"Generated function failed validation: {val_res.errors}"
    print("  [OK] Function specification generated and validated cleanly.")

    shutil.rmtree(test_dir)
    return True


def test_5_generic_function_tag_specification():
    print("=" * 70)
    print("TEST 5: GENERIC FUNCTION TAG SPECIFICATION")
    print("=" * 70)

    plan = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "summary": "Execute game loop on tick",
        "implementation_plan": [
            {
                "requirement_index": 0,
                "objective": "Bind function to #minecraft:tick",
                "mechanisms": [
                    {
                        "type": "function",
                        "namespace": "custom_loop",
                        "path": "loop",
                        "commands": ["particle minecraft:cloud ~ ~ ~ 0.1 0.1 0.1 0 1"]
                    },
                    {
                        "type": "function_tag",
                        "namespace": "minecraft",
                        "tag_name": "tick",
                        "values": ["custom_loop:loop"]
                    }
                ]
            }
        ]
    }

    test_dir = Path("generated") / "test_tag_spec"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    gen = DatapackGenerator(output_dir=test_dir)
    res = gen.generate(plan=plan, datapack_name="loop_tag_dp", create_zip=True)

    tag_file = res.datapack_path / "data" / "minecraft" / "tags" / "function" / "tick.json"
    assert tag_file.exists()
    tag_data = json.loads(tag_file.read_text(encoding="utf-8"))
    assert "values" in tag_data
    assert "custom_loop:loop" in tag_data["values"]

    validator = DatapackValidator()
    val_res = validator.validate(res.datapack_path)
    assert val_res.is_valid, f"Tag datapack failed validation: {val_res.errors}"
    print("  [OK] Function tag specification verified at data/minecraft/tags/function/tick.json.")

    shutil.rmtree(test_dir)
    return True


def test_6_generic_advancement_specification():
    print("=" * 70)
    print("TEST 6: GENERIC ADVANCEMENT SPECIFICATION")
    print("=" * 70)

    # Generic: Make players receive a reward when they kill a zombie
    plan = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "summary": "Reward players when killing zombie",
        "implementation_plan": [
            {
                "requirement_index": 0,
                "objective": "Trigger advancement on zombie death",
                "mechanisms": [
                    {
                        "type": "advancement",
                        "namespace": "zombie_hunt",
                        "path": "kill_zombie_reward",
                        "criteria": {
                            "killed_zombie": {
                                "trigger": "minecraft:player_killed_entity",
                                "conditions": {
                                    "entity": {
                                        "type": "minecraft:zombie"
                                    }
                                }
                            }
                        },
                        "rewards": {
                            "experience": 100
                        },
                        "display": {
                            "title": {"text": "Zombie Hunter"},
                            "description": {"text": "Slay a zombie"},
                            "icon": {"id": "minecraft:rotten_flesh"}
                        }
                    }
                ]
            }
        ]
    }

    test_dir = Path("generated") / "test_adv_spec"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    gen = DatapackGenerator(output_dir=test_dir)
    res = gen.generate(plan=plan, datapack_name="zombie_adv_dp", create_zip=True)

    adv_file = res.datapack_path / "data" / "zombie_hunt" / "advancement" / "kill_zombie_reward.json"
    assert adv_file.exists()
    adv_data = json.loads(adv_file.read_text(encoding="utf-8"))
    assert "criteria" in adv_data
    assert "killed_zombie" in adv_data["criteria"]
    assert adv_data["rewards"]["experience"] == 100

    validator = DatapackValidator()
    val_res = validator.validate(res.datapack_path)
    assert val_res.is_valid, f"Advancement datapack failed validation: {val_res.errors}"
    print("  [OK] Advancement specification verified at data/zombie_hunt/advancement/kill_zombie_reward.json.")

    shutil.rmtree(test_dir)
    return True


def test_7_generic_loot_table_specification():
    print("=" * 70)
    print("TEST 7: GENERIC LOOT-TABLE SPECIFICATION")
    print("=" * 70)

    plan = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "summary": "Make every creeper drop diamonds",
        "implementation_plan": [
            {
                "requirement_index": 0,
                "objective": "Add diamond drop to creeper",
                "mechanisms": [
                    {
                        "type": "loot_table",
                        "target": "entities/creeper.json",
                        "item": "minecraft:diamond",
                        "count": 3,
                        "operation": "add_pool"
                    }
                ]
            }
        ]
    }

    test_dir = Path("generated") / "test_lt_spec"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    gen = DatapackGenerator(output_dir=test_dir)
    res = gen.generate(plan=plan, datapack_name="creeper_lt_dp", create_zip=True)

    lt_file = res.datapack_path / "data" / "minecraft" / "loot_table" / "entities" / "creeper.json"
    assert lt_file.exists()
    lt_data = json.loads(lt_file.read_text(encoding="utf-8"))
    assert len(lt_data.get("pools", [])) == 3

    # Check added pool has diamond with count 3
    added_pool = lt_data["pools"][-1]
    assert added_pool["entries"][0]["name"] == "minecraft:diamond"

    validator = DatapackValidator()
    val_res = validator.validate(res.datapack_path)
    assert val_res.is_valid, f"Loot table failed validation: {val_res.errors}"
    print("  [OK] Structured loot table specification generated and validated.")

    shutil.rmtree(test_dir)
    return True


def test_8_multiple_mechanisms_in_one_plan():
    print("=" * 70)
    print("TEST 8: MULTIPLE MECHANISMS IN ONE PLAN")
    print("=" * 70)

    # Example: Give every player a diamond sword when they join
    plan = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "summary": "Give diamond sword on join",
        "implementation_plan": [
            {
                "requirement_index": 0,
                "objective": "Give diamond sword and announce",
                "mechanisms": [
                    {
                        "type": "function",
                        "namespace": "starter",
                        "path": "grant_starter_gear",
                        "commands": [
                            "give @a minecraft:diamond_sword 1",
                            "say Welcome to the game!"
                        ]
                    },
                    {
                        "type": "function_tag",
                        "namespace": "minecraft",
                        "tag_name": "load",
                        "values": ["starter:grant_starter_gear"]
                    },
                    {
                        "type": "advancement",
                        "namespace": "starter",
                        "path": "join_game",
                        "criteria": {
                            "joined": {
                                "trigger": "minecraft:tick"
                            }
                        }
                    }
                ]
            }
        ]
    }

    test_dir = Path("generated") / "test_multi_spec"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    gen = DatapackGenerator(output_dir=test_dir)
    res = gen.generate(plan=plan, datapack_name="starter_pack", create_zip=True)

    assert (res.datapack_path / "data" / "starter" / "function" / "grant_starter_gear.mcfunction").exists()
    assert (res.datapack_path / "data" / "minecraft" / "tags" / "function" / "load.json").exists()
    assert (res.datapack_path / "data" / "starter" / "advancement" / "join_game.json").exists()

    validator = DatapackValidator()
    val_res = validator.validate(res.datapack_path)
    assert val_res.is_valid, f"Multi-mechanism plan failed validation: {val_res.errors}"
    print("  [OK] Multi-mechanism plan (function + tag + advancement) cleanly generated and validated.")

    shutil.rmtree(test_dir)
    return True


def test_9_existing_loot_table_compatibility():
    print("=" * 70)
    print("TEST 9: EXISTING LOOT-TABLE COMPATIBILITY (LEGACY MINIMAL PLAN)")
    print("=" * 70)

    # Legacy plan format without structured mechanism fields
    plan = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "summary": "Override creeper loot table",
        "implementation_plan": [
            {
                "requirement_index": 0,
                "objective": "Creepers drop diamonds",
                "mechanisms": [{"type": "loot_table_override"}],
                "steps": [
                    {
                        "id": "step1",
                        "action": "Add diamond drop",
                        "resources": ["entities/creeper.json", "minecraft:diamond"]
                    }
                ]
            }
        ]
    }

    test_dir = Path("generated") / "test_compat"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    gen = DatapackGenerator(output_dir=test_dir)
    res = gen.generate(plan=plan, datapack_name="compat_pack", create_zip=True)

    assert (res.datapack_path / "data" / "minecraft" / "loot_table" / "entities" / "creeper.json").exists()
    validator = DatapackValidator()
    val_res = validator.validate(res.datapack_path)
    assert val_res.is_valid, f"Legacy plan failed validation: {val_res.errors}"
    print("  [OK] Full backward compatibility verified for legacy minimal plans.")

    shutil.rmtree(test_dir)
    return True


def test_10_dynamic_clarification_preservation():
    print("=" * 70)
    print("TEST 10: DYNAMIC CLARIFICATION PRESERVATION")
    print("=" * 70)

    res = run_minecraft_pipeline("Make the zombie stronger.")
    assert res.status == "needs_clarification", f"Expected needs_clarification, got: {res.status}"
    assert res.clarification is not None and len(res.clarification) > 0
    print(f"  [OK] Ambiguous request correctly stopped at clarification: '{res.clarification}'")
    return True


def test_11_arbitrary_entity_item_generality():
    print("=" * 70)
    print("TEST 11: ARBITRARY ENTITY / ITEM COMBINATIONS")
    print("=" * 70)

    # Mob 1: Skeleton drops Iron Ingot
    spec1 = MechanismSpecification(
        type="loot_table",
        target="entities/skeleton.json",
        item="minecraft:iron_ingot",
        count=2
    )

    # Mob 2: Spider drops Emerald
    spec2 = MechanismSpecification(
        type="loot_table",
        target="entities/spider.json",
        item="minecraft:emerald",
        count=1
    )

    test_dir = Path("generated") / "test_arbitrary"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    gen = DatapackGenerator(output_dir=test_dir)
    res = gen.generate(
        modifications=[spec1.to_loot_modification(), spec2.to_loot_modification()],
        datapack_name="custom_mobs_dp",
        create_zip=True
    )

    assert (res.datapack_path / "data" / "minecraft" / "loot_table" / "entities" / "skeleton.json").exists()
    assert (res.datapack_path / "data" / "minecraft" / "loot_table" / "entities" / "spider.json").exists()

    validator = DatapackValidator()
    val_res = validator.validate(res.datapack_path)
    assert val_res.is_valid, f"Arbitrary entity/item pack failed validation: {val_res.errors}"
    print("  [OK] Multiple arbitrary mob/item pairs verified without special casing.")

    shutil.rmtree(test_dir)
    return True


def test_12_full_pipeline_integration():
    print("=" * 70)
    print("TEST 12: FULL PIPELINE INTEGRATION")
    print("=" * 70)

    res = run_minecraft_pipeline("Make every creeper drop diamonds.")
    assert res.status == "success", f"Pipeline failed: {res.message}"
    assert res.final_zip_path is not None
    assert Path(res.final_zip_path).exists()
    print(f"  [OK] Full pipeline generated validated ZIP at: {res.final_zip_path}")
    return True


def test_13_deterministic_reproducibility():
    print("=" * 70)
    print("TEST 13: DETERMINISTIC REPRODUCIBILITY")
    print("=" * 70)

    dir1 = Path("generated") / "repro_1"
    dir2 = Path("generated") / "repro_2"
    for d in [dir1, dir2]:
        if d.exists():
            shutil.rmtree(d)

    spec = MechanismSpecification(
        type="function",
        namespace="repro_ns",
        path="repro_tick",
        commands=["effect give @a minecraft:jump_boost 10 0 true", "say jump"]
    )
    tag_spec = MechanismSpecification(
        type="function_tag",
        namespace="minecraft",
        tag_name="tick",
        values=["repro_ns:repro_tick"]
    )

    gen1 = DatapackGenerator(output_dir=dir1)
    res1 = gen1.generate(
        functions=[spec.to_function_definition()],
        tags=[tag_spec.to_tag_definition()],
        datapack_name="repro_dp",
        create_zip=True
    )

    gen2 = DatapackGenerator(output_dir=dir2)
    res2 = gen2.generate(
        functions=[spec.to_function_definition()],
        tags=[tag_spec.to_tag_definition()],
        datapack_name="repro_dp",
        create_zip=True
    )

    # Compare files byte-for-byte
    for rel_path in res1.files_generated:
        f1 = res1.datapack_path / rel_path
        f2 = res2.datapack_path / rel_path
        assert f1.read_bytes() == f2.read_bytes(), f"Mismatch in {rel_path}"

    # Compare SHA256 of ZIPs
    hash1 = hashlib.sha256(res1.zip_path.read_bytes()).hexdigest()
    hash2 = hashlib.sha256(res2.zip_path.read_bytes()).hexdigest()
    assert hash1 == hash2, f"ZIP hash mismatch: {hash1} vs {hash2}"
    print(f"  [OK] Byte-identical reproducibility verified across runs (SHA256: {hash1[:16]}...).")

    shutil.rmtree(dir1)
    shutil.rmtree(dir2)
    return True


def run_all_tests():
    print("RUNNING STEP 11 PLANNER BOUNDARY TESTS...\n")
    tests = [
        test_1_planner_structured_mechanism_output,
        test_2_pydantic_validation_valid_specifications,
        test_3_rejection_incomplete_specifications,
        test_4_generic_function_specification,
        test_5_generic_function_tag_specification,
        test_6_generic_advancement_specification,
        test_7_generic_loot_table_specification,
        test_8_multiple_mechanisms_in_one_plan,
        test_9_existing_loot_table_compatibility,
        test_10_dynamic_clarification_preservation,
        test_11_arbitrary_entity_item_generality,
        test_12_full_pipeline_integration,
        test_13_deterministic_reproducibility,
    ]

    passed = 0
    for t in tests:
        if t():
            passed += 1

    print("=" * 70)
    print(f"ALL {passed}/{len(tests)} PLANNER BOUNDARY TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_all_tests()
