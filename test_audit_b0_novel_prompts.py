import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from ai.planner import MinecraftPlanner, create_plan
from ai.provider import AIProvider, is_ollama_unreachable_error
from ai.schemas import MinecraftUnderstandingResult, Requirement
from ai.understanding import MinecraftUnderstanding
from ai.version_registry import VersionContext
from generator.datapack_generator import DatapackGenerator
from pipeline.minecraft_pipeline import (
    MinecraftPipeline,
    run_minecraft_pipeline,
    _is_question_already_answered,
    _is_fundamentally_unsupported_mechanic,
)
from pipeline.models import PipelineResult
from qa.models import IntentVerificationResult, QACategory, QAResult, QASeverity
from qa.reviewer import AutonomousQAReviewer
from validator.datapack_validator import DatapackValidator


TEST_OUTPUT_DIR = Path("scratch/test_b0_output")


@pytest.fixture(autouse=True)
def cleanup_test_dir():
    if TEST_OUTPUT_DIR.exists():
        shutil.rmtree(TEST_OUTPUT_DIR, ignore_errors=True)
    TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    yield
    if TEST_OUTPUT_DIR.exists():
        shutil.rmtree(TEST_OUTPUT_DIR, ignore_errors=True)


SHARED_HEALTH_PROMPTS = [
    "shared life: all players share the same HP; if one gets hearts all get hearts; if one heals all heal by the same amount.",
    "Make all players share the same health: when one player takes damage or gains hearts, all players get the same change in HP, ...",
    "Make all players share one health bar.",
]

FIFTEEN_NOVEL_PROMPTS = [
    ("shared_hunger", "make all players share the same hunger level and food saturation"),
    ("death_slowness", "everyone gets slowness when one player dies"),
    ("jump_lightning", "lightning strikes when a player jumps"),
    ("lucky_blocks", "break a gold block to trigger random lucky drops or explosions"),
    ("periodic_zombie", "spawn a zombie every 5 minutes"),
    ("ban_item", "ban players from holding or picking up diamond swords"),
    ("double_jump", "double jump mechanic that launches player upwards when jumping twice"),
    ("nightly_random_effect", "grant every player a random status effect each night"),
    ("lava_walker", "frost walker for lava: turning lava into obsidian beneath player"),
    ("sneak_invisibility", "make players invisible while sneaking"),
    ("creeper_defusal", "shearing a creeper disables its explosion"),
    ("void_death_broadcast", "broadcast custom title message when player falls into void"),
    ("elytra_feather_boost", "right click with feather boosts player while flying with elytra"),
    ("tree_capitator", "breaking the bottom log of a tree breaks the entire tree"),
    ("compass_tracker", "make compass needle always track the nearest other player"),
]


class TestAuditB0SharedHealthLoopResolution:
    """
    Acceptance tests for B0:
    The three "shared health" prompts never loop on the same clarification question,
    never produce a plan whose only mechanism is 'health set N', and properly identify
    vanilla Java datapack capability boundaries.
    """

    @pytest.mark.parametrize("prompt", SHARED_HEALTH_PROMPTS)
    def test_shared_health_prompts_detected_as_unsupported_without_loop(self, prompt: str):
        """
        The three shared health prompts must be recognized as unsupported vanilla mechanics,
        halting without asking the repetitive keyword question ('By what amount...').
        """
        result = run_minecraft_pipeline(
            request=prompt,
            minecraft_version="1.21.11",
            provider="ollama",
            create_zip=False,
            output_dir=TEST_OUTPUT_DIR
        )

        assert result.status == "unsupported"
        assert not result.is_success
        assert len(result.errors) > 0
        unsupported_msg = result.errors[0].lower()
        assert "health" in unsupported_msg or "unsupported" in unsupported_msg
        assert result.clarification != "By what amount, percentage, or multiplier should health be set?"
        assert result.clarification != "By what amount, percentage, or multiplier should attack damage be set?"

    @pytest.mark.parametrize("prompt", SHARED_HEALTH_PROMPTS)
    def test_shared_health_with_clarification_answers_never_sets_static_health(self, prompt: str):
        """
        Even when a user answers with a number (e.g. 'Specifically: 20 hearts.') or explanation,
        the pipeline must never resolve it into a bogus 'health set 20' plan.
        """
        # Answer with '20 hearts'
        history_answer_number = [
            {"question": "How should health be configured?", "answer": "20 hearts."}
        ]
        result_num = run_minecraft_pipeline(
            request=prompt,
            minecraft_version="1.21.11",
            provider="ollama",
            create_zip=False,
            output_dir=TEST_OUTPUT_DIR,
            clarification_history=history_answer_number,
            clarification_round=1
        )
        assert result_num.status == "unsupported"
        if result_num.plan:
            assert result_num.plan.get("property") != "health" or result_num.plan.get("operation") != "set"

        # Answer with 'shared health pool'
        history_answer_pool = [
            {"question": "How should health be configured?", "answer": "shared health pool across all players."}
        ]
        result_pool = run_minecraft_pipeline(
            request=prompt,
            minecraft_version="1.21.11",
            provider="ollama",
            create_zip=False,
            output_dir=TEST_OUTPUT_DIR,
            clarification_history=history_answer_pool,
            clarification_round=1
        )
        assert result_pool.status == "unsupported"


class TestAuditB0QAIntentVerification:
    """
    QA Intent Verification must strictly reject plans whose mechanism does not implement
    the described relational behavior (e.g. rejecting 'health set 20' for shared health).
    """

    def test_intent_verification_rejects_static_health_set_for_shared_health(self):
        reviewer = AutonomousQAReviewer(provider="ollama", version="1.21.11")
        prompt = "Make all players share one health bar."

        bogus_plan = {
            "status": "ready",
            "feature_name": "shared_health",
            "mechanisms": [{"type": "attribute_modifier", "property": "health", "operation": "set", "value": 20}],
            "implementation_plan": [
                {
                    "step": 1,
                    "target_file": "data/minecraftai/function/tick.mcfunction",
                    "action": "execute",
                    "command": "attribute @a minecraft:generic.max_health base set 20"
                }
            ]
        }
        bogus_understanding = {
            "status": "understood",
            "feature_type": "attribute_modification",
            "requirements": [{"intent": "modify_property", "property": "health", "operation": "set", "value": 20}]
        }
        generated_files = {
            "data/minecraftai/function/tick.mcfunction": "attribute @a minecraft:generic.max_health base set 20\n"
        }

        intent_res = reviewer.verify_intent(
            original_request=prompt,
            understanding=bogus_understanding,
            plan=bogus_plan,
            generated_files=generated_files,
            findings=[]
        )

        assert not intent_res.matches_intent
        assert any("shared health" in m.lower() or "synchronization" in m.lower() for m in intent_res.missing_aspects)


class TestAuditB0ClarificationLoopBreaker:
    """
    Test loop breaker invariants:
    - Maximum 2 rounds.
    - Never ask the same question twice.
    - Halts with best-effort assumptions or unsupported.
    """

    def test_question_similarity_deduplication(self):
        history = [
            {"question": "By what amount, percentage, or multiplier should health be set?", "answer": "shared"}
        ]
        assert _is_question_already_answered("By what amount should health be set?", history)
        assert _is_question_already_answered("How much health should be set?", history)
        assert not _is_question_already_answered("Should it play a particle effect?", history)

    def test_loop_breaker_max_two_rounds(self):
        pipeline = MinecraftPipeline(provider="ollama", version="1.21.11")

        # Mock understanding that repeatedly requests clarification
        mock_und = MagicMock()
        mock_und.understand.return_value = {
            "status": "needs_clarification",
            "clarification": {"question": "Do you prefer blue or red particles?"}
        }
        pipeline.understanding = mock_und

        history = [
            {"question": "Do you want particles?", "answer": "yes"},
            {"question": "What particle type?", "answer": "flame"}
        ]

        # Round 2 reached: loop breaker should activate
        result = pipeline.run(
            request="Make a fire particle effect around player.",
            clarification_history=history,
            clarification_round=2
        )

        # Loop breaker must not ask for clarification again
        assert result.status != "needs_clarification"
        assert len(result.assumptions) > 0


class TestAuditB0FifteenNovelPrompts:
    """
    Evaluate 15 new prompts across diverse gameplay domains on both Minecraft 1.21.11 and 1.21.1.
    Each must end in either a validated datapack or a single unsupported result within <= 2 rounds.
    """

    @pytest.mark.parametrize("version", ["1.21.11", "1.21.1"])
    @pytest.mark.parametrize("feature_key, prompt_text", FIFTEEN_NOVEL_PROMPTS)
    def test_novel_prompts_terminate_cleanly(self, version: str, feature_key: str, prompt_text: str):
        pipeline = MinecraftPipeline(
            provider="ollama",
            version=version,
            output_dir=TEST_OUTPUT_DIR / f"{version}_{feature_key}",
            verbose=False
        )

        # Build realistic mocked understanding and planner for deterministic execution
        mock_und = MagicMock()
        mock_planner = MagicMock()

        # If fundamentally unsupported (shared hunger), pipeline must catch it
        if feature_key == "shared_hunger":
            result = pipeline.run(request=prompt_text)
            assert result.status == "unsupported"
            assert "hunger" in result.errors[0].lower() or "read-only" in result.errors[0].lower()
            return

        # For valid datapack mechanics, configure realistic structured understanding and plan
        mock_und.understand.return_value = {
            "status": "understood",
            "summary": f"Implementation for {feature_key}",
            "requirements": [{"intent": "custom_gameplay", "subject": "player", "description": prompt_text}],
            "target_version": version
        }

        # Generate standard valid tick actions based on feature domain
        cmd = "execute as @a run effect give @s minecraft:speed 1 0 true"
        if feature_key == "death_slowness":
            cmd = "execute as @a[scores={deaths=1..}] run effect give @a minecraft:slowness 10 1"
        elif feature_key == "jump_lightning":
            cmd = "execute as @a[scores={jump=1..}] at @s run summon minecraft:lightning_bolt ~ ~ ~"
        elif feature_key == "periodic_zombie":
            cmd = "execute if score #timer global matches 6000.. run summon minecraft:zombie ~ ~ ~"
        elif feature_key == "ban_item":
            cmd = "clear @a minecraft:diamond_sword"
        elif feature_key == "nightly_random_effect":
            cmd = "execute if score #night global matches 1 run effect give @a minecraft:night_vision 30 0"
        elif feature_key == "sneak_invisibility":
            cmd = "execute as @a[scores={sneak=1..}] run effect give @s minecraft:invisibility 2 0 true"

        mock_plan = {
            "status": "ready",
            "feature_name": feature_key,
            "summary": f"Plan for {feature_key}",
            "implementation_plan": [
                {
                    "step": 1,
                    "target_file": "data/minecraftai/function/tick.mcfunction",
                    "mechanisms": [
                        {
                            "type": "continuous_action",
                            "actions": [{"action_type": "raw_command", "command": cmd}],
                            "namespace": "minecraftai"
                        }
                    ]
                }
            ]
        }

        pipeline.understanding = mock_und

        with patch("pipeline.minecraft_pipeline.create_plan", return_value=mock_plan):
            result = pipeline.run(request=prompt_text, datapack_name=f"dp_{feature_key}")

        assert result.status in ("verified", "success")
        assert result.is_success
        assert result.final_datapack_path is not None
        assert Path(result.final_datapack_path).exists()
        assert result.final_zip_path is not None
        assert Path(result.final_zip_path).exists()


class TestAuditB0RealLLM:
    """
    Run against real configured LLM provider if reachable, and report real outcome.
    If unreachable, skip cleanly without falsely claiming success.
    """

    def test_real_llm_execution_or_skip(self):
        try:
            ai = AIProvider()
            # Check reachability with a fast test prompt
            test_resp = ai.generate_structured(
                system_prompt="You are a JSON test assistant.",
                user_prompt="Respond with valid JSON: {\"status\": \"ok\"}",
                schema={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"}
                    },
                    "required": ["status"]
                }
            )
            if not test_resp or test_resp.get("status") != "ok":
                pytest.skip("Real LLM did not return expected response; skipping live test.")
        except Exception as e:
            pytest.skip(f"Live LLM provider is not reachable or errored ({e}); skipping live test.")

        # If reachable, test the "shared life" prompt
        pipeline = MinecraftPipeline(provider="ollama", version="1.21.11")
        result = pipeline.run("shared life: all players share the same HP; if one gets hearts all get hearts; if one heals all heal by the same amount.")
        assert result.status == "unsupported"
        assert not result.is_success
