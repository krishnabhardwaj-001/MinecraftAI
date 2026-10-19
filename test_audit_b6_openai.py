"""
test_audit_b6_openai.py - Tests for B6: OpenAI Provider Schema Compatibility and Configuration.

Verifies:
1. OpenAI provider uses strict: False for json_schema, allowing Pydantic schemas with extra fields.
2. Default model is 'gpt-4o' (not unverified 'gpt-5.6') and OPENAI_MODEL environment variable is respected.
3. Requests sent to client.responses.create or client.chat.completions.create are properly formed and return parsed JSON.
"""

import json
from unittest.mock import MagicMock, patch
import pytest
from ai.provider import AIProvider


def test_openai_provider_default_model(monkeypatch):
    """OpenAI provider defaults to gpt-4o when OPENAI_MODEL is not set."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-mock-test-key")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    provider = AIProvider(provider="openai")
    assert provider.model == "gpt-4o"


def test_openai_provider_custom_model(monkeypatch):
    """OpenAI provider respects OPENAI_MODEL environment variable."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-mock-test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")

    provider = AIProvider(provider="openai")
    assert provider.model == "gpt-4o-mini"


def test_openai_responses_api_sends_strict_false(monkeypatch):
    """When using responses API, format.strict must be False."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-mock-test-key")

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.output_text = json.dumps({"status": "ready", "summary": "test passed"})
    mock_client.responses.create.return_value = mock_response

    with patch("ai.provider.OpenAI", return_value=mock_client):
        provider = AIProvider(provider="openai")
        schema = {
            "type": "object",
            "properties": {"status": {"type": "string"}},
            "additionalProperties": True  # Pydantic extra="allow" produces this
        }

        result = provider.generate_structured(
            system_prompt="You are a helper.",
            user_prompt="Make skeletons drop iron.",
            schema=schema
        )

        assert result == {"status": "ready", "summary": "test passed"}

        # Inspect call args
        mock_client.responses.create.assert_called_once()
        _, kwargs = mock_client.responses.create.call_args
        assert kwargs["model"] == "gpt-4o"
        assert kwargs["instructions"] == "You are a helper."
        assert kwargs["input"] == "Make skeletons drop iron."

        format_dict = kwargs["text"]["format"]
        assert format_dict["type"] == "json_schema"
        assert format_dict["strict"] is False
        assert format_dict["schema"] == schema


def test_openai_chat_completions_fallback_sends_strict_false(monkeypatch):
    """When falling back to chat completions API, json_schema.strict must be False."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-mock-test-key")

    # Mock client without responses attribute
    mock_client = MagicMock(spec=["chat", "close"])
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({"status": "ready", "items": ["diamond"]})
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_completion

    with patch("ai.provider.OpenAI", return_value=mock_client):
        provider = AIProvider(provider="openai")
        schema = {"type": "object", "properties": {"status": {"type": "string"}}}

        result = provider.generate_structured(
            system_prompt="System instructions",
            user_prompt="Give player diamond",
            schema=schema
        )

        assert result == {"status": "ready", "items": ["diamond"]}

        mock_client.chat.completions.create.assert_called_once()
        _, kwargs = mock_client.chat.completions.create.call_args
        rf = kwargs["response_format"]
        assert rf["type"] == "json_schema"
        assert rf["json_schema"]["strict"] is False
