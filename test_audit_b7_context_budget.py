"""
test_audit_b7_context_budget.py - Tests for B7: Planner Prompt Context Budget and Output Token Truncation.

Verifies:
1. Estimated planner prompt size for sample requests stays safely within configured input token budget.
2. An Ollama response with done_reason="length" immediately raises a RuntimeError instead of parsing broken JSON.
3. The planner reuses pre-retrieved context without executing redundant second retrievals.
"""

from unittest.mock import MagicMock, patch
import pytest
from ai.context import retrieve_minecraft_context
from ai.planner import MinecraftPlanner, create_plan
from ai.provider import AIProvider


def test_estimated_planner_prompt_within_budget():
    """
    For typical sample requests, estimated prompt tokens must not exceed
    the input budget (num_ctx - num_predict).
    """
    sample_requests = [
        "Make every skeleton drop iron ingots.",
        "When it starts raining, give every player one diamond.",
        "Add a recipe that crafts a diamond from 9 dirt blocks.",
        "Give players night vision once when night starts.",
        "Make all creepers drop diamonds and summon lightning.",
    ]

    planner = MinecraftPlanner(version="1.21.11")
    system_prompt = planner._system_prompt()

    # Default configured budget: 16384 total context - 4096 output budget = 12288 input tokens
    num_ctx = 16384
    num_predict = 4096
    input_budget = num_ctx - num_predict

    for req in sample_requests:
        understanding = {
            "status": "understood",
            "minecraft_version": "1.21.11",
            "understood_request": req,
            "requirements": [{"description": req, "target": "@a"}]
        }
        context = retrieve_minecraft_context(understanding, version="1.21.11", max_results=10)
        user_prompt = planner._build_user_prompt(understanding, context)

        total_chars = len(system_prompt) + len(user_prompt)
        estimated_tokens = total_chars // 4

        # Must comfortably fit within the input token budget
        assert estimated_tokens <= input_budget, (
            f"Prompt for '{req}' estimated at {estimated_tokens} tokens exceeds budget of {input_budget}"
        )


def test_ollama_done_reason_length_raises():
    """
    If Ollama halts with done_reason='length', a RuntimeError is raised
    indicating output truncation rather than attempting to repair invalid partial JSON.
    """
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.done_reason = "length"
    mock_response.message.content = '{"status": "ready", "sum'
    mock_client.chat.return_value = mock_response

    provider = AIProvider(provider="ollama")
    provider.client = mock_client

    with pytest.raises(RuntimeError, match="done_reason='length'"):
        provider.generate_structured(
            system_prompt="system",
            user_prompt="user",
            schema={"type": "object"}
        )


def test_planner_reuses_provided_context():
    """
    create_plan must reuse pre-computed context and not call retrieve_minecraft_context again.
    """
    dummy_understanding = {
        "status": "understood",
        "minecraft_version": "1.21.11",
        "understood_request": "Dummy request",
        "requirements": [{"description": "dummy"}]
    }
    dummy_context = {
        "minecraft": {"edition": "Java Edition", "version": "1.21.11"},
        "user_request": "Dummy request",
        "requirements": ["dummy"],
        "knowledge": {}
    }

    mock_ai = MagicMock()
    mock_ai.generate_structured.return_value = {
        "status": "ready",
        "minecraft_version": "1.21.11",
        "summary": "Dummy plan",
        "implementation_plan": []
    }

    with patch("ai.planner.retrieve_minecraft_context") as mock_retrieve:
        plan = create_plan(
            dummy_understanding,
            ai_provider=mock_ai,
            context=dummy_context
        )
        assert plan["status"] == "ready"
        # Since context was provided, retrieve_minecraft_context must NOT be called
        mock_retrieve.assert_not_called()
