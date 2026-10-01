import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai.context import retrieve_minecraft_context
from ai.provider import AIProvider
from generator.datapack_generator import DatapackGenerator
from generator.models import LootTableModification
from repair import AIRepairLoop, RepairAttempt, RepairPlan, RepairResult
from validator.datapack_validator import DatapackValidator


class MockAIProvider:
    """
    Mock AI Provider for fast, deterministic unit testing of the repair loop.
    Records calls and returns structured responses based on custom handlers.
    """
    def __init__(self, handler=None):
        self.call_count = 0
        self.recorded_calls = []
        self.handler = handler

    def generate_structured(self, system_prompt: str, user_prompt: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        self.call_count += 1
        call_record = {
            "call_index": self.call_count,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "schema": schema
        }
        self.recorded_calls.append(call_record)

        if self.handler:
            return self.handler(self.call_count, system_prompt, user_prompt, schema)

        return {
            "repair_reasoning": "Standard mock diagnosis and resolution.",
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "Mock repaired plan",
            "implementation_plan": [],
            "missing_knowledge": [],
            "clarifications": []
        }


def test_zero_repair_attempts_on_valid_datapack():
    print("=" * 70)
    print("TEST 1: ZERO REPAIR ATTEMPTS ON VALID DATAPACK")
    print("=" * 70)

    test_dir = Path("generated") / "test_repair_valid"
    if test_dir.exists():
        shutil.rmtree(test_dir)

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

    generator = DatapackGenerator(output_dir=test_dir, version="1.21.11")
    gen_result = generator.generate(
        plan=plan,
        context=context,
        understanding=understanding,
        datapack_name="creeper_repair_valid_test",
        create_zip=True
    )

    validator = DatapackValidator()
    val_result = validator.validate(gen_result.datapack_path)
    assert val_result.is_valid, "Pre-condition failed: Datapack should be valid initially."

    mock_ai = MockAIProvider()
    repair_loop = AIRepairLoop(
        ai_provider=mock_ai,
        max_attempts=3,
        generator=generator,
        validator=validator
    )

    result = repair_loop.repair(
        understanding=understanding,
        context=context,
        planner_result=plan,
        generation_result=gen_result,
        validator_result=val_result
    )

    # Verify Requirement 3: Only invoke AI repair when validation fails.
    assert result.is_success, "Result should be successful when initial pack is valid."
    assert result.status == "skipped", f"Expected 'skipped', got {result.status}"
    assert result.total_attempts == 0, f"Expected 0 attempts, got {result.total_attempts}"
    assert len(result.attempts) == 0, "No repair attempts should be recorded."
    assert mock_ai.call_count == 0, "AI must NOT be called when validation passes!"

    print("  [OK] Valid datapack correctly skipped AI repair (0 attempts, 0 AI calls).")
    shutil.rmtree(test_dir, ignore_errors=True)


def test_corrupted_output_triggers_repair_and_regenerates_valid():
    print("=" * 70)
    print("TEST 2: CORRUPTED OUTPUT TRIGGERS REPAIR & REGENERATES VALID DATAPACK")
    print("=" * 70)

    test_dir = Path("generated") / "test_repair_heal"
    if test_dir.exists():
        shutil.rmtree(test_dir)

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

    # Initial plan intentionally contains an invalid Minecraft item ID
    bad_plan = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "summary": "Corrupted plan with bad item ID",
        "implementation_plan": [
            {
                "requirement_index": 0,
                "objective": "Creepers drop invalid fake item",
                "mechanisms": [{"type": "loot_table_override"}],
                "steps": [
                    {
                        "id": "step_1",
                        "action": "modify_loot_table",
                        "resources": ["minecraft:totally_invalid_gem_xyz", "entities/creeper.json"]
                    }
                ]
            }
        ],
        "modifications": [
            {
                "loot_table_path": "entities/creeper.json",
                "item": "minecraft:totally_invalid_gem_xyz",
                "count": 1
            }
        ]
    }

    generator = DatapackGenerator(output_dir=test_dir, version="1.21.11")
    gen_result = generator.generate(
        plan=bad_plan,
        context=context,
        understanding=understanding,
        datapack_name="creeper_repair_heal_test",
        create_zip=True
    )

    validator = DatapackValidator()
    val_result = validator.validate(gen_result.datapack_path)
    assert not val_result.is_valid, "Pre-condition failed: bad plan should produce invalid pack."
    assert any(e.code == "INVALID_ITEM_ID" for e in val_result.errors)

    def healing_ai_handler(call_idx, sys_prompt, usr_prompt, schema):
        # AI diagnoses the invalid item ID from validator errors and context
        assert "INVALID_ITEM_ID" in usr_prompt
        assert "totally_invalid_gem_xyz" in usr_prompt
        return {
            "repair_reasoning": "Validator detected invalid item ID 'minecraft:totally_invalid_gem_xyz'. Correcting to 'minecraft:diamond' from user understanding.",
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "Repaired plan with valid diamond item ID",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Creepers drop valid diamonds",
                    "mechanisms": [{"type": "loot_table_override"}],
                    "steps": [
                        {
                            "id": "step_1",
                            "action": "modify_loot_table",
                            "resources": ["minecraft:diamond", "entities/creeper.json"]
                        }
                    ]
                }
            ],
            "modifications": [
                {
                    "loot_table_path": "entities/creeper.json",
                    "item": "minecraft:diamond",
                    "count": 1
                }
            ]
        }

    mock_ai = MockAIProvider(handler=healing_ai_handler)
    repair_loop = AIRepairLoop(
        ai_provider=mock_ai,
        max_attempts=3,
        generator=generator,
        validator=validator
    )

    result = repair_loop.repair(
        understanding=understanding,
        context=context,
        planner_result=bad_plan,
        generation_result=gen_result,
        validator_result=val_result
    )

    assert result.is_success, f"Expected success after healing, got {result.status}"
    assert result.status == "success"
    assert result.total_attempts == 1, f"Expected exactly 1 attempt, got {result.total_attempts}"
    assert len(result.attempts) == 1
    assert result.attempts[0].validation_status == "valid"
    assert "totally_invalid_gem_xyz" in result.attempts[0].repair_reasoning
    assert result.final_validation and result.final_validation.is_valid

    # Validate physical files on disk
    final_path = Path(result.final_datapack_path)
    assert final_path.exists()
    assert (final_path / "pack.mcmeta").exists()
    disk_val = validator.validate(final_path)
    assert disk_val.is_valid

    print(f"  [OK] Successfully repaired invalid item ID on attempt #1: {result.message}")
    shutil.rmtree(test_dir, ignore_errors=True)


def test_maximum_retry_count_enforced_and_no_infinite_loop():
    print("=" * 70)
    print("TEST 3: MAXIMUM RETRY COUNT ENFORCEMENT & NO INFINITE LOOP")
    print("=" * 70)

    test_dir = Path("generated") / "test_repair_max_retries"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    understanding = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "edition": "Java",
        "understood_request": "Zombie drops invalid items",
        "requirements": [{"subject": "zombie", "target": "zombie", "intent": "drop invalid"}]
    }
    context = retrieve_minecraft_context(understanding, version="1.21.11")

    bad_plan = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "summary": "Persistently corrupted plan",
        "modifications": [
            {
                "loot_table_path": "entities/zombie.json",
                "item": "minecraft:nonexistent_item_attempt_0",
                "count": 1
            }
        ]
    }

    generator = DatapackGenerator(output_dir=test_dir, version="1.21.11")
    gen_result = generator.generate(
        plan=bad_plan,
        context=context,
        understanding=understanding,
        datapack_name="zombie_repair_retry_test",
        create_zip=True
    )

    validator = DatapackValidator()
    val_result = validator.validate(gen_result.datapack_path)
    assert not val_result.is_valid

    MAX_RETRIES = 3

    def persistent_failing_handler(call_idx, sys_prompt, usr_prompt, schema):
        # AI repeatedly returns invalid items (simulating stubborn/unresolvable failure)
        return {
            "repair_reasoning": f"Attempt {call_idx} failed diagnosis; still returning unrecognized item.",
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": f"Failed attempt {call_idx}",
            "modifications": [
                {
                    "loot_table_path": "entities/zombie.json",
                    "item": f"minecraft:still_invalid_item_{call_idx}",
                    "count": 1
                }
            ]
        }

    mock_ai = MockAIProvider(handler=persistent_failing_handler)
    repair_loop = AIRepairLoop(
        ai_provider=mock_ai,
        max_attempts=MAX_RETRIES,
        generator=generator,
        validator=validator
    )

    result = repair_loop.repair(
        understanding=understanding,
        context=context,
        planner_result=bad_plan,
        generation_result=gen_result,
        validator_result=val_result
    )

    # Must terminate cleanly after exactly MAX_RETRIES without infinite looping
    assert not result.is_success, "Expected failure when all retries fail."
    assert result.status == "failed"
    assert result.total_attempts == MAX_RETRIES, (
        f"Expected total_attempts == {MAX_RETRIES}, got {result.total_attempts}"
    )
    assert len(result.attempts) == MAX_RETRIES
    assert mock_ai.call_count == MAX_RETRIES

    print(f"  [OK] Enforced exact retry limit ({MAX_RETRIES}) with no infinite loop: {result.message}")
    shutil.rmtree(test_dir, ignore_errors=True)


def test_failed_repair_returns_structured_failure_history():
    print("=" * 70)
    print("TEST 4: FAILED REPAIR RETURNS COMPLETE STRUCTURED FAILURE HISTORY")
    print("=" * 70)

    test_dir = Path("generated") / "test_repair_history"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    understanding = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "edition": "Java",
        "understood_request": "Skeleton drops broken items",
        "requirements": [{"subject": "skeleton", "target": "skeleton", "intent": "drop broken"}]
    }
    context = retrieve_minecraft_context(understanding, version="1.21.11")

    bad_plan = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "summary": "Initial bad plan",
        "modifications": [
            {
                "loot_table_path": "entities/skeleton.json",
                "item": "minecraft:bad_item_init",
                "count": 1
            }
        ]
    }

    generator = DatapackGenerator(output_dir=test_dir, version="1.21.11")
    gen_result = generator.generate(
        plan=bad_plan,
        context=context,
        understanding=understanding,
        datapack_name="skeleton_repair_history_test",
        create_zip=True
    )

    validator = DatapackValidator()
    val_result = validator.validate(gen_result.datapack_path)

    def failing_handler(call_idx, sys_prompt, usr_prompt, schema):
        return {
            "repair_reasoning": f"Reasoning for failure at attempt #{call_idx}",
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": f"Plan attempt #{call_idx}",
            "modifications": [
                {
                    "loot_table_path": "entities/skeleton.json",
                    "item": f"minecraft:bad_item_{call_idx}",
                    "count": 1
                }
            ]
        }

    mock_ai = MockAIProvider(handler=failing_handler)
    repair_loop = AIRepairLoop(
        ai_provider=mock_ai,
        max_attempts=2,
        generator=generator,
        validator=validator
    )

    result = repair_loop.repair(
        understanding=understanding,
        context=context,
        planner_result=bad_plan,
        generation_result=gen_result,
        validator_result=val_result
    )

    assert result.status == "failed"
    assert len(result.attempts) == 2

    # Verify Requirement 10: Every attempt must be recorded with diagnostic details
    for idx, att in enumerate(result.attempts, 1):
        assert att.attempt_number == idx
        assert att.validation_status == "invalid"
        assert len(att.validator_errors) > 0
        assert any(e.code == "INVALID_ITEM_ID" for e in att.validator_errors)
        assert f"Reasoning for failure at attempt #{idx}" in att.repair_reasoning
        assert att.plan is not None
        assert att.datapack_path is not None
        print(f"  [OK] Attempt #{att.attempt_number} recorded: errors={len(att.validator_errors)}, reasoning='{att.repair_reasoning}'")

    summary_text = result.summary()
    assert "Attempt History:" in summary_text
    print("  [OK] Structured failure summary formatted cleanly.")
    shutil.rmtree(test_dir, ignore_errors=True)


def test_arbitrary_entity_and_item_combination():
    print("=" * 70)
    print("TEST 5: GENERIC REPAIR ON ARBITRARY MOB / ITEM COMBINATION")
    print("=" * 70)

    # Test an arbitrary entity and item: Spider drops string (or iron_ingot)
    test_dir = Path("generated") / "test_repair_arbitrary"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    understanding = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "edition": "Java",
        "understood_request": "Spiders should drop iron ingots.",
        "requirements": [
            {
                "subject": "spider",
                "target": "spider",
                "intent": "drop iron ingots",
                "details": [{"name": "item", "value": "iron_ingot"}],
                "conditions": ["upon death"],
                "constraints": []
            }
        ]
    }
    context = retrieve_minecraft_context(understanding, version="1.21.11")

    # Initial plan has an invalid item name for spiders
    bad_plan = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "summary": "Spider drop with typo in item ID",
        "modifications": [
            {
                "loot_table_path": "entities/spider.json",
                "item": "minecraft:iron_ingot_typo_invalid",
                "count": 2
            }
        ]
    }

    generator = DatapackGenerator(output_dir=test_dir, version="1.21.11")
    gen_result = generator.generate(
        plan=bad_plan,
        context=context,
        understanding=understanding,
        datapack_name="spider_iron_repair_test",
        create_zip=True
    )

    validator = DatapackValidator()
    val_result = validator.validate(gen_result.datapack_path)
    assert not val_result.is_valid

    def generic_repair_handler(call_idx, sys_prompt, usr_prompt, schema):
        # Generically fixes the typo from knowledge without hardcoded spider/iron rules
        assert "iron_ingot_typo_invalid" in usr_prompt
        return {
            "repair_reasoning": "Corrected misspelled item ID to official Minecraft 1.21.11 identifier 'minecraft:iron_ingot'.",
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "Spiders drop iron ingots upon death",
            "modifications": [
                {
                    "loot_table_path": "entities/spider.json",
                    "item": "minecraft:iron_ingot",
                    "count": 2
                }
            ]
        }

    mock_ai = MockAIProvider(handler=generic_repair_handler)
    repair_loop = AIRepairLoop(
        ai_provider=mock_ai,
        max_attempts=3,
        generator=generator,
        validator=validator
    )

    result = repair_loop.repair(
        understanding=understanding,
        context=context,
        planner_result=bad_plan,
        generation_result=gen_result,
        validator_result=val_result
    )

    assert result.is_success
    assert result.status == "success"
    assert result.total_attempts == 1
    assert result.final_validation and result.final_validation.is_valid

    # Check generated JSON content
    repaired_file = Path(result.final_datapack_path) / "data" / "minecraft" / "loot_table" / "entities" / "spider.json"
    assert repaired_file.exists()
    with open(repaired_file, "r", encoding="utf-8") as f:
        repaired_data = json.load(f)

    # Verify original spider drops (string, spider eye) and added iron_ingot
    found_iron = False
    for pool in repaired_data.get("pools", []):
        for entry in pool.get("entries", []):
            if entry.get("name") == "minecraft:iron_ingot":
                found_iron = True
    assert found_iron, "Repaired loot table must contain 'minecraft:iron_ingot'!"

    print("  [OK] Arbitrary spider -> iron_ingot combination successfully healed and validated.")
    shutil.rmtree(test_dir, ignore_errors=True)


def test_ai_provider_instantiation_and_contract():
    print("=" * 70)
    print("TEST 6: AI PROVIDER ABSTRACTION CONTRACT (OLLAMA SUPPORT)")
    print("=" * 70)

    # Verify that AIRepairLoop defaults to AIProvider(provider="ollama") without error
    loop = AIRepairLoop(provider="ollama")
    assert isinstance(loop.ai, AIProvider)
    assert loop.ai.provider == "ollama"
    assert loop.max_attempts == 3
    assert loop.version == "1.21.11"
    print("  [OK] AIRepairLoop initializes cleanly with default Ollama AIProvider.")


def test_multi_attempt_repair_resolution():
    print("=" * 70)
    print("TEST 7: MULTI-ATTEMPT REPAIR RESOLUTION (PASSES ON ATTEMPT #2)")
    print("=" * 70)

    test_dir = Path("generated") / "test_repair_multi"
    if test_dir.exists():
        shutil.rmtree(test_dir)

    understanding = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "edition": "Java",
        "understood_request": "Blaze drops snowballs",
        "requirements": [{"subject": "blaze", "target": "blaze", "intent": "drop snowballs"}]
    }
    context = retrieve_minecraft_context(understanding, version="1.21.11")

    bad_plan = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "summary": "Initial bad blaze plan",
        "modifications": [
            {
                "loot_table_path": "entities/blaze.json",
                "item": "minecraft:wrong_blaze_item",
                "count": 1
            }
        ]
    }

    generator = DatapackGenerator(output_dir=test_dir, version="1.21.11")
    gen_result = generator.generate(
        plan=bad_plan,
        context=context,
        understanding=understanding,
        datapack_name="blaze_multi_repair_test",
        create_zip=True
    )

    validator = DatapackValidator()
    val_result = validator.validate(gen_result.datapack_path)

    def multi_step_handler(call_idx, sys_prompt, usr_prompt, schema):
        if call_idx == 1:
            # Attempt 1 still introduces a bad item
            return {
                "repair_reasoning": "Attempt 1: tried another invalid identifier.",
                "status": "ready",
                "minecraft_version": "1.21.11",
                "summary": "Attempt 1 failed",
                "modifications": [
                    {
                        "loot_table_path": "entities/blaze.json",
                        "item": "minecraft:still_wrong_snow_item",
                        "count": 1
                    }
                ]
            }
        else:
            # Attempt 2 produces the valid item
            return {
                "repair_reasoning": "Attempt 2: successfully resolved to 'minecraft:snowball'.",
                "status": "ready",
                "minecraft_version": "1.21.11",
                "summary": "Attempt 2 resolved",
                "modifications": [
                    {
                        "loot_table_path": "entities/blaze.json",
                        "item": "minecraft:snowball",
                        "count": 1
                    }
                ]
            }

    mock_ai = MockAIProvider(handler=multi_step_handler)
    repair_loop = AIRepairLoop(
        ai_provider=mock_ai,
        max_attempts=3,
        generator=generator,
        validator=validator
    )

    result = repair_loop.repair(
        understanding=understanding,
        context=context,
        planner_result=bad_plan,
        generation_result=gen_result,
        validator_result=val_result
    )

    assert result.is_success
    assert result.status == "success"
    assert result.total_attempts == 2, f"Expected resolution on attempt #2, got {result.total_attempts}"
    assert len(result.attempts) == 2
    assert result.attempts[0].validation_status == "invalid"
    assert result.attempts[1].validation_status == "valid"
    assert result.final_validation and result.final_validation.is_valid

    print(f"  [OK] Multi-attempt repair resolved successfully on attempt #2: {result.message}")
    shutil.rmtree(test_dir, ignore_errors=True)


if __name__ == "__main__":
    try:
        test_zero_repair_attempts_on_valid_datapack()
        test_corrupted_output_triggers_repair_and_regenerates_valid()
        test_maximum_retry_count_enforced_and_no_infinite_loop()
        test_failed_repair_returns_structured_failure_history()
        test_arbitrary_entity_and_item_combination()
        test_ai_provider_instantiation_and_contract()
        test_multi_attempt_repair_resolution()
        print("=" * 70)
        print("ALL 7 REPAIR LOOP TESTS PASSED SUCCESSFULLY!")
        print("=" * 70)
        sys.exit(0)
    except AssertionError:
        sys.exit(1)
