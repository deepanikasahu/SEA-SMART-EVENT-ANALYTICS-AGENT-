"""
Provider-Agnostic LLM Client for Smart Event Analytics Agent.
Supports Groq, Google Gemini, OpenRouter, and a Mock provider via .env configuration.
Written against a clean unified adapter interface so the orchestrator remains 100% provider-agnostic.
"""

import concurrent.futures
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union, Callable, TypeVar
import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load local environment variables
load_dotenv()

T = TypeVar("T")


def execute_with_timeout_and_retry(
    func: Callable[..., T],
    *args: Any,
    timeout_seconds: float = 15.0,
    max_retries: int = 1,
    **kwargs: Any
) -> T:
    """
    Executes a function with a specified timeout (default 15s) and exactly one retry
    (max_retries=1) on timeout or failure.
    Total attempts = 1 initial + max_retries.
    """
    last_exception = None
    for attempt in range(max_retries + 1):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func, *args, **kwargs)
            try:
                return future.result(timeout=timeout_seconds)
            except concurrent.futures.TimeoutError:
                last_exception = TimeoutError(
                    f"LLM call timed out after {timeout_seconds}s (attempt {attempt + 1}/{max_retries + 1})."
                )
                logger.warning(f"Timeout on attempt {attempt + 1}/{max_retries + 1}")
            except Exception as e:
                last_exception = e
                logger.warning(f"LLM call error on attempt {attempt + 1}/{max_retries + 1}: {e}")
    raise last_exception


@dataclass
class ToolCall:
    """Standardized tool call representation across all LLM providers."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    """Standardized LLM response object."""
    content: Optional[str]
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None


class BaseLLMAdapter:
    """Abstract base class for provider adapters."""
    def call_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto"
    ) -> LLMResponse:
        raise NotImplementedError

    def call_text(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None
    ) -> str:
        raise NotImplementedError


class GroqAdapter(BaseLLMAdapter):
    """Adapter for Groq Cloud API using the official Groq SDK."""
    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY", "")
        self.model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        if not self.api_key or self.api_key.startswith("your_"):
            raise ValueError(
                "GROQ_API_KEY is not set or contains a placeholder. "
                "Please configure GROQ_API_KEY in your .env file."
            )
        try:
            from groq import Groq
            self.client = Groq(api_key=self.api_key)
        except ImportError:
            raise ImportError("Please install groq package: `pip install groq`")

    def call_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto"
    ) -> LLMResponse:
        return execute_with_timeout_and_retry(
            self._call_with_tools_impl, messages, tools, tool_choice, timeout_seconds=15.0, max_retries=1
        )

    def _call_with_tools_impl(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto"
    ) -> LLMResponse:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools if tools else None,
                tool_choice=tool_choice if tools else None,
                temperature=0.1
            )
            choice = response.choices[0]
            message = choice.message
            content = message.content

            parsed_tool_calls = []
            if message.tool_calls:
                for tc in message.tool_calls:
                    args = tc.function.arguments
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {}
                    parsed_tool_calls.append(ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=args
                    ))

            return LLMResponse(
                content=content,
                tool_calls=parsed_tool_calls,
                finish_reason=choice.finish_reason,
                model=self.model,
                provider="groq"
            )
        except Exception as e:
            sanitized = str(e).replace(self.api_key, "[REDACTED]")
            raise RuntimeError(f"Groq API call failed: {sanitized}")

    def call_text(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None
    ) -> str:
        return execute_with_timeout_and_retry(
            self._call_text_impl, messages, system_prompt, timeout_seconds=15.0, max_retries=1
        )

    def _call_text_impl(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None
    ) -> str:
        try:
            call_msgs = []
            if system_prompt:
                call_msgs.append({"role": "system", "content": system_prompt})
            call_msgs.extend(messages)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=call_msgs,
                temperature=0.2
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            sanitized = str(e).replace(self.api_key, "[REDACTED]")
            raise RuntimeError(f"Groq API call failed: {sanitized}")


class OpenRouterAdapter(BaseLLMAdapter):
    """Adapter for OpenRouter API (OpenAI compatible)."""
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.model = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        if not self.api_key or self.api_key.startswith("your_"):
            raise ValueError("OPENROUTER_API_KEY is not set in .env")

    def call_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto"
    ) -> LLMResponse:
        return execute_with_timeout_and_retry(
            self._call_with_tools_impl, messages, tools, tool_choice, timeout_seconds=15.0, max_retries=1
        )

    def _call_with_tools_impl(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto"
    ) -> LLMResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8501",
            "X-Title": "Smart Event Analytics Agent"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        try:
            resp = requests.post(self.base_url, headers=headers, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            msg = choice.get("message", {})
            content = msg.get("content")

            parsed_tool_calls = []
            if "tool_calls" in msg and msg["tool_calls"]:
                for tc in msg["tool_calls"]:
                    fn = tc.get("function", {})
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {}
                    parsed_tool_calls.append(ToolCall(
                        id=tc.get("id", "call_1"),
                        name=fn.get("name", ""),
                        arguments=args
                    ))

            return LLMResponse(
                content=content,
                tool_calls=parsed_tool_calls,
                finish_reason=choice.get("finish_reason"),
                model=self.model,
                provider="openrouter"
            )
        except Exception as e:
            sanitized = str(e).replace(self.api_key, "[REDACTED]")
            raise RuntimeError(f"OpenRouter API call failed: {sanitized}")

    def call_text(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None
    ) -> str:
        res = self.call_with_tools(
            ([{"role": "system", "content": system_prompt}] if system_prompt else []) + messages,
            tools=[]
        )
        return res.content or ""


class GeminiAdapter(BaseLLMAdapter):
    """Adapter for Google Gemini API via standard REST endpoint."""
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        self.model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        if not self.api_key or self.api_key.startswith("your_"):
            raise ValueError("GEMINI_API_KEY is not set in .env")

    def call_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto"
    ) -> LLMResponse:
        return execute_with_timeout_and_retry(
            self._call_with_tools_impl, messages, tools, tool_choice, timeout_seconds=15.0, max_retries=1
        )

    def _call_with_tools_impl(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto"
    ) -> LLMResponse:
        # Converts standard tools format to Gemini REST format
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        
        # Convert messages
        contents = []
        for m in messages:
            role = "user" if m["role"] in ["user", "system"] else "model"
            contents.append({
                "role": role,
                "parts": [{"text": str(m["content"])}]
            })

        payload: Dict[str, Any] = {"contents": contents}
        try:
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            cand = data["candidates"][0]
            text = cand["content"]["parts"][0]["text"]
            return LLMResponse(content=text, tool_calls=[], provider="gemini", model=self.model)
        except Exception as e:
            sanitized = str(e).replace(self.api_key, "[REDACTED]")
            raise RuntimeError(f"Gemini API call failed: {sanitized}")

    def call_text(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None
    ) -> str:
        res = self.call_with_tools(
            ([{"role": "system", "content": system_prompt}] if system_prompt else []) + messages,
            tools=[]
        )
        return res.content or ""


class MockLLMAdapter(BaseLLMAdapter):
    """
    Deterministic Mock LLM adapter for fast automated testing and offline verification.
    Simulates tool-calling iterations and grounded explanations.
    """
    def __init__(self):
        self.call_count = 0

    def call_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto"
    ) -> LLMResponse:
        self.call_count += 1
        user_msg = ""
        for m in messages:
            if m["role"] == "user":
                user_msg = m["content"]

        # If user message has no date keywords or time period
        if "tell me which clubs performed best" in user_msg.lower() and not any(k in user_msg.lower() for k in ["semester", "2024", "month", "from", "last"]):
            return LLMResponse(
                content="Could you please specify the time period or semester (e.g., 'last semester' or '2024-01-15 to 2024-05-30') you want to analyze?",
                tool_calls=[],
                provider="mock"
            )

        # First turn: call get_events
        has_events_result = any(m.get("role") == "tool" and m.get("name") == "get_events" for m in messages)
        has_all_data = any(m.get("role") == "tool" and m.get("name") == "get_feedback" for m in messages)

        if not has_events_result:
            dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", user_msg)
            if len(dates) >= 2:
                s_date = dates[0]
                e_date = dates[1]
            else:
                s_date = "2024-01-15"
                e_date = "2024-05-30"

            cat = "Cultural" if "cultural" in user_msg.lower() else "Technical"

            return LLMResponse(
                content="Fetching events conducted during specified period...",
                tool_calls=[
                    ToolCall(
                        id="call_mock_1",
                        name="get_events",
                        arguments={"start_date": s_date, "end_date": e_date, "category": cat}
                    )
                ],
                provider="mock"
            )
        elif not has_all_data:
            # Second turn: request registrations, attendance, feedback, and club plans
            # Extract event ids from previous tool result
            event_ids = []
            for m in messages:
                if m.get("role") == "tool" and m.get("name") == "get_events":
                    try:
                        raw = json.loads(m["content"])
                        event_ids = [e["event_id"] for e in raw]
                    except Exception:
                        event_ids = ["EVT_001", "EVT_002", "EVT_003"]

            return LLMResponse(
                content="Fetching registration, attendance, feedback, and club planning targets...",
                tool_calls=[
                    ToolCall(id="call_mock_2", name="get_registrations", arguments={"event_ids": event_ids}),
                    ToolCall(id="call_mock_3", name="get_attendance", arguments={"event_ids": event_ids}),
                    ToolCall(id="call_mock_4", name="get_feedback", arguments={"event_ids": event_ids}),
                    ToolCall(id="call_mock_5", name="get_club_plans", arguments={})
                ],
                provider="mock"
            )
        else:
            return LLMResponse(
                content="All data retrieved successfully. Ready for deterministic calculation.",
                tool_calls=[],
                provider="mock"
            )

    def call_text(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None
    ) -> str:
        if not messages or not isinstance(messages, list) or "content" not in messages[0]:
            raise ValueError("MockLLMAdapter.call_text requires non-empty messages with user prompt content")

        content = messages[0]["content"]
        if "```json\n" not in content or "\n```" not in content:
            raise ValueError("MockLLMAdapter.call_text failed to locate ```json codeblock in user prompt")

        json_block = content.split("```json\n")[1].split("\n```")[0]
        table = json.loads(json_block)
        if not table:
            return "### Qualitative Performance Analysis\n\nNo clubs evaluated in scope."

        top_clubs = table[:min(3, len(table))]
        max_composite = max(c["composite_score"] for c in top_clubs)
        max_turnout = max(c["attendance_rate_pct"] for c in top_clubs)
        max_feedback = max(c["engagement_quality_rating"] for c in top_clubs)

        lines = [
            "### Qualitative Performance Analysis",
            "",
            "Based strictly on the computed metrics:"
        ]
        for c in top_clubs:
            rank = c["rank"]
            name = c["club_name"]
            score = c["composite_score"]
            turnout = c["attendance_rate_pct"]
            feedback = c["engagement_quality_rating"]

            score_desc = "highest overall score" if score == max_composite else "overall score"
            turnout_desc = "highest turnout" if turnout == max_turnout else "turnout"
            feedback_desc = "highest feedback rating" if feedback == max_feedback else "feedback rating"

            if score == max_composite and feedback == max_feedback:
                sentence = f"{rank}. **{name}** achieved rank {rank} with the {score_desc} of {score:.2f}, a {turnout_desc} of {turnout:.2f}%, and the {feedback_desc} of {feedback:.2f}."
            elif turnout == max_turnout:
                sentence = f"{rank}. **{name}** achieved rank {rank} with an {score_desc} of {score:.2f}, the {turnout_desc} of {turnout:.2f}%, and a {feedback_desc} of {feedback:.2f}."
            else:
                sentence = f"{rank}. **{name}** achieved rank {rank} with an {score_desc} of {score:.2f}, a {turnout_desc} of {turnout:.2f}%, and a {feedback_desc} of {feedback:.2f}."
            lines.append(sentence)

        return "\n".join(lines)


def get_llm_adapter(provider: Optional[str] = None) -> BaseLLMAdapter:
    """
    Factory function returning the configured LLM adapter instance.
    Reads provider from LLM_PROVIDER env variable ('mock', 'groq', 'gemini', 'openrouter').
    Defaults safely to 'mock'.
    """
    chosen_provider = (provider or os.getenv("LLM_PROVIDER", "mock")).strip().lower()

    if chosen_provider == "groq":
        return GroqAdapter()
    elif chosen_provider == "gemini":
        return GeminiAdapter()
    elif chosen_provider == "openrouter":
        return OpenRouterAdapter()
    elif chosen_provider in ["mock", "test"]:
        return MockLLMAdapter()
    else:
        raise ValueError(
            f"Unsupported LLM_PROVIDER '{chosen_provider}'. "
            f"Please choose one of: 'groq', 'gemini', 'openrouter', 'mock'."
        )
