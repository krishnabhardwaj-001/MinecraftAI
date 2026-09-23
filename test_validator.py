import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from ai.context import retrieve_minecraft_context
from generator import DatapackGenerator
from validator import DatapackValidator, validate_datapack


def test_valid_creeper_datapack():
    print("=" * 70)
    print("TEST 1: VALID CREEPER -> DIAMOND DATAPACK (DIRECTORY & ZIP)")
    print("=" * 70)

    # First, ensure creeper datapack is generated
    understanding = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "edition": "Java",
        "understood_request": "Make every creeper drop diamonds.",
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
        "summary": "Override creeper loot table to add diamond drop.",
        "implementation_plan": [
            {
                "requirement_index": 0,
                "objective": "All creepers drop diamonds.",
                "mechanisms": [{"type": "loot_table_override"}]
            }
        ]
    }

    test_dir = Path("generated") / "val_test_creeper"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    gen = DatapackGenerator(output_dir=test_dir)
    gen_res = gen.generate(
        plan=plan,
        context=context,
        understanding=understanding,
        datapack_name="creeper_val_test",
        create_zip=True
    )

    validator = DatapackValidator()

    # Validate directory
    res_dir = validator.validate(gen_res.datapack_path)
    assert res_dir.is_valid, f"Expected valid directory, got: {res_dir.errors}"
    assert len(res_dir.errors) == 0
    print("  [OK] Creeper datapack directory is VALID.")

    # Validate ZIP
    assert gen_res.zip_path and gen_res.zip_path.exists()
    res_zip = validator.validate(gen_res.zip_path)
    assert res_zip.is_valid, f"Expected valid ZIP, got: {res_zip.errors}"
    assert res_zip.is_zip is True
    print("  [OK] Creeper datapack ZIP archive is VALID.")

    # Clean up
    shutil.rmtree(test_dir)
    return True


def test_invalid_json():
    print("=" * 70)
    print("TEST 2: INVALID JSON DETECTION")
    print("=" * 70)

    with tempfile.TemporaryDirectory(prefix="val_inv_json_") as temp_dir:
        dp_path = Path(temp_dir)
        mcmeta = dp_path / "pack.mcmeta"
        with open(mcmeta, "w", encoding="utf-8") as f:
            f.write('{"pack": {"pack_format": 94, "description": "test"}}\n')

        lt_path = dp_path / "data" / "minecraft" / "loot_table" / "entities" / "zombie.json"
        lt_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lt_path, "w", encoding="utf-8") as f:
            f.write('{\n  "type": "minecraft:entity",\n  "pools": [\n    BROKEN_JSON_HERE\n')

        validator = DatapackValidator()
        result = validator.validate(dp_path)

        assert not result.is_valid, "Expected invalid result for broken JSON!"
        assert any(e.code == "INVALID_JSON" for e in result.errors), (
            f"Expected INVALID_JSON error code, got: {[e.code for e in result.errors]}"
        )
        print(f"  [OK] Correctly caught invalid JSON syntax: {result.errors[0].message}")
    return True


def test_missing_mcmeta():
    print("=" * 70)
    print("TEST 3: MISSING PACK.MCMETA DETECTION")
    print("=" * 70)

    with tempfile.TemporaryDirectory(prefix="val_no_mcmeta_") as temp_dir:
        dp_path = Path(temp_dir)
        data_dir = dp_path / "data"
        data_dir.mkdir()

        validator = DatapackValidator()
        result = validator.validate(dp_path)

        assert not result.is_valid, "Expected invalid result when pack.mcmeta is missing!"
        assert any(e.code == "MISSING_MCMETA" for e in result.errors)
        print(f"  [OK] Correctly caught missing pack.mcmeta: {result.errors[0].message}")
    return True


def test_wrong_pack_format():
    print("=" * 70)
    print("TEST 4: WRONG PACK FORMAT DETECTION")
    print("=" * 70)

    with tempfile.TemporaryDirectory(prefix="val_wrong_fmt_") as temp_dir:
        dp_path = Path(temp_dir)
        mcmeta = dp_path / "pack.mcmeta"
        with open(mcmeta, "w", encoding="utf-8") as f:
            # Format 48 is obsolete for 1.21.11 (expects 94)
            f.write('{"pack": {"pack_format": 48, "description": "test"}}\n')

        data_dir = dp_path / "data"
        data_dir.mkdir()

        validator = DatapackValidator()
        result = validator.validate(dp_path)

        assert not result.is_valid, "Expected invalid result for wrong pack_format!"
        assert any(e.code == "INVALID_PACK_FORMAT" for e in result.errors)
        print(f"  [OK] Correctly caught incompatible pack format: {result.errors[0].message}")
    return True


def test_invalid_item_id():
    print("=" * 70)
    print("TEST 5: INVALID MINECRAFT ITEM ID DETECTION")
    print("=" * 70)

    with tempfile.TemporaryDirectory(prefix="val_bad_item_") as temp_dir:
        dp_path = Path(temp_dir)
        mcmeta = dp_path / "pack.mcmeta"
        with open(mcmeta, "w", encoding="utf-8") as f:
            f.write('{"pack": {"pack_format": 94, "description": "test"}}\n')

        lt_path = dp_path / "data" / "minecraft" / "loot_table" / "entities" / "zombie.json"
        lt_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lt_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "type": "minecraft:entity",
                    "pools": [
                        {
                            "rolls": 1,
                            "entries": [
                                {
                                    "type": "minecraft:item",
                                    "name": "minecraft:totally_fake_item_xyz_999"
                                }
                            ]
                        }
                    ]
                },
                f,
                indent=2
            )

        validator = DatapackValidator()
        result = validator.validate(dp_path)

        assert not result.is_valid, "Expected invalid result for unrecognized item ID!"
        assert any(e.code == "INVALID_ITEM_ID" for e in result.errors)
        print(f"  [OK] Correctly caught unrecognized item ID: {result.errors[0].message}")
    return True


def test_malformed_loot_table():
    print("=" * 70)
    print("TEST 6: MALFORMED LOOT TABLE STRUCTURE DETECTION")
    print("=" * 70)

    with tempfile.TemporaryDirectory(prefix="val_malformed_lt_") as temp_dir:
        dp_path = Path(temp_dir)
        mcmeta = dp_path / "pack.mcmeta"
        with open(mcmeta, "w", encoding="utf-8") as f:
            f.write('{"pack": {"pack_format": 94, "description": "test"}}\n')

        lt_path = dp_path / "data" / "minecraft" / "loot_table" / "entities" / "pig.json"
        lt_path.parent.mkdir(parents=True, exist_ok=True)
        # Missing 'rolls' and entries is not a list
        with open(lt_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "type": "minecraft:entity",
                    "pools": [
                        {
                            "entries": "not_a_list"
                        }
                    ]
                },
                f,
                indent=2
            )

        validator = DatapackValidator()
        result = validator.validate(dp_path)

        assert not result.is_valid, "Expected invalid result for malformed loot table!"
        assert any(e.code == "MALFORMED_LOOT_TABLE" for e in result.errors)
        print(f"  [OK] Correctly caught malformed loot table schema: {result.errors[0].message}")
    return True


def test_unsafe_zip_path():
    print("=" * 70)
    print("TEST 7: UNSAFE ZIP PATH DETECTION (PATH TRAVERSAL GUARD)")
    print("=" * 70)

    with tempfile.TemporaryDirectory(prefix="val_unsafe_zip_") as temp_dir:
        zip_path = Path(temp_dir) / "malicious.zip"

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("pack.mcmeta", '{"pack": {"pack_format": 94, "description": "evil"}}\n')
            zf.writestr("data/minecraft/loot_table/entities/creeper.json", "{}\n")
            # Inject unsafe path traversal
            zf.writestr("../../../evil_exploit.txt", "exploit contents")

        validator = DatapackValidator()
        result = validator.validate(zip_path)

        assert not result.is_valid, "Expected invalid result for zip path traversal!"
        assert any(e.code == "UNSAFE_PATH" for e in result.errors)
        print(f"  [OK] Blocked unsafe path in ZIP archive: {result.errors[0].message}")
    return True


def test_valid_skeleton_datapack():
    print("=" * 70)
    print("TEST 8: VALID SKELETON -> IRON DATAPACK")
    print("=" * 70)

    understanding = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "edition": "Java",
        "understood_request": "Skeleton drops iron",
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
        "summary": "Override skeleton loot table to add iron ingot drop.",
        "implementation_plan": [
            {
                "requirement_index": 0,
                "objective": "Skeletons drop iron on death.",
                "mechanisms": [{"type": "loot_table_override"}]
            }
        ]
    }

    test_dir = Path("generated") / "val_test_skel"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    gen = DatapackGenerator(output_dir=test_dir)
    gen_res = gen.generate(
        plan=plan,
        context=context,
        understanding=understanding,
        datapack_name="skeleton_val_test",
        create_zip=True
    )

    validator = DatapackValidator()
    result = validator.validate(gen_res.datapack_path)

    assert result.is_valid, f"Expected valid skeleton datapack, got errors: {result.errors}"
    print("  [OK] Skeleton -> iron datapack validated successfully.")

    shutil.rmtree(test_dir)
    return True


def test_obsolete_plural_path():
    print("=" * 70)
    print("TEST 9: OBSOLETE 1.20- PLURAL 'loot_tables' PATH DETECTION")
    print("=" * 70)

    with tempfile.TemporaryDirectory(prefix="val_obsolete_") as temp_dir:
        dp_path = Path(temp_dir)
        mcmeta = dp_path / "pack.mcmeta"
        with open(mcmeta, "w", encoding="utf-8") as f:
            f.write('{"pack": {"pack_format": 94, "description": "test"}}\n')

        # Create obsolete plural loot_tables directory
        obsolete_path = dp_path / "data" / "minecraft" / "loot_tables" / "entities" / "zombie.json"
        obsolete_path.parent.mkdir(parents=True, exist_ok=True)
        with open(obsolete_path, "w", encoding="utf-8") as f:
            f.write('{"type": "minecraft:entity", "pools": []}\n')

        validator = DatapackValidator()
        result = validator.validate(dp_path)

        assert not result.is_valid, "Expected invalid result for legacy plural 'loot_tables' path!"
        assert any(e.code == "OBSOLETE_PATH" for e in result.errors)
        print(f"  [OK] Correctly caught obsolete 1.20 path convention: {result.errors[0].message}")
    return True


def test_function_tag_validation():
    print("=" * 70)
    print("TEST 10: FUNCTION TAG SCHEMA & REFERENCE VALIDATION")
    print("=" * 70)

    with tempfile.TemporaryDirectory(prefix="val_tag_") as temp_dir:
        dp_path = Path(temp_dir)
        mcmeta = dp_path / "pack.mcmeta"
        with open(mcmeta, "w", encoding="utf-8") as f:
            f.write('{"pack": {"pack_format": 94, "description": "tag test"}}\n')

        # 1. Valid function on disk
        fn_path = dp_path / "data" / "test_pack" / "function" / "tick.mcfunction"
        fn_path.parent.mkdir(parents=True, exist_ok=True)
        fn_path.write_text("say ticking\n", encoding="utf-8")

        # 2. Case A: Minimal canonical format (no replace field)
        tag_path = dp_path / "data" / "minecraft" / "tags" / "function" / "tick.json"
        tag_path.parent.mkdir(parents=True, exist_ok=True)
        tag_path.write_text(json.dumps({"values": ["test_pack:tick"]}), encoding="utf-8")

        validator = DatapackValidator()
        res_a = validator.validate(dp_path)
        assert res_a.is_valid, f"Expected minimal tag format to be valid, got errors: {res_a.errors}"
        print("  [OK] Minimal canonical tag format (omitting replace) passed validation cleanly.")

        # 3. Case B: Explicit 'replace': false is valid Minecraft syntax (do NOT error)
        tag_path.write_text(json.dumps({"replace": False, "values": ["test_pack:tick"]}), encoding="utf-8")
        res_b = validator.validate(dp_path)
        assert res_b.is_valid, f"Expected 'replace': false to be recognized as valid, got: {res_b.errors}"
        print("  [OK] Explicit 'replace': false recognized as valid syntax without error.")

        # 4. Case C: Invalid non-boolean 'replace'
        tag_path.write_text(json.dumps({"replace": "invalid_string", "values": ["test_pack:tick"]}), encoding="utf-8")
        res_c = validator.validate(dp_path)
        assert not res_c.is_valid, "Expected non-boolean replace to fail validation!"
        assert any(e.code == "MALFORMED_TAG" for e in res_c.errors)
        print("  [OK] Non-boolean 'replace' correctly flagged with MALFORMED_TAG.")

        # 5. Case D: Misplaced game-loop tag under custom namespace
        tag_path.unlink()
        misplaced_tag = dp_path / "data" / "test_pack" / "tags" / "function" / "tick.json"
        misplaced_tag.parent.mkdir(parents=True, exist_ok=True)
        misplaced_tag.write_text(json.dumps({"values": ["test_pack:tick"]}), encoding="utf-8")
        res_d = validator.validate(dp_path)
        assert any(w.code == "MISPLACED_GAME_LOOP_TAG" for w in res_d.warnings)
        print("  [OK] Misplaced game-loop tag under custom namespace caught with MISPLACED_GAME_LOOP_TAG warning.")

        # 6. Case E: Missing function reference (all-or-nothing TagLoader drop risk)
        misplaced_tag.unlink()
        tag_path.write_text(json.dumps({"values": ["test_pack:non_existent_function"]}), encoding="utf-8")
        res_e = validator.validate(dp_path)
        assert not res_e.is_valid, "Expected missing tag reference to fail validation!"
        assert any(e.code == "MISSING_TAG_REFERENCE" for e in res_e.errors)
        print("  [OK] Missing tag reference correctly flagged with MISSING_TAG_REFERENCE.")

    return True


if __name__ == "__main__":
    t1 = test_valid_creeper_datapack()
    t2 = test_invalid_json()
    t3 = test_missing_mcmeta()
    t4 = test_wrong_pack_format()
    t5 = test_invalid_item_id()
    t6 = test_malformed_loot_table()
    t7 = test_unsafe_zip_path()
    t8 = test_valid_skeleton_datapack()
    t9 = test_obsolete_plural_path()
    t10 = test_function_tag_validation()

    if all([t1, t2, t3, t4, t5, t6, t7, t8, t9, t10]):
        print("=" * 70)
        print("ALL 10 VALIDATOR TESTS PASSED SUCCESSFULLY!")
        print("=" * 70)
        sys.exit(0)
    else:
        sys.exit(1)
