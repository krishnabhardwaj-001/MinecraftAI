import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

from generator import (
    AdvancementDefinition,
    DatapackGenerator,
    DatapackResource,
    FunctionDefinition,
    FunctionTagDefinition,
    LootTableModification,
)
from generator.mechanisms import (
    AdvancementMechanismGenerator,
    FunctionMechanismGenerator,
    FunctionTagMechanismGenerator,
)
from validator import DatapackValidator


def test_function_mechanism():
    print("=" * 70)
    print("TEST 1: FUNCTION MECHANISM GENERATOR")
    print("=" * 70)

    gen = FunctionMechanismGenerator()
    func = FunctionDefinition(
        function_path="combat/heal_all",
        commands=[
            "/effect give @a minecraft:instant_health 1 0",  # Leading slash should be stripped
            "say Healed all players!",
            "# A comment inside function",
            "playsound minecraft:entity.player.levelup player @a"
        ],
        namespace="custom_pack",
        description="Heals all players"
    )

    resources = gen.generate(func)
    assert len(resources) == 1
    res = resources[0]
    assert res.relative_path == "data/custom_pack/function/combat/heal_all.mcfunction"
    assert res.resource_type == "function"

    # Verify leading slash was stripped
    lines = [line for line in res.content.strip().split("\n") if line and not line.startswith("#")]
    for line in lines:
        assert not line.startswith("/"), f"Leading slash was not stripped: '{line}'"

    assert "effect give @a minecraft:instant_health 1 0" in lines
    assert "say Healed all players!" in lines
    assert "playsound minecraft:entity.player.levelup player @a" in lines
    print("  [OK] Function generated with singular 1.21+ path and stripped slashes.")
    return True


def test_function_tag_mechanism():
    print("=" * 70)
    print("TEST 2: FUNCTION TAG MECHANISM GENERATOR")
    print("=" * 70)

    gen = FunctionTagMechanismGenerator()
    tag = FunctionTagDefinition(
        tag_name="tick",
        values=["custom_pack:combat/heal_all", "minecraft_ai:tick"],
        namespace="minecraft",
        replace=False
    )

    resources = gen.generate(tag)
    assert len(resources) == 1
    res = resources[0]
    assert res.relative_path == "data/minecraft/tags/function/tick.json"
    assert res.resource_type == "function_tag"

    data = json.loads(res.content)
    # Canonical minimal tag format: 'replace' is omitted when False
    assert "replace" not in data
    assert data.get("values") == ["custom_pack:combat/heal_all", "minecraft_ai:tick"]

    # Test explicit replace=True is preserved
    tag_explicit = FunctionTagDefinition(
        tag_name="custom_tag",
        values=["custom_pack:action"],
        namespace="custom_pack",
        replace=True
    )
    res_explicit = gen.generate(tag_explicit)[0]
    data_explicit = json.loads(res_explicit.content)
    assert data_explicit.get("replace") is True
    assert res_explicit.relative_path == "data/custom_pack/tags/function/custom_tag.json"

    # Test game loop tags (tick, load) route to 'minecraft' namespace even with custom pack namespace
    tag_routed = FunctionTagDefinition(
        tag_name="load",
        values=["my_pack:init"],
        namespace="my_pack",
        replace=False
    )
    res_routed = gen.generate(tag_routed)[0]
    assert res_routed.relative_path == "data/minecraft/tags/function/load.json"
    data_routed = json.loads(res_routed.content)
    assert "replace" not in data_routed
    assert data_routed.get("values") == ["my_pack:init"]

    print("  [OK] Function tag generated at data/minecraft/tags/function/tick.json with valid JSON.")
    print("  [OK] Minimal canonical format verified (replace omitted when False, included when True).")
    print("  [OK] Game-loop tag namespace routing to 'minecraft' verified.")
    return True


def test_advancement_mechanism():
    print("=" * 70)
    print("TEST 3: ADVANCEMENT MECHANISM GENERATOR")
    print("=" * 70)

    gen = AdvancementMechanismGenerator()
    adv = AdvancementDefinition(
        advancement_path="story/kill_boss",
        criteria={
            "killed_boss": {
                "trigger": "minecraft:player_killed_entity",
                "conditions": {
                    "entity": {
                        "type": "minecraft:wither"
                    }
                }
            }
        },
        rewards={
            "experience": 1000,
            "function": "custom_pack:combat/heal_all"
        },
        namespace="custom_pack",
        display={
            "icon": {"id": "minecraft:nether_star"},
            "title": {"text": "Wither Slayer"},
            "description": {"text": "Defeat the Wither"},
            "frame": "challenge"
        }
    )

    resources = gen.generate(adv)
    assert len(resources) == 1
    res = resources[0]
    assert res.relative_path == "data/custom_pack/advancement/story/kill_boss.json"
    assert res.resource_type == "advancement"

    data = json.loads(res.content)
    assert "criteria" in data
    assert "killed_boss" in data["criteria"]
    assert data.get("rewards", {}).get("experience") == 1000
    assert data.get("display", {}).get("frame") == "challenge"
    print("  [OK] Advancement generated at data/custom_pack/advancement/story/kill_boss.json.")
    return True


def test_multi_mechanism_datapack():
    print("=" * 70)
    print("TEST 4: MULTI-MECHANISM COMPOSITE DATAPACK & VALIDATION")
    print("=" * 70)

    test_dir = Path("generated") / "test_multi_mech"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    generator = DatapackGenerator(output_dir=test_dir, version="1.21.11")

    # 1. Loot modification
    mod = LootTableModification(
        loot_table_path="entities/creeper.json",
        item="minecraft:diamond",
        count=2,
        operation="add_pool"
    )

    # 2. Function
    func = FunctionDefinition(
        function_path="main_tick",
        commands=[
            "effect give @a minecraft:speed 5 0 true",
            "particle minecraft:happy_villager ~ ~1 ~ 0.5 0.5 0.5 0 5"
        ],
        namespace="speedy",
        description="Speed effect on tick"
    )

    # 3. Tick Tag
    tag = FunctionTagDefinition(
        tag_name="tick",
        values=["speedy:main_tick"],
        namespace="minecraft"
    )

    # 4. Advancement
    adv = AdvancementDefinition(
        advancement_path="got_speed",
        criteria={
            "has_speed": {
                "trigger": "minecraft:effects_changed",
                "conditions": {
                    "effects": {
                        "minecraft:speed": {}
                    }
                }
            }
        },
        namespace="speedy"
    )

    res = generator.generate(
        modifications=[mod],
        functions=[func],
        tags=[tag],
        advancements=[adv],
        datapack_name="speedy_creeper_pack",
        description="Multi-mechanism test datapack",
        create_zip=True
    )

    assert res.status == "success"
    assert (res.datapack_path / "pack.mcmeta").exists()
    assert (res.datapack_path / "data/minecraft/loot_table/entities/creeper.json").exists()
    assert (res.datapack_path / "data/speedy/function/main_tick.mcfunction").exists()
    assert (res.datapack_path / "data/minecraft/tags/function/tick.json").exists()
    assert (res.datapack_path / "data/speedy/advancement/got_speed.json").exists()
    assert res.zip_path and res.zip_path.exists()

    # Validate directory and zip
    validator = DatapackValidator()
    val_dir = validator.validate(res.datapack_path)
    assert val_dir.is_valid, f"Multi-mechanism directory failed validation: {val_dir.errors}"
    print("  [OK] Multi-mechanism directory passed all validator checks.")

    val_zip = validator.validate(res.zip_path)
    assert val_zip.is_valid, f"Multi-mechanism ZIP failed validation: {val_zip.errors}"
    print("  [OK] Multi-mechanism ZIP archive passed all validator checks.")

    # Cleanup
    shutil.rmtree(test_dir)
    return True


def test_validator_catches_invalid_mechanisms():
    print("=" * 70)
    print("TEST 5: VALIDATOR MECHANISM ERROR DETECTION")
    print("=" * 70)

    validator = DatapackValidator()

    # Case A: Leading slash in mcfunction
    with tempfile.TemporaryDirectory(prefix="val_test_slash_") as tmp:
        dp = Path(tmp)
        (dp / "pack.mcmeta").write_text('{"pack": {"pack_format": 94, "description": "test"}}\n', encoding="utf-8")
        func_dir = dp / "data" / "test" / "function"
        func_dir.mkdir(parents=True)
        (func_dir / "bad.mcfunction").write_text("/say this has a leading slash\n", encoding="utf-8")

        res = validator.validate(dp)
        assert not res.is_valid
        slash_errors = [e for e in res.errors if e.code == "LEADING_SLASH_IN_FUNCTION"]
        assert len(slash_errors) > 0, "Validator failed to flag LEADING_SLASH_IN_FUNCTION!"
        print("  [OK] Validator caught LEADING_SLASH_IN_FUNCTION.")

    # Case B: Obsolete plural functions directory
    with tempfile.TemporaryDirectory(prefix="val_test_obs_func_") as tmp:
        dp = Path(tmp)
        (dp / "pack.mcmeta").write_text('{"pack": {"pack_format": 94, "description": "test"}}\n', encoding="utf-8")
        obs_dir = dp / "data" / "test" / "functions"
        obs_dir.mkdir(parents=True)
        (obs_dir / "test.mcfunction").write_text("say hello\n", encoding="utf-8")

        res = validator.validate(dp)
        assert not res.is_valid
        obs_errors = [e for e in res.errors if e.code == "OBSOLETE_PATH"]
        assert len(obs_errors) > 0, "Validator failed to flag obsolete 'functions' directory!"
        print("  [OK] Validator caught obsolete plural 'functions' directory.")

    # Case C: Malformed tag file (missing 'values')
    with tempfile.TemporaryDirectory(prefix="val_test_bad_tag_") as tmp:
        dp = Path(tmp)
        (dp / "pack.mcmeta").write_text('{"pack": {"pack_format": 94, "description": "test"}}\n', encoding="utf-8")
        tag_dir = dp / "data" / "minecraft" / "tags" / "function"
        tag_dir.mkdir(parents=True)
        (tag_dir / "tick.json").write_text('{"replace": false}\n', encoding="utf-8")

        res = validator.validate(dp)
        assert not res.is_valid
        tag_errors = [e for e in res.errors if e.code == "MALFORMED_TAG"]
        assert len(tag_errors) > 0, "Validator failed to flag MALFORMED_TAG!"
        print("  [OK] Validator caught MALFORMED_TAG missing 'values'.")

    # Case D: Malformed advancement file (missing 'criteria')
    with tempfile.TemporaryDirectory(prefix="val_test_bad_adv_") as tmp:
        dp = Path(tmp)
        (dp / "pack.mcmeta").write_text('{"pack": {"pack_format": 94, "description": "test"}}\n', encoding="utf-8")
        adv_dir = dp / "data" / "test" / "advancement"
        adv_dir.mkdir(parents=True)
        (adv_dir / "adv.json").write_text('{"display": {"title": "Test"}}\n', encoding="utf-8")

        res = validator.validate(dp)
        assert not res.is_valid
        adv_errors = [e for e in res.errors if e.code == "MALFORMED_ADVANCEMENT"]
        assert len(adv_errors) > 0, "Validator failed to flag MALFORMED_ADVANCEMENT!"
        print("  [OK] Validator caught MALFORMED_ADVANCEMENT missing 'criteria'.")

    return True


def test_determinism_multi_mechanism():
    print("=" * 70)
    print("TEST 6: DETERMINISTIC REPRODUCIBILITY (MULTI-MECHANISM)")
    print("=" * 70)

    dir1 = Path("generated") / "det_run_1"
    dir2 = Path("generated") / "det_run_2"
    for d in [dir1, dir2]:
        if d.exists():
            shutil.rmtree(d)

    mod = LootTableModification(
        loot_table_path="entities/creeper.json",
        item="minecraft:diamond",
        count=1,
        operation="add_pool"
    )
    func = FunctionDefinition(
        function_path="loop",
        commands=["effect give @a minecraft:speed 10 0", "say tick"],
        namespace="test_ns"
    )
    tag = FunctionTagDefinition(
        tag_name="tick",
        values=["test_ns:loop"],
        namespace="minecraft"
    )

    gen1 = DatapackGenerator(output_dir=dir1)
    res1 = gen1.generate(
        modifications=[mod],
        functions=[func],
        tags=[tag],
        datapack_name="det_test",
        create_zip=True
    )

    gen2 = DatapackGenerator(output_dir=dir2)
    res2 = gen2.generate(
        modifications=[mod],
        functions=[func],
        tags=[tag],
        datapack_name="det_test",
        create_zip=True
    )

    # Compare every file byte-for-byte
    for rel_path in res1.files_generated:
        f1 = res1.datapack_path / rel_path
        f2 = res2.datapack_path / rel_path
        assert f1.exists() and f2.exists()
        assert f1.read_bytes() == f2.read_bytes(), f"File {rel_path} differed across runs!"

    # Compare ZIP hash
    hash1 = hashlib.sha256(res1.zip_path.read_bytes()).hexdigest()
    hash2 = hashlib.sha256(res2.zip_path.read_bytes()).hexdigest()
    assert hash1 == hash2, f"Zip hashes differed: {hash1} vs {hash2}"
    print(f"  [OK] Byte-identical reproducibility verified across runs (SHA256: {hash1[:16]}...).")

    # Cleanup
    shutil.rmtree(dir1)
    shutil.rmtree(dir2)
    return True


def test_generic_pipeline_effect_request():
    print("=" * 70)
    print("TEST 7: GENERIC PIPELINE REQUEST (SPEED EFFECT ON TICK)")
    print("=" * 70)

    # Test completely generic extraction without hardcoding any mob or item
    plan = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "summary": "Give speed effect continuously via tick function",
        "implementation_plan": [
            {
                "requirement_index": 0,
                "objective": "Apply speed effect to all players continuously.",
                "mechanisms": [
                    {"type": "function", "description": "Function to apply effect"},
                    {"type": "tick_tag", "description": "Tick tag to run function every tick"}
                ],
                "steps": [
                    {
                        "id": "step_1",
                        "action": "effect give @a minecraft:speed 10 1 true",
                        "resources": ["minecraft:speed", "function:tick"]
                    }
                ]
            }
        ]
    }

    test_dir = Path("generated") / "test_pipeline_effect"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    gen = DatapackGenerator(output_dir=test_dir)
    res = gen.generate(
        plan=plan,
        datapack_name="tick_speed_pack",
        create_zip=True
    )

    assert (res.datapack_path / "data/minecraft_ai/function/tick.mcfunction").exists()
    assert (res.datapack_path / "data/minecraft/tags/function/tick.json").exists()

    func_content = (res.datapack_path / "data/minecraft_ai/function/tick.mcfunction").read_text(encoding="utf-8")
    assert "effect give @a minecraft:speed 10 1 true" in func_content
    assert not func_content.startswith("/")

    tag_content = json.loads((res.datapack_path / "data/minecraft/tags/function/tick.json").read_text(encoding="utf-8"))
    assert "minecraft_ai:tick" in tag_content["values"]

    validator = DatapackValidator()
    val_res = validator.validate(res.datapack_path)
    assert val_res.is_valid, f"Generated tick effect datapack failed validation: {val_res.errors}"
    print("  [OK] Generic effect request generated and validated successfully.")

    shutil.rmtree(test_dir)
    return True


def run_all_tests():
    print("RUNNING STEP 10 MECHANISM TESTS...\n")
    tests = [
        test_function_mechanism,
        test_function_tag_mechanism,
        test_advancement_mechanism,
        test_multi_mechanism_datapack,
        test_validator_catches_invalid_mechanisms,
        test_determinism_multi_mechanism,
        test_generic_pipeline_effect_request,
    ]

    passed = 0
    for t in tests:
        if t():
            passed += 1

    print("=" * 70)
    print(f"ALL {passed}/{len(tests)} MECHANISM TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_all_tests()
