"""
Tests for Task 5: Safe, provider-agnostic LLM layer.
Verifies timeout, retry wrapper, credential masking, and deterministic ranking fallback.
"""

import json
import os
import tempfile
import time
from typing import Any, Dict, List, Optional
import pytest

from data_generation.generate_dummy_data import generate_data
from agent.llm_client import (
    BaseLLMAdapter,
    LLMResponse,
    MockLLMAdapter,
    execute_with_timeout_and_retry,
    get_llm_adapter,
)
from agent.orchestrator import EventAnalyticsAgent


class AlwaysFailingLLMAdapter(BaseLLMAdapter):
    """Adapter that intentionally raises on every single external call."""
    def __init__(self, fake_key: str = "fake_secret_key_abcdef123456"):
        self.api_key = fake_key
        self.call_tools_attempts = 0
        self.call_text_attempts = 0

    def call_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto"
    ) -> LLMResponse:
        self.call_tools_attempts += 1
        raise ConnectionError(f"Remote service unreachable with key {self.api_key}")

    def call_text(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None
    ) -> str:
        self.call_text_attempts += 1
        raise TimeoutError(f"Remote text generation timed out with key {self.api_key}")


def test_mock_adapter_is_default_provider():
    """Verify get_llm_adapter defaults to MockLLMAdapter when no provider is specified."""
    # When provider is None and LLM_PROVIDER is unset or default
    adapter = get_llm_adapter()
    assert isinstance(adapter, MockLLMAdapter)


def test_credentials_not_leaked_in_result_or_execution_log():
    """Verify secret API keys never leak into execution_log or result dict on failure."""
    secret_key = "super_secret_token_never_log_this_xyz999"
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        generate_data(db_path=db_path, seed=42)

        agent = EventAnalyticsAgent(
            db_path=db_path,
            weights_path="weights_config.json",
            provider="mock"
        )
        agent.llm_adapter = AlwaysFailingLLMAdapter(fake_key=secret_key)

        res = agent.run("Analyze all technical events conducted last semester and tell me which clubs performed best.")

        result_str = json.dumps(res, default=str)
        assert secret_key not in result_str
        assert "[REDACTED]" in result_str


def test_execute_with_timeout_and_retry_behavior():
    """Verify wrapper executes with 1 retry on failure and catches timeout."""
    attempts = 0

    def flaky_func(val: int):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionResetError("Transient network drop")
        return val * 2

    # Attempt 1 fails, attempt 2 (retry 1) succeeds
    result = execute_with_timeout_and_retry(flaky_func, 21, timeout_seconds=5.0, max_retries=1)
    assert result == 42
    assert attempts == 2

    # Function that times out
    def slow_func():
        time.sleep(0.5)
        return "done"

    with pytest.raises(TimeoutError) as exc_info:
        execute_with_timeout_and_retry(slow_func, timeout_seconds=0.05, max_retries=1)
    assert "timed out" in str(exc_info.value)


def test_deterministic_fallback_when_llm_raises_on_all_calls():
    """
    Assert that when an LLM provider fails on every call:
    1. Orchestrator falls back to deterministic execution.
    2. result['llm_notice'] is populated with a user-facing notice.
    3. The ranked_clubs table is byte-for-byte identical to the mock run for the same seed.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_fallback.db")
        generate_data(db_path=db_path, seed=42)

        # Baseline run with mock adapter
        mock_agent = EventAnalyticsAgent(
            db_path=db_path,
            weights_path="weights_config.json",
            provider="mock"
        )
        mock_res = mock_agent.run("Analyze all technical events conducted last semester and tell me which clubs performed best.")

        # Run with failing adapter
        failing_agent = EventAnalyticsAgent(
            db_path=db_path,
            weights_path="weights_config.json",
            provider="mock"
        )
        failing_agent.llm_adapter = AlwaysFailingLLMAdapter()
        fallback_res = failing_agent.run("Analyze all technical events conducted last semester and tell me which clubs performed best.")

        assert fallback_res["status"] == "SUCCESS"
        assert fallback_res["llm_notice"] is not None
        assert "LLM provider call failed" in fallback_res["llm_notice"]
        assert "Fell back to deterministic execution and ranking" in fallback_res["llm_notice"]

        # Assert ranking is 100% identical to mock run
        assert fallback_res["ranked_clubs"] == mock_res["ranked_clubs"]
        assert fallback_res["in_scope_events_count"] == mock_res["in_scope_events_count"]
