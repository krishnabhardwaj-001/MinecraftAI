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
    RecipeDefinition,
    validate_mechanism_specification,
)
from validator.datapack_validator import DatapackValidator


def test_1_shaped_crafting_recipe():
    print("=" * 70)
    print("TEST 1: SHAPED CRAFTING RECIPE GENERATION & VALIDATION")
    print("=" * 70)

    test_dir = Path("generated") / "test_recipe_shaped"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    recipe = RecipeDefinition(
        recipe_path="custom_saddle",
        recipe_type="crafting_shaped",
        result_item="minecraft:saddle",
        result_count=1,
        pattern=[
            "LLL",
            "I I"
        ],
        key={
            "L": "minecraft:leather",
            "I": "minecraft:iron_ingot"
        },
        category="equipment",
        namespace="crafting_pack"
    )

    gen = DatapackGenerator(output_dir=test_dir)
    res = gen.generate(
        recipes=[recipe],
        datapack_name="saddle_datapack",
        create_zip=True
    )

    recipe_file = res.datapack_path / "data" / "crafting_pack" / "recipe" / "custom_saddle.json"
    assert recipe_file.exists(), f"Recipe file missing at {recipe_file}"

    with open(recipe_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["type"] == "minecraft:crafting_shaped"
    assert data["category"] == "equipment"
    assert data["pattern"] == ["LLL", "I I"]
    assert data["key"]["L"] == "minecraft:leather"
    assert data["key"]["I"] == "minecraft:iron_ingot"
    # 1.21.11 result format check
    assert data["result"]["id"] == "minecraft:saddle"
    assert data["result"]["count"] == 1

    validator = DatapackValidator()
    val_res = validator.validate(res.datapack_path)
    assert val_res.is_valid, f"Validation failed: {val_res.errors}"

    val_zip = validator.validate(res.zip_path)
    assert val_zip.is_valid, f"ZIP validation failed: {val_zip.errors}"

    print("  [OK] Shaped recipe correctly generated with 1.21+ result.id syntax and validated.")
    shutil.rmtree(test_dir)


def test_2_shapeless_crafting_recipe():
    print("=" * 70)
    print("TEST 2: SHAPELESS CRAFTING RECIPE GENERATION & VALIDATION")
    print("=" * 70)

    test_dir = Path("generated") / "test_recipe_shapeless"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    recipe = RecipeDefinition(
        recipe_path="diamond_from_dirt",
        recipe_type="crafting_shapeless",
        result_item="minecraft:diamond",
        result_count=1,
        ingredients=["minecraft:dirt"],
        category="misc",
        namespace="alchemy"
    )

    gen = DatapackGenerator(output_dir=test_dir)
    res = gen.generate(
        recipes=[recipe],
        datapack_name="alchemy_pack",
        create_zip=True
    )

    recipe_file = res.datapack_path / "data" / "alchemy" / "recipe" / "diamond_from_dirt.json"
    assert recipe_file.exists(), f"Recipe file missing at {recipe_file}"

    with open(recipe_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["type"] == "minecraft:crafting_shapeless"
    assert data["ingredients"] == ["minecraft:dirt"]
    assert data["result"]["id"] == "minecraft:diamond"
    assert data["result"]["count"] == 1

    validator = DatapackValidator()
    val_res = validator.validate(res.datapack_path)
    assert val_res.is_valid, f"Validation failed: {val_res.errors}"

    print("  [OK] Shapeless recipe correctly generated and validated.")
    shutil.rmtree(test_dir)


def test_3_smelting_recipe():
    print("=" * 70)
    print("TEST 3: SMELTING RECIPE GENERATION & VALIDATION")
    print("=" * 70)

    test_dir = Path("generated") / "test_recipe_smelting"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    recipe = RecipeDefinition(
        recipe_path="leather_from_rotten_flesh",
        recipe_type="smelting",
        result_item="minecraft:leather",
        result_count=1,
        ingredients=["minecraft:rotten_flesh"],
        experience=0.35,
        cooking_time=200,
        category="misc",
        namespace="survival"
    )

    gen = DatapackGenerator(output_dir=test_dir)
    res = gen.generate(
        recipes=[recipe],
        datapack_name="survival_pack",
        create_zip=True
    )

    recipe_file = res.datapack_path / "data" / "survival" / "recipe" / "leather_from_rotten_flesh.json"
    assert recipe_file.exists(), f"Recipe file missing at {recipe_file}"

    with open(recipe_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["type"] == "minecraft:smelting"
    assert data["ingredient"] == "minecraft:rotten_flesh"
    assert data["result"]["id"] == "minecraft:leather"
    assert data["experience"] == 0.35
    assert data["cookingtime"] == 200

    validator = DatapackValidator()
    val_res = validator.validate(res.datapack_path)
    assert val_res.is_valid, f"Validation failed: {val_res.errors}"

    print("  [OK] Smelting recipe correctly generated with cookingtime/experience and validated.")
    shutil.rmtree(test_dir)


def test_4_blasting_and_smoking_recipes():
    print("=" * 70)
    print("TEST 4: BLASTING & SMOKING RECIPES")
    print("=" * 70)

    test_dir = Path("generated") / "test_recipe_furnace_types"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    blast_rec = RecipeDefinition(
        recipe_path="fast_iron",
        recipe_type="blasting",
        result_item="minecraft:iron_ingot",
        ingredients=["minecraft:raw_iron"],
        cooking_time=100,
        experience=0.7,
        namespace="fast_smelt"
    )

    smoke_rec = RecipeDefinition(
        recipe_path="fast_beef",
        recipe_type="smoking",
        result_item="minecraft:cooked_beef",
        ingredients=["minecraft:beef"],
        cooking_time=100,
        experience=0.35,
        namespace="fast_smelt"
    )

    gen = DatapackGenerator(output_dir=test_dir)
    res = gen.generate(
        recipes=[blast_rec, smoke_rec],
        datapack_name="fast_smelt_pack",
        create_zip=True
    )

    validator = DatapackValidator()
    val_res = validator.validate(res.datapack_path)
    assert val_res.is_valid, f"Validation failed: {val_res.errors}"

    print("  [OK] Blasting and smoking recipes verified.")
    shutil.rmtree(test_dir)


def test_5_validator_catches_invalid_item_id():
    print("=" * 70)
    print("TEST 5: VALIDATOR REJECTION OF INVALID ITEM ID IN RECIPE")
    print("=" * 70)

    test_dir = Path("generated") / "test_recipe_invalid_item"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    # Recipe with completely fake item
    recipe = RecipeDefinition(
        recipe_path="bad_recipe",
        recipe_type="crafting_shapeless",
        result_item="minecraft:totally_fake_nonexistent_item_9999",
        ingredients=["minecraft:dirt"],
        namespace="test_bad"
    )

    gen = DatapackGenerator(output_dir=test_dir)
    res = gen.generate(
        recipes=[recipe],
        datapack_name="bad_item_pack",
        create_zip=False
    )

    validator = DatapackValidator()
    val_res = validator.validate(res.datapack_path)
    assert not val_res.is_valid
    codes = [e.code for e in val_res.errors]
    assert "INVALID_ITEM_ID" in codes, f"Expected INVALID_ITEM_ID, got: {codes}"

    print(f"  [OK] Validator caught invalid item ID: {val_res.errors[0].message}")
    shutil.rmtree(test_dir)


def test_6_validator_catches_obsolete_recipes_plural_directory():
    print("=" * 70)
    print("TEST 6: VALIDATOR REJECTION OF OBSOLETE 'recipes/' PLURAL DIRECTORY")
    print("=" * 70)

    test_dir = Path("generated") / "test_obsolete_recipes_dir"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    # Manually create pack with legacy plural recipes directory
    bad_dir = test_dir / "bad_pack"
    bad_recipes = bad_dir / "data" / "minecraft" / "recipes"
    bad_recipes.mkdir(parents=True, exist_ok=True)

    mcmeta = {
        "pack": {
            "pack_format": 94,
            "description": "Obsolete recipes path test"
        }
    }
    with open(bad_dir / "pack.mcmeta", "w", encoding="utf-8") as f:
        json.dump(mcmeta, f)

    with open(bad_recipes / "test.json", "w", encoding="utf-8") as f:
        json.dump({"type": "minecraft:crafting_shapeless", "ingredients": ["minecraft:dirt"], "result": {"id": "minecraft:diamond"}}, f)

    validator = DatapackValidator()
    val_res = validator.validate(bad_dir)
    assert not val_res.is_valid
    codes = [e.code for e in val_res.errors]
    assert "OBSOLETE_PATH" in codes, f"Expected OBSOLETE_PATH in {codes}"

    obs_err = next(e for e in val_res.errors if e.code == "OBSOLETE_PATH")
    print(f"  [OK] Validator caught obsolete path: {obs_err.message}")
    shutil.rmtree(test_dir)


def test_7_validator_catches_undefined_pattern_symbol():
    print("=" * 70)
    print("TEST 7: VALIDATOR REJECTION OF UNDEFINED PATTERN SYMBOL")
    print("=" * 70)

    test_dir = Path("generated") / "test_undefined_symbol"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    dp_dir = test_dir / "unmatched_key_pack"
    rec_dir = dp_dir / "data" / "minecraft" / "recipe"
    rec_dir.mkdir(parents=True, exist_ok=True)

    mcmeta = {
        "pack": {
            "pack_format": 94,
            "description": "Unmatched key test"
        }
    }
    with open(dp_dir / "pack.mcmeta", "w", encoding="utf-8") as f:
        json.dump(mcmeta, f)

    bad_recipe = {
        "type": "minecraft:crafting_shaped",
        "pattern": ["X#"],
        "key": {
            "X": "minecraft:diamond"
            # '#' is missing!
        },
        "result": {
            "id": "minecraft:diamond_sword",
            "count": 1
        }
    }
    with open(rec_dir / "unmatched.json", "w", encoding="utf-8") as f:
        json.dump(bad_recipe, f)

    validator = DatapackValidator()
    val_res = validator.validate(dp_dir)
    assert not val_res.is_valid
    codes = [e.code for e in val_res.errors]
    assert "MALFORMED_RECIPE" in codes

    bad_err = next(e for e in val_res.errors if e.code == "MALFORMED_RECIPE")
    print(f"  [OK] Validator caught unmatched pattern symbol: {bad_err.message}")
    shutil.rmtree(test_dir)


def test_8_rejection_of_incomplete_recipe_specifications():
    print("=" * 70)
    print("TEST 8: REJECTION OF INCOMPLETE RECIPE SPECIFICATIONS")
    print("=" * 70)

    # 1. Missing result item
    try:
        spec_no_result = MechanismSpecification(
            type="recipe",
            recipe_type="crafting_shapeless",
            ingredients=["minecraft:dirt"]
        )
        validate_mechanism_specification(spec_no_result)
        assert False, "Should have rejected recipe without result_item"
    except ValueError as e:
        print(f"  [OK] Rejected recipe missing result_item: {e}")

    # 2. Shaped recipe missing pattern
    try:
        spec_no_pattern = MechanismSpecification(
            type="recipe",
            recipe_type="crafting_shaped",
            result_item="minecraft:diamond_sword",
            key={"#": "minecraft:stick"}
        )
        validate_mechanism_specification(spec_no_pattern)
        assert False, "Should have rejected shaped recipe without pattern"
    except ValueError as e:
        print(f"  [OK] Rejected shaped recipe missing pattern: {e}")

    # 3. Shaped recipe missing key
    try:
        spec_no_key = MechanismSpecification(
            type="recipe",
            recipe_type="crafting_shaped",
            result_item="minecraft:diamond_sword",
            pattern=["X", "#"]
        )
        validate_mechanism_specification(spec_no_key)
        assert False, "Should have rejected shaped recipe without key"
    except ValueError as e:
        print(f"  [OK] Rejected shaped recipe missing key: {e}")

    # 4. Shapeless recipe missing ingredients
    try:
        spec_no_ings = MechanismSpecification(
            type="recipe",
            recipe_type="crafting_shapeless",
            result_item="minecraft:diamond",
            ingredients=[]
        )
        validate_mechanism_specification(spec_no_ings)
        assert False, "Should have rejected shapeless recipe with empty ingredients"
    except ValueError as e:
        print(f"  [OK] Rejected shapeless recipe with empty ingredients: {e}")


def test_9_multi_mechanism_composite_all_five():
    print("=" * 70)
    print("TEST 9: COMPOSITE DATAPACK WITH ALL 5 MECHANISMS")
    print("=" * 70)

    test_dir = Path("generated") / "test_all_five_mechanisms"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    plan = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "summary": "Full 5-mechanism composite datapack",
        "implementation_plan": [
            {
                "requirement_index": 0,
                "objective": "Loot table modification",
                "mechanisms": [
                    {
                        "type": "loot_table",
                        "target": "entities/creeper.json",
                        "item": "minecraft:diamond",
                        "count": 2,
                        "operation": "add_pool"
                    }
                ]
            },
            {
                "requirement_index": 1,
                "objective": "Function command script",
                "mechanisms": [
                    {
                        "type": "function",
                        "namespace": "composite_mod",
                        "path": "boost",
                        "commands": ["effect give @a minecraft:speed 10 0 true"]
                    }
                ]
            },
            {
                "requirement_index": 2,
                "objective": "Function tag binding",
                "mechanisms": [
                    {
                        "type": "function_tag",
                        "namespace": "minecraft",
                        "tag_name": "tick",
                        "values": ["composite_mod:boost"]
                    }
                ]
            },
            {
                "requirement_index": 3,
                "objective": "Advancement trigger",
                "mechanisms": [
                    {
                        "type": "advancement",
                        "namespace": "composite_mod",
                        "path": "kill_boss",
                        "criteria": {
                            "kill_wither": {
                                "trigger": "minecraft:player_killed_entity",
                                "conditions": {"entity": {"type": "minecraft:wither"}}
                            }
                        },
                        "rewards": {"experience": 500}
                    }
                ]
            },
            {
                "requirement_index": 4,
                "objective": "Custom recipe",
                "mechanisms": [
                    {
                        "type": "recipe",
                        "namespace": "composite_mod",
                        "path": "netherite_upgrade",
                        "recipe_type": "crafting_shapeless",
                        "result_item": "minecraft:netherite_ingot",
                        "result_count": 1,
                        "ingredients": ["minecraft:netherite_scrap", "minecraft:gold_ingot"]
                    }
                ]
            }
        ]
    }

    gen = DatapackGenerator(output_dir=test_dir)
    res = gen.generate(
        plan=plan,
        datapack_name="all_five_datapack",
        create_zip=True
    )

    validator = DatapackValidator()
    val_dir = validator.validate(res.datapack_path)
    assert val_dir.is_valid, f"Directory validation failed: {val_dir.errors}"

    val_zip = validator.validate(res.zip_path)
    assert val_zip.is_valid, f"ZIP validation failed: {val_zip.errors}"

    # Verify all 5 resources exist
    data_dir = res.datapack_path / "data"
    assert (data_dir / "minecraft" / "loot_table" / "entities" / "creeper.json").exists()
    assert (data_dir / "composite_mod" / "function" / "boost.mcfunction").exists()
    assert (data_dir / "minecraft" / "tags" / "function" / "tick.json").exists()
    assert (data_dir / "composite_mod" / "advancement" / "kill_boss.json").exists()
    assert (data_dir / "composite_mod" / "recipe" / "netherite_upgrade.json").exists()

    print("  [OK] Composite datapack successfully generated and validated all 5 mechanisms!")
    shutil.rmtree(test_dir)


def test_10_deterministic_reproducibility():
    print("=" * 70)
    print("TEST 10: DETERMINISTIC REPRODUCIBILITY")
    print("=" * 70)

    test_dir1 = Path("generated") / "test_recipe_det_1"
    test_dir2 = Path("generated") / "test_recipe_det_2"
    for d in [test_dir1, test_dir2]:
        if d.exists():
            shutil.rmtree(d)

    recipe = RecipeDefinition(
        recipe_path="deterministic_recipe",
        recipe_type="crafting_shaped",
        result_item="minecraft:diamond_sword",
        result_count=1,
        pattern=["X", "X", "#"],
        key={"#": "minecraft:stick", "X": "minecraft:diamond"},
        namespace="repro_pack"
    )

    gen1 = DatapackGenerator(output_dir=test_dir1)
    res1 = gen1.generate(recipes=[recipe], datapack_name="repro_recipe", create_zip=True)

    gen2 = DatapackGenerator(output_dir=test_dir2)
    res2 = gen2.generate(recipes=[recipe], datapack_name="repro_recipe", create_zip=True)

    content1 = (res1.datapack_path / "data" / "repro_pack" / "recipe" / "deterministic_recipe.json").read_bytes()
    content2 = (res2.datapack_path / "data" / "repro_pack" / "recipe" / "deterministic_recipe.json").read_bytes()
    assert content1 == content2, "Recipe JSON bytes did not match!"

    zip_hash1 = hashlib.sha256(res1.zip_path.read_bytes()).hexdigest()
    zip_hash2 = hashlib.sha256(res2.zip_path.read_bytes()).hexdigest()
    assert zip_hash1 == zip_hash2, f"ZIP hashes differed: {zip_hash1} vs {zip_hash2}"

    print(f"  [OK] Byte-identical reproducibility verified across runs (SHA256: {zip_hash1[:16]}...).")
    shutil.rmtree(test_dir1)
    shutil.rmtree(test_dir2)


def test_11_arbitrary_item_generality():
    print("=" * 70)
    print("TEST 11: ARBITRARY ITEM GENERALITY")
    print("=" * 70)

    test_dir = Path("generated") / "test_arbitrary_items"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    # 3 distinct arbitrary items from 1.21.11 knowledge
    recipes = [
        RecipeDefinition(
            recipe_path="amethyst_from_copper",
            recipe_type="crafting_shapeless",
            result_item="minecraft:amethyst_shard",
            ingredients=["minecraft:copper_ingot", "minecraft:quartz"],
            namespace="fantasy"
        ),
        RecipeDefinition(
            recipe_path="echo_from_sculk",
            recipe_type="smelting",
            result_item="minecraft:echo_shard",
            ingredients=["minecraft:sculk"],
            experience=1.5,
            cooking_time=300,
            namespace="deep_dark"
        )
    ]

    gen = DatapackGenerator(output_dir=test_dir)
    res = gen.generate(recipes=recipes, datapack_name="fantasy_pack", create_zip=True)

    validator = DatapackValidator()
    val_res = validator.validate(res.datapack_path)
    assert val_res.is_valid, f"Validation failed: {val_res.errors}"

    print("  [OK] Multiple arbitrary item combinations verified cleanly.")
    shutil.rmtree(test_dir)


def test_12_planner_structured_recipe_plan():
    print("=" * 70)
    print("TEST 12: PLANNER STRUCTURED RECIPE PLAN CONSUMPTION")
    print("=" * 70)

    test_dir = Path("generated") / "test_planner_recipe"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    # Simulated plan produced by MinecraftPlanner
    plan = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "summary": "Add a custom shapeless crafting recipe to craft diamond from dirt.",
        "implementation_plan": [
            {
                "requirement_index": 0,
                "objective": "craft diamond from dirt",
                "mechanisms": [
                    {
                        "type": "recipe",
                        "namespace": "minecraft_ai",
                        "path": "diamond_from_dirt",
                        "recipe_type": "crafting_shapeless",
                        "result_item": "minecraft:diamond",
                        "result_count": 1,
                        "ingredients": ["minecraft:dirt"]
                    }
                ]
            }
        ]
    }

    gen = DatapackGenerator(output_dir=test_dir)
    res = gen.generate(plan=plan, datapack_name="dirt_to_diamond", create_zip=True)

    recipe_file = res.datapack_path / "data" / "minecraft_ai" / "recipe" / "diamond_from_dirt.json"
    assert recipe_file.exists(), f"Recipe file missing at {recipe_file}"

    validator = DatapackValidator()
    val_res = validator.validate(res.datapack_path)
    assert val_res.is_valid, f"Validation failed: {val_res.errors}"

    val_zip = validator.validate(res.zip_path)
    assert val_zip.is_valid, f"ZIP validation failed: {val_zip.errors}"

    print("  [OK] Planner recipe plan generated and validated cleanly.")
    shutil.rmtree(test_dir)


def run_all_tests():
    print("RUNNING STEP 12 RECIPE MECHANISM TESTS...\n")
    tests = [
        test_1_shaped_crafting_recipe,
        test_2_shapeless_crafting_recipe,
        test_3_smelting_recipe,
        test_4_blasting_and_smoking_recipes,
        test_5_validator_catches_invalid_item_id,
        test_6_validator_catches_obsolete_recipes_plural_directory,
        test_7_validator_catches_undefined_pattern_symbol,
        test_8_rejection_of_incomplete_recipe_specifications,
        test_9_multi_mechanism_composite_all_five,
        test_10_deterministic_reproducibility,
        test_11_arbitrary_item_generality,
        test_12_planner_structured_recipe_plan,
    ]

    passed = 0
    for t in tests:
        t()
        passed += 1

    print("\n" + "=" * 70)
    print(f"ALL {passed}/{len(tests)} RECIPE TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_all_tests()
