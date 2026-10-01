import hashlib
import json
import shutil
import sys
from pathlib import Path

from ai.context import retrieve_minecraft_context
from generator import DatapackGenerator, LootTableModification
from validator.datapack_validator import DatapackValidator


def test_creeper_drops_diamonds():
    print("=" * 70)
    print("TEST 1: CREEPER DROPS DIAMONDS (PRIMARY TEST)")
    print("=" * 70)

    user_request = "Make every creeper drop diamonds."

    understanding = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "edition": "Java",
        "understood_request": user_request,
        "requirements": [
            {
                "subject": "creepers",
                "target": "creepers",
                "intent": "drop diamonds",
                "details": [{"name": "item", "value": "diamond"}],
                "conditions": ["upon death"],
                "constraints": []
            }
        ]
    }

    context = retrieve_minecraft_context(understanding, version="1.21.11")

    plan = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "summary": "Override the creeper entity loot table to add a diamond drop.",
        "implementation_plan": [
            {
                "requirement_index": 0,
                "objective": "All creepers should drop diamonds when they die.",
                "mechanisms": [
                    {
                        "type": "loot_table_override",
                        "description": "Override entities/creeper.json to add diamond drop."
                    }
                ],
                "steps": [],
                "constraints": [],
                "missing_knowledge": []
            }
        ]
    }

    test_output_dir = Path("generated") / "test_run"
    if test_output_dir.exists():
        shutil.rmtree(test_output_dir)

    generator = DatapackGenerator(output_dir=test_output_dir, version="1.21.11")
    result = generator.generate(
        plan=plan,
        context=context,
        understanding=understanding,
        datapack_name="creeper_diamonds_v1",
        create_zip=True
    )

    print(f"Generator status: {result.status}")
    print(f"Datapack path:   {result.datapack_path}")
    print(f"Zip path:        {result.zip_path}")
    print(f"Files generated: {result.files_generated}")

    # 1. Verify directory creation
    assert result.datapack_path.exists(), "Datapack directory was not created!"
    print("  [OK] Datapack directory exists.")

    # 2. Verify pack.mcmeta
    mcmeta_path = result.datapack_path / "pack.mcmeta"
    assert mcmeta_path.exists(), "pack.mcmeta does not exist!"
    with open(mcmeta_path, "r", encoding="utf-8") as f:
        mcmeta_data = json.load(f)
    assert mcmeta_data["pack"]["pack_format"] == 94, (
        f"pack_format expected 94, got {mcmeta_data['pack']['pack_format']}"
    )
    print(f"  [OK] pack.mcmeta exists with pack_format: {mcmeta_data['pack']['pack_format']}")

    # 3. Verify loot table path (1.21+ singular loot_table)
    loot_table_path = (
        result.datapack_path
        / "data"
        / "minecraft"
        / "loot_table"
        / "entities"
        / "creeper.json"
    )
    assert loot_table_path.exists(), (
        f"Loot table does not exist at {loot_table_path}!"
    )
    print("  [OK] Loot table exists at data/minecraft/loot_table/entities/creeper.json")

    # 4. Verify JSON content & preservation
    with open(loot_table_path, "r", encoding="utf-8") as f:
        table_data = json.load(f)

    assert table_data.get("type") == "minecraft:entity", "Loot table type mismatch!"
    assert table_data.get("random_sequence") == "minecraft:entities/creeper", (
        "random_sequence was not preserved!"
    )

    pools = table_data.get("pools", [])
    assert len(pools) == 3, f"Expected 3 pools (2 original + 1 added), found {len(pools)}"

    # Pool 0: Gunpowder preservation check
    pool_0_entries = pools[0].get("entries", [])
    assert pool_0_entries[0].get("name") == "minecraft:gunpowder", (
        "Original gunpowder drop was not preserved in pool 0!"
    )
    assert len(pool_0_entries[0].get("functions", [])) == 2, (
        "Original gunpowder functions were altered!"
    )
    print("  [OK] Original Pool 0 (gunpowder + functions) preserved.")

    # Pool 1: Music disc condition preservation check
    pool_1_conditions = pools[1].get("conditions", [])
    assert len(pool_1_conditions) == 1, "Original music disc condition altered!"
    assert pool_1_conditions[0]["predicate"]["type"] == "#minecraft:skeletons", (
        "Original skeleton attacker condition altered!"
    )
    print("  [OK] Original Pool 1 (music disc + skeleton condition) preserved.")

    # Pool 2: New Diamond drop check
    pool_2_entries = pools[2].get("entries", [])
    assert len(pool_2_entries) == 1, "Pool 2 does not have exactly 1 entry!"
    assert pool_2_entries[0].get("type") == "minecraft:item", "Pool 2 entry is not minecraft:item!"
    assert pool_2_entries[0].get("name") == "minecraft:diamond", (
        f"Expected minecraft:diamond, got {pool_2_entries[0].get('name')}"
    )
    assert pools[2].get("rolls") == 1.0, f"Expected rolls: 1.0, got {pools[2].get('rolls')}"
    print("  [OK] Newly added Pool 2 (minecraft:diamond) verified.")

    # 5. Verify ZIP
    assert result.zip_path and result.zip_path.exists(), "ZIP archive was not created!"
    print(f"  [OK] Datapack ZIP created successfully: {result.zip_path}")

    print("\nTEST 1 PASSED SUCCESSFULLY!\n")


def test_determinism():
    print("=" * 70)
    print("TEST 2: DETERMINISTIC REPRODUCIBILITY")
    print("=" * 70)

    test_output_1 = Path("generated") / "test_run_1"
    test_output_2 = Path("generated") / "test_run_2"

    for p in [test_output_1, test_output_2]:
        if p.exists():
            shutil.rmtree(p)

    mod = LootTableModification(
        loot_table_path="entities/creeper.json",
        item="minecraft:diamond",
        count=1,
        operation="add_pool"
    )

    gen1 = DatapackGenerator(output_dir=test_output_1)
    res1 = gen1.generate(
        modifications=[mod],
        datapack_name="determinism_test",
        create_zip=True
    )

    gen2 = DatapackGenerator(output_dir=test_output_2)
    res2 = gen2.generate(
        modifications=[mod],
        datapack_name="determinism_test",
        create_zip=True
    )

    # Compare JSON files byte for byte
    file1 = res1.datapack_path / "data/minecraft/loot_table/entities/creeper.json"
    file2 = res2.datapack_path / "data/minecraft/loot_table/entities/creeper.json"

    content1 = file1.read_bytes()
    content2 = file2.read_bytes()
    assert content1 == content2, "Loot table JSON output is not byte-identical across runs!"
    print("  [OK] Loot table JSON output is 100% byte-identical across multiple runs.")

    # Compare mcmeta byte for byte
    mcmeta1 = (res1.datapack_path / "pack.mcmeta").read_bytes()
    mcmeta2 = (res2.datapack_path / "pack.mcmeta").read_bytes()
    assert mcmeta1 == mcmeta2, "pack.mcmeta output is not byte-identical across runs!"
    print("  [OK] pack.mcmeta is 100% byte-identical across multiple runs.")

    # Compare zip hashes
    zip_hash1 = hashlib.sha256(res1.zip_path.read_bytes()).hexdigest()
    zip_hash2 = hashlib.sha256(res2.zip_path.read_bytes()).hexdigest()
    assert zip_hash1 == zip_hash2, "Zip archive SHA256 hashes differ across runs!"
    print(f"  [OK] Zip archive hash is byte-for-byte reproducible (SHA256: {zip_hash1[:16]}...).")

    # Clean up test runs
    shutil.rmtree(test_output_1)
    shutil.rmtree(test_output_2)

    print("\nTEST 2 PASSED SUCCESSFULLY!\n")


def test_generality_arbitrary_mob():
    print("=" * 70)
    print("TEST 3: GENERALITY TEST (SKELETON DROPS IRON)")
    print("=" * 70)

    user_request = "Skeleton drops iron"

    understanding = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "edition": "Java",
        "understood_request": user_request,
        "requirements": [
            {
                "subject": "skeleton",
                "target": "skeleton",
                "intent": "drop iron",
                "details": [{"name": "item", "value": "iron"}],
                "conditions": ["upon death"],
                "constraints": []
            }
        ]
    }

    context = retrieve_minecraft_context(understanding, version="1.21.11")

    plan = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "summary": "Override skeleton loot table to add iron drop.",
        "implementation_plan": [
            {
                "requirement_index": 0,
                "objective": "Skeletons drop iron on death.",
                "mechanisms": [{"type": "loot_table_override"}],
                "steps": [],
                "constraints": [],
                "missing_knowledge": []
            }
        ]
    }

    test_output_dir = Path("generated") / "test_run_skeleton"
    if test_output_dir.exists():
        shutil.rmtree(test_output_dir)

    generator = DatapackGenerator(output_dir=test_output_dir, version="1.21.11")
    result = generator.generate(
        plan=plan,
        context=context,
        understanding=understanding,
        datapack_name="skeleton_drops_iron",
        create_zip=True
    )

    # Verify skeleton loot table
    loot_file = (
        result.datapack_path
        / "data"
        / "minecraft"
        / "loot_table"
        / "entities"
        / "skeleton.json"
    )
    assert loot_file.exists(), "Skeleton loot table was not created!"

    with open(loot_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Skeleton original drops: arrow and bone
    original_items = []
    for p in data["pools"][:-1]:
        for e in p.get("entries", []):
            original_items.append(e.get("name"))

    assert "minecraft:arrow" in original_items, "Original arrow drop not preserved!"
    assert "minecraft:bone" in original_items, "Original bone drop not preserved!"
    print("  [OK] Original skeleton drops (arrow, bone) preserved.")

    # New item added: iron_ingot
    added_entry = data["pools"][-1]["entries"][0]
    assert added_entry.get("name") == "minecraft:iron_ingot", (
        f"Expected minecraft:iron_ingot, got {added_entry.get('name')}"
    )
    print(f"  [OK] Added drop: {added_entry.get('name')} in final pool.")

    shutil.rmtree(test_output_dir)

    print("\nTEST 3 PASSED SUCCESSFULLY!\n")


def test_multi_datapack_tag_aggregation():
    print("=" * 70)
    print("TEST 4: MULTI-DATAPACK TAG AGGREGATION & DANGLING-REFERENCE SANITIZATION")
    print("=" * 70)

    test_output_dir = Path("generated") / "tag_agg_test"
    if test_output_dir.exists():
        shutil.rmtree(test_output_dir)

    gen = DatapackGenerator(output_dir=test_output_dir)

    # Simulate two independent mechanisms contributing to #minecraft:tick
    # and one ghost reference that should be pruned by the dangling-reference sanitizer
    plan = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "summary": "Multi-mechanism aggregation and sanitization test",
        "functions": [
            {
                "function_path": "feature_a_loop",
                "commands": ["say feature A running"],
                "namespace": "feature_pack"
            },
            {
                "function_path": "feature_b_loop",
                "commands": ["say feature B running"],
                "namespace": "feature_pack"
            }
        ],
        "tags": [
            {
                "tag_name": "tick",
                "values": ["feature_pack:feature_a_loop", "feature_pack:dangling_ghost_function"],
                "namespace": "minecraft",
                "replace": False
            },
            {
                "tag_name": "tick",
                "values": ["feature_pack:feature_b_loop"],
                "namespace": "minecraft",
                "replace": False
            }
        ]
    }

    gen_res = gen.generate(
        plan=plan,
        datapack_name="tag_aggregation_pack",
        create_zip=False,
        clean=True
    )

    tick_file = gen_res.datapack_path / "data" / "minecraft" / "tags" / "function" / "tick.json"
    assert tick_file.exists(), f"Expected tick.json to exist at {tick_file}"

    data = json.loads(tick_file.read_text(encoding="utf-8"))

    # 1. Verify minimal canonical format (replace is omitted when false)
    assert "replace" not in data, f"Expected 'replace' to be omitted by default, found: {data.get('replace')}"
    print("  [OK] 'replace' omitted by default (minimal canonical format).")

    # 2. Verify non-destructive aggregation (both feature_a_loop and feature_b_loop are present)
    assert "feature_pack:feature_a_loop" in data["values"], "feature_a_loop missing from aggregated tick tag!"
    assert "feature_pack:feature_b_loop" in data["values"], "feature_b_loop missing from aggregated tick tag!"
    print("  [OK] Multi-mechanism tag values aggregated cleanly.")

    # 3. Verify dangling-reference sanitizer pruned the ghost function to prevent TagLoader drop
    assert "feature_pack:dangling_ghost_function" not in data["values"], (
        "Dangling ghost function was not pruned by sanitizer!"
    )
    print("  [OK] Dangling function reference safely pruned by sanitizer.")

    # 4. Verify the final aggregated datapack passes DatapackValidator cleanly
    validator = DatapackValidator()
    val_res = validator.validate(gen_res.datapack_path)
    assert val_res.is_valid, f"Generated datapack failed validation: {val_res.errors}"
    print("  [OK] Aggregated datapack passed DatapackValidator cleanly (0 errors).")

    shutil.rmtree(test_output_dir)
    print("\nTEST 4 PASSED SUCCESSFULLY!\n")


if __name__ == "__main__":
    try:
        test_creeper_drops_diamonds()
        test_determinism()
        test_generality_arbitrary_mob()
        test_multi_datapack_tag_aggregation()
        print("=" * 70)
        print("ALL 4 GENERATOR TESTS PASSED SUCCESSFULLY!")
        print("=" * 70)
        sys.exit(0)
    except AssertionError:
        sys.exit(1)
