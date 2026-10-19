"""
test_audit_b8_clarification.py - Tests for B8: Multi-Round Clarification Accumulation and Length Validation.

Verifies:
1. Multi-round clarification flow preserves all previous answers across consecutive rounds.
2. The composed prompt is re-validated through validate_prompt, rejecting oversized accumulated prompts (HTTP 400).
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from pipeline.models import PipelineResult
from web.app import app
from security.rate_limit import DEFAULT_RATE_LIMITER


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    DEFAULT_RATE_LIMITER.reset()
    yield
    DEFAULT_RATE_LIMITER.reset()


def test_two_clarification_rounds_accumulate_answers():
    """
    Submitting answers in multiple clarification rounds must accumulate
    earlier answers rather than replacing them.
    """
    client = TestClient(app)

    # Round 1: ambiguous base request
    res1 = PipelineResult(
        status="needs_clarification",
        is_success=False,
        original_request="Make me faster.",
        clarification="How much faster?",
        clarification_requirements=[{"question": "How much faster?", "options": ["speed 1", "speed 2"]}]
    )

    # Round 2: still needs clarification (e.g. duration)
    res2 = PipelineResult(
        status="needs_clarification",
        is_success=False,
        original_request="Make me faster. Specifically: speed 2.",
        clarification="For how long?",
        clarification_requirements=[{"question": "For how long?", "options": ["30 seconds", "infinite"]}]
    )

    # Round 3: fully specified and succeeds
    res3 = PipelineResult(
        status="success",
        is_success=True,
        original_request="Make me faster. Specifically: speed 2. Specifically: 30 seconds.",
        minecraft_version="1.21.11"
    )

    mock_run = MagicMock(side_effect=[res1, res2, res3])

    with patch("web.app.run_minecraft_pipeline", mock_run):
        # 1. Base request
        resp1 = client.post("/api/generate", json={"request": "Make me faster."})
        assert resp1.status_code == 200
        d1 = resp1.json()
        assert d1["status"] == "needs_clarification"
        assert d1["refined_request"] == "Make me faster."

        # 2. Answer first question: "speed 2"
        resp2 = client.post("/api/generate", json={
            "request": d1["refined_request"],
            "clarification_answer": "speed 2",
            "previous_request": d1["refined_request"]
        })
        assert resp2.status_code == 200
        d2 = resp2.json()
        assert d2["status"] == "needs_clarification"
        assert d2["refined_request"] == "Make me faster. Specifically: speed 2."

        # 3. Answer second question: "30 seconds"
        resp3 = client.post("/api/generate", json={
            "request": d2["refined_request"],
            "clarification_answer": "30 seconds",
            "previous_request": d2["refined_request"]
        })
        assert resp3.status_code == 200
        d3 = resp3.json()
        assert d3["status"] == "success"
        assert "speed 2" in d3["original_request"]
        assert "30 seconds" in d3["original_request"]

        # Ensure the pipeline was called in Round 3 with BOTH answers accumulated
        assert mock_run.call_count == 3
        last_call_args = mock_run.call_args_list[-1]
        assert "Make me faster. Specifically: speed 2. Specifically: 30 seconds." in last_call_args.kwargs["request"]


def test_clarification_composed_prompt_revalidates_length():
    """
    If answering clarification causes the composed prompt to exceed
    the maximum prompt length, it must be rejected with HTTP 400.
    """
    client = TestClient(app)

    # Base prompt that is close to the 2000 char limit
    base_prompt = "a" * 1950
    huge_answer = "b" * 100

    resp = client.post("/api/generate", json={
        "request": base_prompt,
        "clarification_answer": huge_answer,
        "previous_request": base_prompt
    })

    assert resp.status_code == 400
    assert "maximum permitted length" in resp.json()["detail"].lower()
