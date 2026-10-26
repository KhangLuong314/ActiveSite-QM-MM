"""ActiveSite — OpenAI-compatible model client (NVIDIA NIM by default; Meterless is just another base URL).

Without MODEL_API_KEY the client is unavailable and ``generate`` returns None
without any HTTP call. Callers must validate everything that comes back and
never execute it: the Planner keeps only allow-listed steps.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

import httpx

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "nvidia/llama-3.3-nemotron-super-49b-v1"
PLANNER_SYSTEM = (
    "You plan a QM/MM setup. Reply with one JSON object only: "
    '{"steps": [...], "theory": "PM6"}. Allowed steps, in order: gather_data, propose_qm_region, precheck, '
    "run_qmmm, postcheck, explain. Do not add steps. Do not add prose."
)


class ModelClient:
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None, api_key: Optional[str] = None,
                 timeout: float = 60.0):
        self.api_key = api_key if api_key is not None else (
            os.getenv("MODEL_API_KEY") or os.getenv("NVIDIA_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        )
        resolved_model = model or os.getenv("MODEL_NAME") or os.getenv("NEMOTRON_MODEL") or DEFAULT_MODEL
        if not base_url and not os.getenv("MODEL_BASE_URL"):
            if self.api_key.startswith("sk-"):
                self.base_url = "https://api.openai.com/v1"
                self.model = model or os.getenv("MODEL_NAME") or "gpt-4o"
            else:
                self.base_url = DEFAULT_BASE_URL
                self.model = resolved_model
        else:
            self.base_url = (base_url or os.getenv("MODEL_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
            self.model = resolved_model
        self.timeout = timeout
        self.calls = 0
        self.last_error: Optional[str] = None

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def generate(self, system: str, prompt: str, max_tokens: int = 400) -> Optional[str]:
        if not self.available:
            return None
        self.calls += 1
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": int(max_tokens),
        }
        try:
            r = httpx.post(f"{self.base_url}/chat/completions", json=payload,
                           headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                           timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            msg = data["choices"][0]["message"]
            content = msg.get("content") or msg.get("reasoning_content")
            return content if isinstance(content, str) else None
        except Exception as exc:  # network, schema, auth: the caller falls back
            self.last_error = f"{type(exc).__name__}: {exc}"[:300]
            return None

    def chat_detailed(self, messages: list[dict[str, Any]] | list[Any], max_tokens: int = 1500, model: Optional[str] = None) -> Dict[str, Any]:
        """Multi-turn conversation returning reply content and separated thinking/reasoning process."""
        if not self.available:
            return {"reply": None, "thinking": None}
        self.calls += 1
        model_name = model or os.getenv("NEMOTRON_MODEL") or self.model or "nvidia/nemotron-3.5-lightning-30b-a3b"
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": int(max_tokens),
        }
        try:
            r = httpx.post(f"{self.base_url}/chat/completions", json=payload,
                           headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                           timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            msg = data["choices"][0]["message"]
            raw_content = msg.get("content") or ""
            reasoning = msg.get("reasoning_content") or ""

            thinking = reasoning.strip() if isinstance(reasoning, str) else ""
            content = raw_content.strip() if isinstance(raw_content, str) else ""

            # Check if thinking/thought tags are embedded in content
            for tag in ("thought", "think"):
                pattern = rf"<{tag}>(.*?)</{tag}>"
                m = re.search(pattern, content, flags=re.DOTALL)
                if m:
                    extracted = m.group(1).strip()
                    if not thinking:
                        thinking = extracted
                    content = re.sub(pattern, "", content, flags=re.DOTALL).strip()

            # If content was empty but reasoning exists, use reasoning as reply fallback
            if not content and thinking:
                content = thinking
                thinking = ""

            return {"reply": content if content else None, "thinking": thinking if thinking else None}
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"[:300]
            return {"reply": None, "thinking": None}

    def chat(self, messages: list[dict[str, Any]] | list[Any], max_tokens: int = 800, model: Optional[str] = None) -> Optional[str]:
        """Multi-turn conversation with Nemotron / OpenAI-compatible endpoint."""
        res = self.chat_detailed(messages, max_tokens=max_tokens, model=model)
        return res.get("reply")

    def plan_json(self, case: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Ask for a plan and parse the first JSON object defensively. The Planner allow-lists the result."""
        prompt = f"Case id: {case.get('id')}. Question: {case.get('question', '')[:500]}"
        text = self.generate(PLANNER_SYSTEM, prompt, max_tokens=1000)
        if not text:
            return None
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
        return obj if isinstance(obj, dict) else None
