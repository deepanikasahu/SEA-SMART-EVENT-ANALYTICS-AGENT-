"""
Provider-Agnostic LLM Adapter — Smart Event Analytics Agent v2.

Supports Claude (Anthropic), Groq, and an offline Mock provider.
Switch via V2_LLM_PROVIDER environment variable or v2_config.yaml.

Key difference vs v1's llm_client.py:
  - Claude added as a first-class provider (default for v2).
  - All adapters share a strict BaseLLMAdapter interface.
  - The Mock adapter is fully deterministic (fixed seed) for CI/testing.
"""

from __future__ import annotations
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── Pricing constants (USD per 1M tokens) ────────────────────────────────────
# Source: Groq pricing page (approx), Claude pricing page (approx)
PRICING = {
    "openai/gpt-oss-20b":   {"input": 0.90,  "output": 0.90},   # Groq v1 model
    "openai/gpt-oss-120b":  {"input": 3.00,  "output": 3.00},   # Groq v2 model
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "default":               {"input": 1.00,  "output": 1.00},
}


class UsageTracker:
    """Thread-local call telemetry — latency + token counts + cost per adapter."""

    def __init__(self):
        self.calls: List[Dict[str, Any]] = []

    def record(self, provider: str, model: str, prompt_tokens: int,
               completion_tokens: int, latency_s: float):
        pricing = PRICING.get(model, PRICING["default"])
        cost_usd = (
            prompt_tokens / 1_000_000 * pricing["input"]
            + completion_tokens / 1_000_000 * pricing["output"]
        )
        self.calls.append({
            "provider": provider,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "latency_s": round(latency_s, 3),
            "cost_usd": round(cost_usd, 6),
        })

    def summary(self) -> Dict[str, Any]:
        if not self.calls:
            return {"calls": 0, "total_tokens": 0, "total_cost_usd": 0.0, "total_latency_s": 0.0}
        return {
            "calls": len(self.calls),
            "total_tokens": sum(c["total_tokens"] for c in self.calls),
            "prompt_tokens": sum(c["prompt_tokens"] for c in self.calls),
            "completion_tokens": sum(c["completion_tokens"] for c in self.calls),
            "total_cost_usd": round(sum(c["cost_usd"] for c in self.calls), 6),
            "total_latency_s": round(sum(c["latency_s"] for c in self.calls), 3),
            "per_call": self.calls,
        }

    def reset(self):
        self.calls.clear()


# Global tracker — reset at the start of each pipeline run
_global_tracker = UsageTracker()


def get_tracker() -> UsageTracker:
    return _global_tracker


# ─── Shared Data Classes (mirrors v1's ToolCall / LLMResponse for compat) ──────

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    content: Optional[str]
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None


# ─── Base interface ────────────────────────────────────────────────────────────

class BaseLLMAdapter:
    """Abstract base class — every provider must implement both methods."""

    def call_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto",
    ) -> LLMResponse:
        raise NotImplementedError

    def call_text(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
    ) -> str:
        raise NotImplementedError

    @property
    def provider_name(self) -> str:
        return self.__class__.__name__.replace("Adapter", "")


# ─── Claude Adapter (Anthropic) ───────────────────────────────────────────────

class ClaudeAdapter(BaseLLMAdapter):
    """
    Anthropic Claude adapter using the official `anthropic` SDK.
    Default model: claude-3-5-sonnet-20241022.
    """

    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.model = os.getenv("V2_CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
        self.max_tokens = int(os.getenv("V2_CLAUDE_MAX_TOKENS", "2048"))
        if not self.api_key or self.api_key.startswith("your_"):
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env file. "
                "Get a key from https://console.anthropic.com"
            )
        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.api_key)
        except ImportError:
            raise ImportError("Install anthropic SDK: pip install anthropic")

    def call_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto",
    ) -> LLMResponse:
        import anthropic

        # Claude uses a slightly different tool schema format — convert from OpenAI-style
        claude_tools = []
        for t in tools:
            fn = t.get("function", t)
            claude_tools.append({
                "name": fn["name"],
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            })

        # Separate system prompt from messages
        system_msg = ""
        conv_messages = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                conv_messages.append(m)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_msg,
            messages=conv_messages,
            tools=claude_tools,
        )

        tool_calls: List[ToolCall] = []
        text_content: List[str] = []

        for block in response.content:
            if block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input if isinstance(block.input, dict) else {},
                ))
            elif block.type == "text":
                text_content.append(block.text)

        return LLMResponse(
            content="\n".join(text_content) if text_content else None,
            tool_calls=tool_calls,
            finish_reason=str(response.stop_reason),
            model=self.model,
            provider="ClaudeAdapter",
        )

    def call_text(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
    ) -> str:
        import anthropic

        system_msg = system_prompt or ""
        conv_messages = [m for m in messages if m["role"] != "system"]

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_msg,
            messages=conv_messages,
        )
        return response.content[0].text if response.content else ""


# ─── Groq Adapter (reused from v1, no v1 files modified) ──────────────────────

class GroqAdapter(BaseLLMAdapter):
    """
    Groq Cloud API adapter — identical interface to ClaudeAdapter.
    Allows A/B testing: v1 Groq vs v2 Claude on the exact same pipeline.
    """

    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY", "")
        # V2_GROQ_MODEL lets v2 use a different model than v1 (A/B at model level)
        self.model = os.getenv("V2_GROQ_MODEL") or os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
        self.max_tokens = int(os.getenv("V2_GROQ_MAX_TOKENS", "2048"))
        if not self.api_key or self.api_key.startswith("your_"):
            raise ValueError("GROQ_API_KEY is not set or contains a placeholder.")
        try:
            from groq import Groq
            self.client = Groq(api_key=self.api_key)
        except ImportError:
            raise ImportError("Install groq SDK: pip install groq")

    def call_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto",
    ) -> LLMResponse:
        import time
        t0 = time.time()
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            max_tokens=self.max_tokens,
        )
        latency = time.time() - t0
        choice = response.choices[0]
        msg = choice.message

        # Record telemetry
        usage = response.usage
        _global_tracker.record(
            provider="GroqAdapter",
            model=self.model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            latency_s=latency,
        )

        tool_calls: List[ToolCall] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))

        return LLMResponse(
            content=msg.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            model=self.model,
            provider="GroqAdapter",
        )

    def call_text(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
    ) -> str:
        import time
        all_msgs = messages
        if system_prompt:
            all_msgs = [{"role": "system", "content": system_prompt}] + messages
        t0 = time.time()
        response = self.client.chat.completions.create(
            model=self.model,
            messages=all_msgs,
            max_tokens=self.max_tokens,
        )
        latency = time.time() - t0
        usage = response.usage
        _global_tracker.record(
            provider="GroqAdapter",
            model=self.model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            latency_s=latency,
        )
        return response.choices[0].message.content or ""



# ─── Offline Mock Adapter (deterministic, no API call) ─────────────────────────

class MockAdapter(BaseLLMAdapter):
    """
    Deterministic offline mock for fast CI runs and comparison harness tests.
    Always returns a fixed tool call (get_events with last-semester dates)
    on the first turn, then signals completion on subsequent turns.
    """

    _MOCK_EVENTS_CALL = {
        "id": "mock_tc_001",
        "name": "get_events",
        "arguments": {
            "start_date": "2024-01-15",
            "end_date": "2024-05-30",
            "category": "Technical",
        },
    }

    _MOCK_NARRATIVE = (
        "## Executive Performance Summary\n\n"
        "Based on the deterministically computed club metrics:\n\n"
        "- **Top Club** demonstrated the highest composite score driven by strong engagement quality and consistent turnout.\n"
        "- All rankings are derived exclusively from the pre-computed metrics table provided.\n"
        "- No figures have been estimated or invented by this model.\n"
    )

    def __init__(self):
        self._call_count: Dict[str, int] = {}

    def call_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto",
    ) -> LLMResponse:
        conv_id = str(id(messages))
        count = self._call_count.get(conv_id, 0)
        self._call_count[conv_id] = count + 1

        if count == 0:
            # First turn: return a tool call for get_events
            return LLMResponse(
                content=None,
                tool_calls=[ToolCall(**self._MOCK_EVENTS_CALL)],
                finish_reason="tool_calls",
                model="mock",
                provider="MockAdapter",
            )
        # Subsequent turns: signal done
        return LLMResponse(
            content="Data collection complete.",
            tool_calls=[],
            finish_reason="stop",
            model="mock",
            provider="MockAdapter",
        )

    def call_text(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
    ) -> str:
        return self._MOCK_NARRATIVE


# ─── Factory ───────────────────────────────────────────────────────────────────

def get_v2_adapter(provider: Optional[str] = None) -> BaseLLMAdapter:
    """
    Resolve and return the appropriate LLM adapter for v2.

    Priority:
      1. `provider` argument (explicit call-time override)
      2. V2_LLM_PROVIDER environment variable
      3. v2_config.yaml (loaded lazily)
      4. Fallback: "mock" (safe default for offline environments)
    """
    resolved = (
        provider
        or os.getenv("V2_LLM_PROVIDER")
        or _read_config_provider()
        or "mock"
    ).lower()

    logger.info(f"v2 LLM adapter resolved: {resolved}")

    if resolved == "claude":
        return ClaudeAdapter()
    elif resolved == "groq":
        return GroqAdapter()
    elif resolved == "mock":
        return MockAdapter()
    else:
        raise ValueError(
            f"Unknown v2 LLM provider '{resolved}'. "
            "Supported: 'claude', 'groq', 'mock'."
        )


def _read_config_provider() -> Optional[str]:
    """Read default provider from v2_config.yaml without crashing if missing."""
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "config", "v2_config.yaml"
    )
    try:
        import yaml
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)
        return cfg.get("llm", {}).get("provider")
    except Exception:
        return None
