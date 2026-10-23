"""ModelClient: no key -> None and no HTTP; with httpx mocked -> parsed reply; plan_json parses defensively."""
import httpx
import pytest

from activesite import llm as llm_mod
from activesite.llm import ModelClient


def test_without_key_no_call(monkeypatch):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)

    def boom(*a, **k):
        raise AssertionError("HTTP must not be called without a key")

    monkeypatch.setattr(llm_mod.httpx, "post", boom)
    c = ModelClient()
    assert c.available is False and c.generate("s", "p") is None and c.plan_json({"id": "x"}) is None and c.calls == 0
    assert c.base_url == "https://integrate.api.nvidia.com/v1" and c.model == "nvidia/llama-3.3-nemotron-super-49b-v1"


def test_with_key_parses_reply(monkeypatch):
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, json=json, headers=headers)
        return httpx.Response(200, json={"choices": [{"message": {"content": 'ok {"steps": ["gather_data"], "theory": "PM6"} end'}}]},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(llm_mod.httpx, "post", fake_post)
    c = ModelClient(base_url="https://example.test/v1/", api_key="k", model="m")
    assert c.generate("sys", "hello", max_tokens=50).startswith("ok")
    assert seen["url"] == "https://example.test/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer k" and seen["json"]["temperature"] == 0.1
    assert seen["json"]["model"] == "m" and seen["json"]["max_tokens"] == 50
    assert seen["json"]["messages"][0] == {"role": "system", "content": "sys"}
    assert c.plan_json({"id": "x"}) == {"steps": ["gather_data"], "theory": "PM6"} and c.calls == 2


def test_errors_fall_back_to_none(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        return httpx.Response(500, text="boom", request=httpx.Request("POST", url))

    monkeypatch.setattr(llm_mod.httpx, "post", fake_post)
    c = ModelClient(api_key="k")
    assert c.generate("s", "p") is None and "HTTPStatusError" in c.last_error
