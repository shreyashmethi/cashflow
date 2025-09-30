
from __future__ import annotations
import os
import json
import base64
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# ---- Provider Abstraction ------------------------------------------------

class BaseLLMProvider:
    def __init__(self, model: Optional[str] = None, temperature: float = 0.0, max_tokens: int = 2000):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    # Text-only generation
    def generate(self, system: str, user: str, json_mode: bool = False) -> str:
        raise NotImplementedError

    # Vision + Text generation (images: list of bytes)
    def generate_vision(self, system: str, user: str, images: List[bytes], json_mode: bool = False) -> str:
        raise NotImplementedError

# ---- OpenAI (GPT) --------------------------------------------------------

class OpenAIProvider(BaseLLMProvider):
    def __init__(self, model: Optional[str] = None, temperature: float = 0.0, max_tokens: int = 2000):
        super().__init__(model, temperature, max_tokens)
        try:
            from openai import OpenAI  # type: ignore
        except Exception as e:
            raise RuntimeError("openai package is required for OpenAIProvider. pip install openai") from e
        self._client = OpenAI()
        if self.model is None:
            # Sensible default that supports vision + text
            self.model = os.getenv("OPENAI_MODEL", "gpt-4o")

    def _ensure_json(self, text: str) -> str:
        # Strip code fences or stray text around JSON; return raw JSON string
        t = text.strip()
        if t.startswith("```"):
            t = t.strip("`")
            # remove possible "json" language hint
            if t.startswith("json"):
                t = t[len("json"):].lstrip()
        # Find first '{' and last '}' as a simple recovery
        l, r = t.find("{"), t.rfind("}")
        if l != -1 and r != -1 and r > l:
            return t[l:r+1]
        return t

    def generate(self, system: str, user: str, json_mode: bool = False) -> str:
        msgs = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        resp = self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=msgs,
            response_format={"type": "json_object"} if json_mode else None,
        )
        out = resp.choices[0].message.content or ""
        return out if not json_mode else self._ensure_json(out)

    def generate_vision(self, system: str, user: str, images: List[bytes], json_mode: bool = False) -> str:
        # Build a single user message with mixed text + images
        content: List[Dict[str, Any]] = [{"type": "text", "text": user}]
        for b in images:
            b64 = base64.b64encode(b).decode("utf-8")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}
            })
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": content}]
        resp = self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=msgs,
            response_format={"type": "json_object"} if json_mode else None,
        )
        out = resp.choices[0].message.content or ""
        return out if not json_mode else self._ensure_json(out)
    
    """def generate_vision(self, system, user, image_parts, json_mode=False):
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": [{"type": "text", "text": user}, *image_parts]},
        ]
        kwargs = {"model": self.cfg.llm.model, "messages": messages, "temperature": 0}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self._client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content

    def generate_vision_stateful(self, system, user, image_parts, state, json_mode=True):
        # include previous state as text (or a tool call if you already use tools)
        state_snippet = {"type": "text", "text": f"Current state JSON:\n{state}"}
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": [state_snippet, {"type": "text", "text": user}, *image_parts]},
        ]
        kwargs = {"model": self.cfg.llm.model, "messages": messages, "temperature": 0}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self._client.chat.completions.create(**kwargs)
        # parse JSON string to dict
        import json
        return json.loads(resp.choices[0].message.content)"""

# ---- Anthropic (Claude) ---------------------------------------------------

class AnthropicProvider(BaseLLMProvider):
    def __init__(self, model: Optional[str] = None, temperature: float = 0.0, max_tokens: int = 2000):
        super().__init__(model, temperature, max_tokens)
        try:
            from anthropic import Anthropic  # type: ignore
        except Exception as e:
            raise RuntimeError("anthropic package is required for AnthropicProvider. pip install anthropic") from e
        self._client = Anthropic()
        if self.model is None:
            self.model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20240620")

    def _ensure_json(self, text: str) -> str:
        t = text.strip()
        if t.startswith("```"):
            t = t.strip("`")
            if t.startswith("json"):
                t = t[len("json"):].lstrip()
        l, r = t.find("{"), t.rfind("}")
        if l != -1 and r != -1 and r > l:
            return t[l:r+1]
        return t

    def generate(self, system: str, user: str, json_mode: bool = False) -> str:
        # Anthropic Messages API
        content = [{"type": "text", "text": user}]
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system,
            messages=[{"role": "user", "content": content}],
        )
        out = "".join([b.text for b in resp.content if b.type == "text"])
        return out if not json_mode else self._ensure_json(out)

    def generate_vision(self, system: str, user: str, images: List[bytes], json_mode: bool = False) -> str:
        # Images as base64
        content: List[Dict[str, Any]] = [{"type": "text", "text": user}]
        for b in images:
            b64 = base64.b64encode(b).decode("utf-8")
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": b64}
            })
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system,
            messages=[{"role": "user", "content": content}],
        )
        out = "".join([b.text for b in resp.content if b.type == "text"])
        return out if not json_mode else self._ensure_json(out)

# ---- Factory --------------------------------------------------------------

def make_provider(
    provider_name: str = "gpt",
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 2000,
) -> BaseLLMProvider:
    name = (provider_name or "gpt").lower()
    if name in ["gpt", "openai"]:
        return OpenAIProvider(model=model, temperature=temperature, max_tokens=max_tokens)
    elif name in ["claude", "anthropic", "claude4", "claude-4"]:
        # accept 'claude4' alias; actual model string can be overridden via env or argument
        return AnthropicProvider(model=model, temperature=temperature, max_tokens=max_tokens)
    raise ValueError(f"Unknown provider: {provider_name}")
