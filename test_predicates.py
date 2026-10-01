import hashlib
import json
import shutil
from pathlib import Path

from generator.datapack_generator import DatapackGenerator, generate_datapack
from generator.models import (
    AdvancementDefinition,
    FunctionDefinition,
    FunctionTagDefinition,
    LootTableModification,
    MechanismSpecification,
    PredicateDefinition,
    RecipeDefinition,
    validate_mechanism_specification,
)
from validator.datapack_validator import DatapackValidator
from ai.planner import validate_plan_mechanisms


def test_1_valid_simple_predicates():
    print("=" * 70)
    print("TEST 1: VALID SIMPLE PREDICATES (WEATHER, TIME, CHANCE)")
    print("=" * 70)

    test_dir = Path("generated") / "test_predicate_simple"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    preds = [
        PredicateDefinition(
            predicate_path="is_raining",
            condition_type="minecraft:weather_check",
            condition_params={"raining": True},
            namespace="custom_pack"
        ),
        PredicateDefinition(
            predicate_path="is_night",
            condition_type="minecraft:time_check",
            condition_params={"value": {"min": 13000, "max": 24000}},
            namespace="custom_pack"
        ),
        PredicateDefinition(
            predicate_path="twenty_five_percent",
            condition_type="minecraft:random_chance",
            condition_params={"chance": 0.25},
            namespace="custom_pack"
        ),
    ]

    gen = DatapackGenerator(output_dir=test_dir)
    res = gen.generate(
        predicates=preds,
        datapack_name="simple_preds_pack",
        create_zip=True
    )

    # Verify singular directory: data/custom_pack/predicate/
    pred_dir = res.datapack_path / "data" / "custom_pack" / "predicate"
    assert pred_dir.exists(), f"Predicates directory missing at {pred_dir}"

    rain_file = pred_dir / "is_raining.json"
    assert rain_file.exists(), f"Missing file {rain_file}"
    with open(rain_file, "r", encoding="utf-8") as f:
        rain_data = json.load(f)
    assert rain_data["condition"] == "minecraft:weather_check"
    assert rain_data["raining"] is True

    time_file = pred_dir / "is_night.json"
    assert time_file.exists(), f"Missing file {time_file}"
    with open(time_file, "r", encoding="utf-8") as f:
        time_data = json.load(f)
    assert time_data["condition"] == "minecraft:time_check"
    assert time_data["value"]["min"] == 13000

    chance_file = pred_dir / "twenty_five_percent.json"
    assert chance_file.exists(), f"Missing file {chance_file}"
    with open(chance_file, "r", encoding="utf-8") as f:
        chance_data = json.load(f)
    assert chance_data["condition"] == "minecraft:random_chance"
    assert chance_data["chance"] == 0.25

    validator = DatapackValidator()
    val_res = validator.validate(res.datapack_path)
    assert val_res.is_valid, f"Directory validation failed: {val_res.errors}"

    val_zip = validator.validate(res.zip_path)
    assert val_zip.is_valid, f"ZIP validation failed: {val_zip.errors}"

    print("  [OK] Simple predicates correctly generated and validated.")
    shutil.rmtree(test_dir)


def test_2_nested_predicates():
    print("=" * 70)
    print("TEST 2: NESTED COMPOSITE PREDICATES (ANY_OF, INVERTED, ALL_OF)")
    print("=" * 70)

    test_dir = Path("generated") / "test_predicate_nested"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    preds = [
        PredicateDefinition(
            predicate_path="composite_weather_or_chance",
            condition_type="minecraft:any_of",
            terms=[
                {
                    "condition": "minecraft:weather_check",
                    "raining": True
                },
                {
                    "condition": "minecraft:random_chance",
                    "chance": 0.5
                }
            ],
            namespace="composite_pack"
        ),
        PredicateDefinition(
            predicate_path="not_raining",
            condition_type="minecraft:inverted",
            term={
                "condition": "minecraft:weather_check",
                "raining": True
            },
            namespace="composite_pack"
        ),
        PredicateDefinition(
            predicate_path="complex_all_of",
            condition_type="minecraft:all_of",
            terms=[
                {
                    "condition": "minecraft:time_check",
                    "value": {"min": 18000, "max": 24000}
                },
                {
                    "condition": "minecraft:inverted",
                    "term": {
                        "condition": "minecraft:weather_check",
                        "thundering": True
                    }
                }
            ],
            namespace="composite_pack"
        )
    ]

    gen = DatapackGenerator(output_dir=test_dir)
    res = gen.generate(
        predicates=preds,
        datapack_name="nested_preds_pack",
        create_zip=True
    )

    pred_dir = res.datapack_path / "data" / "composite_pack" / "predicate"

    # Test any_of
    any_file = pred_dir / "composite_weather_or_chance.json"
    assert any_file.exists()
    with open(any_file, "r", encoding="utf-8") as f:
        any_data = json.load(f)
    assert any_data["condition"] == "minecraft:any_of"
    assert len(any_data["terms"]) == 2
    assert any_data["terms"][0]["condition"] == "minecraft:weather_check"
    assert any_data["terms"][1]["condition"] == "minecraft:random_chance"

    # Test inverted
    inv_file = pred_dir / "not_raining.json"
    assert inv_file.exists()
    with open(inv_file, "r", encoding="utf-8") as f:
        inv_data = json.load(f)
    assert inv_data["condition"] == "minecraft:inverted"
    assert inv_data["term"]["condition"] == "minecraft:weather_check"

    # Test all_of
    all_file = pred_dir / "complex_all_of.json"
    assert all_file.exists()
    with open(all_file, "r", encoding="utf-8") as f:
        all_data = json.load(f)
    assert all_data["condition"] == "minecraft:all_of"
    assert len(all_data["terms"]) == 2
    assert all_data["terms"][1]["condition"] == "minecraft:inverted"

    validator = DatapackValidator()
    val_res = validator.validate(res.datapack_path)
    assert val_res.is_valid, f"Directory validation failed: {val_res.errors}"

    val_zip = validator.validate(res.zip_path)
    assert val_zip.is_valid, f"ZIP validation failed: {val_zip.errors}"

    print("  [OK] Nested composite predicates correctly generated and validated.")
    shutil.rmtree(test_dir)


def test_3_deterministic_generation():
    print("=" * 70)
    print("TEST 3: DETERMINISTIC BYTE-FOR-BYTE PREDICATE GENERATION")
    print("=" * 70)

    dir1 = Path("generated") / "test_predicate_det1"
    dir2 = Path("generated") / "test_predicate_det2"
    for d in (dir1, dir2):
        if d.exists():
            shutil.rmtree(d)

    pred = PredicateDefinition(
        predicate_path="stormy_night",
        condition_type="minecraft:all_of",
        terms=[
            {"condition": "minecraft:weather_check", "thundering": True, "raining": True},
            {"condition": "minecraft:time_check", "value": {"min": 13000, "max": 24000}}
        ],
        namespace="det_pack"
    )

    gen1 = DatapackGenerator(output_dir=dir1)
    res1 = gen1.generate(predicates=[pred], datapack_name="det_pack")

    gen2 = DatapackGenerator(output_dir=dir2)
    res2 = gen2.generate(predicates=[pred], datapack_name="det_pack")

    file1 = res1.datapack_path / "data" / "det_pack" / "predicate" / "stormy_night.json"
    file2 = res2.datapack_path / "data" / "det_pack" / "predicate" / "stormy_night.json"

    bytes1 = file1.read_bytes()
    bytes2 = file2.read_bytes()

    hash1 = hashlib.sha256(bytes1).hexdigest()
    hash2 = hashlib.sha256(bytes2).hexdigest()

    assert hash1 == hash2, f"Hashes do not match: {hash1} vs {hash2}"
    assert bytes1 == bytes2, "Content bytes are not identical"

    print(f"  [OK] Predicate JSON generation is deterministic (SHA256: {hash1[:16]}...)")
    shutil.rmtree(dir1)
    shutil.rmtree(dir2)


def test_4_namespace_and_path_handling():
    print("=" * 70)
    print("TEST 4: NAMESPACE AND DEEP SUBPATH HANDLING")
    print("=" * 70)

    test_dir = Path("generated") / "test_predicate_paths"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    pred = PredicateDefinition(
        predicate_path="environment/weather/heavy_rain",
        condition_type="minecraft:weather_check",
        condition_params={"raining": True},
        namespace="my_expansion"
    )

    gen = DatapackGenerator(output_dir=test_dir)
    res = gen.generate(predicates=[pred], datapack_name="path_pack")

    expected_path = res.datapack_path / "data" / "my_expansion" / "predicate" / "environment" / "weather" / "heavy_rain.json"
    assert expected_path.exists(), f"Deep path not created at {expected_path}"

    validator = DatapackValidator()
    val_res = validator.validate(res.datapack_path)
    assert val_res.is_valid, f"Deep path validation failed: {val_res.errors}"

    print("  [OK] Deeply nested predicate subpath and custom namespace correctly handled.")
    shutil.rmtree(test_dir)


def test_5_validator_unsupported_type_and_malformed():
    print("=" * 70)
    print("TEST 5: VALIDATOR REJECTION OF UNSUPPORTED TYPES & MALFORMED PARAMS")
    print("=" * 70)

    test_dir = Path("generated") / "test_predicate_invalid"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    pack_dir = test_dir / "bad_pack"
    pred_dir = pack_dir / "data" / "minecraft_ai" / "predicate"
    pred_dir.mkdir(parents=True, exist_ok=True)

    # 1. pack.mcmeta
    with open(pack_dir / "pack.mcmeta", "w", encoding="utf-8") as f:
        json.dump({"pack": {"pack_format": 94, "description": "test"}}, f)

    # 2. Unsupported condition type
    with open(pred_dir / "bad_type.json", "w", encoding="utf-8") as f:
        json.dump({"condition": "minecraft:nonexistent_condition"}, f)

    validator = DatapackValidator()
    val_res = validator.validate(pack_dir)
    assert not val_res.is_valid, "Validator should have rejected unsupported condition type"
    err_codes = [e.code for e in val_res.errors]
    assert "UNSUPPORTED_PREDICATE_TYPE" in err_codes, f"Expected UNSUPPORTED_PREDICATE_TYPE, got {err_codes}"

    # 3. Invalid chance value (> 1.0)
    with open(pred_dir / "bad_chance.json", "w", encoding="utf-8") as f:
        json.dump({"condition": "minecraft:random_chance", "chance": 1.5}, f)

    val_res2 = validator.validate(pack_dir)
    err_codes2 = [e.code for e in val_res2.errors]
    assert "INVALID_PREDICATE_PARAM" in err_codes2, f"Expected INVALID_PREDICATE_PARAM, got {err_codes2}"

    # 4. Obsolete plural path 'predicates/'
    bad_obs_dir = pack_dir / "data" / "minecraft_ai" / "predicates"
    bad_obs_dir.mkdir(parents=True, exist_ok=True)
    with open(bad_obs_dir / "legacy.json", "w", encoding="utf-8") as f:
        json.dump({"condition": "minecraft:weather_check", "raining": True}, f)

    val_res3 = validator.validate(pack_dir)
    err_codes3 = [e.code for e in val_res3.errors]
    assert "OBSOLETE_PATH" in err_codes3, f"Expected OBSOLETE_PATH for 'predicates/', got {err_codes3}"

    print("  [OK] Validator correctly rejects unsupported condition types, bad chance ranges, and legacy plural paths.")
    shutil.rmtree(test_dir)


def test_6_validator_invalid_item_and_entity_ids():
    print("=" * 70)
    print("TEST 6: VALIDATOR REJECTION OF INVALID ITEM AND ENTITY IDS")
    print("=" * 70)

    test_dir = Path("generated") / "test_predicate_invalid_ids"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    pack_dir = test_dir / "bad_ids_pack"
    pred_dir = pack_dir / "data" / "minecraft_ai" / "predicate"
    pred_dir.mkdir(parents=True, exist_ok=True)

    with open(pack_dir / "pack.mcmeta", "w", encoding="utf-8") as f:
        json.dump({"pack": {"pack_format": 94, "description": "test"}}, f)

    # 1. Invalid item ID in match_tool
    with open(pred_dir / "bad_tool.json", "w", encoding="utf-8") as f:
        json.dump({
            "condition": "minecraft:match_tool",
            "predicate": {
                "items": ["minecraft:mythical_infinity_blade"]
            }
        }, f)

    validator = DatapackValidator()
    val_res = validator.validate(pack_dir)
    assert not val_res.is_valid
    err_codes = [e.code for e in val_res.errors]
    assert "INVALID_ITEM_ID" in err_codes, f"Expected INVALID_ITEM_ID, got {err_codes}"

    # 2. Invalid entity type in entity_properties
    with open(pred_dir / "bad_entity.json", "w", encoding="utf-8") as f:
        json.dump({
            "condition": "minecraft:entity_properties",
            "entity": "this",
            "predicate": {
                "type": "minecraft:alien_creature"
            }
        }, f)

    val_res2 = validator.validate(pack_dir)
    err_codes2 = [e.code for e in val_res2.errors]
    assert "INVALID_ENTITY_ID" in err_codes2, f"Expected INVALID_ENTITY_ID, got {err_codes2}"

    print("  [OK] Validator correctly detects and rejects invalid item and entity IDs in predicates.")
    shutil.rmtree(test_dir)


def test_7_planner_boundary_and_validation():
    print("=" * 70)
    print("TEST 7: PLANNER MECHANISM SPECIFICATION BOUNDARY & VALIDATION")
    print("=" * 70)

    # Valid specification
    valid_spec = MechanismSpecification(
        type="predicate",
        path="check_sneak",
        condition_type="minecraft:entity_properties",
        condition_params={
            "entity": "this",
            "predicate": {
                "flags": {
                    "is_sneaking": True
                }
            }
        },
        namespace="stealth_pack"
    )
    validate_mechanism_specification(valid_spec)

    pred_def = valid_spec.to_predicate_definition()
    assert isinstance(pred_def, PredicateDefinition)
    assert pred_def.predicate_path == "check_sneak"
    assert pred_def.condition_type == "minecraft:entity_properties"
    assert pred_def.namespace == "stealth_pack"

    # Incomplete specification (missing condition_type)
    bad_spec = MechanismSpecification(
        type="predicate",
        path="incomplete_pred"
    )
    try:
        validate_mechanism_specification(bad_spec)
        assert False, "Should have raised ValueError for missing condition_type"
    except ValueError as e:
        assert "condition_type" in str(e)

    # Test validate_plan_mechanisms
    plan = {
        "implementation_plan": [
            {
                "requirement_index": 0,
                "objective": "Test predicate",
                "mechanisms": [valid_spec]
            }
        ]
    }
    validate_plan_mechanisms(plan)

    print("  [OK] Planner mechanism specification model and validation boundary fully verified.")


def test_8_composite_datapack_all_mechanisms():
    print("=" * 70)
    print("TEST 8: ALL 6 MECHANISMS TOGETHER (LOOT, FUNCTION, TAG, ADV, RECIPE, PRED)")
    print("=" * 70)

    test_dir = Path("generated") / "test_all_6_mechanisms"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    res = generate_datapack(
        modifications=[
            LootTableModification(
                loot_table_path="entities/creeper.json",
                item="minecraft:emerald",
                count=1
            )
        ],
        functions=[
            FunctionDefinition(
                function_path="main",
                commands=["say All 6 mechanisms active!"]
            )
        ],
        tags=[
            FunctionTagDefinition(
                tag_name="load",
                values=["minecraft_ai:main"]
            )
        ],
        advancements=[
            AdvancementDefinition(
                advancement_path="sample_adv",
                criteria={"impossible": {"trigger": "minecraft:impossible"}}
            )
        ],
        recipes=[
            RecipeDefinition(
                recipe_path="emerald_from_dirt",
                recipe_type="crafting_shapeless",
                result_item="minecraft:emerald",
                result_count=1,
                ingredients=["minecraft:dirt"]
            )
        ],
        predicates=[
            PredicateDefinition(
                predicate_path="is_daytime",
                condition_type="minecraft:time_check",
                condition_params={"value": {"min": 1000, "max": 12000}}
            )
        ],
        datapack_name="six_mechanisms_datapack",
        output_dir=test_dir,
        create_zip=True
    )

    validator = DatapackValidator()
    val_res = validator.validate(res.datapack_path)
    assert val_res.is_valid, f"6-mechanism directory validation failed: {val_res.errors}"

    val_zip = validator.validate(res.zip_path)
    assert val_zip.is_valid, f"6-mechanism ZIP validation failed: {val_zip.errors}"

    print("  [OK] Datapack with all 6 mechanisms (including predicate) generated and passed validation cleanly.")
    shutil.rmtree(test_dir)


if __name__ == "__main__":
    test_1_valid_simple_predicates()
    test_2_nested_predicates()
    test_3_deterministic_generation()
    test_4_namespace_and_path_handling()
    test_5_validator_unsupported_type_and_malformed()
    test_6_validator_invalid_item_and_entity_ids()
    test_7_planner_boundary_and_validation()
    test_8_composite_datapack_all_mechanisms()
    print("\nALL PREDICATE TESTS PASSED!")
