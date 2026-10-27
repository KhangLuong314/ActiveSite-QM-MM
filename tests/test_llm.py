"""ModelClient: no key -> None and no HTTP; with httpx mocked -> parsed reply; plan_json parses defensively."""
import httpx

from activesite import llm as llm_mod
from activesite.llm import ModelClient


def test_without_key_no_call(monkeypatch):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_NAME", raising=False)
    monkeypatch.delenv("NEMOTRON_MODEL", raising=False)

    def boom(*a, **k):
        raise AssertionError("HTTP must not be called without a key")

    monkeypatch.setattr(llm_mod.httpx, "post", boom)
    c = ModelClient()
    assert c.available is False and c.generate("s", "p") is None and c.plan_json({"id": "x"}) is None and c.calls == 0
    assert c.base_url == "https://integrate.api.nvidia.com/v1" and c.model == "nvidia/llama-3.3-nemotron-super-49b-v1"


def test_nemotron_model_env_var_respected(monkeypatch):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_NAME", raising=False)
    monkeypatch.setenv("NEMOTRON_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")
    c = ModelClient()
    assert c.model == "nvidia/nemotron-3.5-lightning-30b-a3b"


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


def _chat_client(monkeypatch, replies):
    """ModelClient whose chat endpoint returns the given (message, finish_reason) pairs in order."""
    budgets = []

    def fake_post(url, json=None, headers=None, timeout=None):
        budgets.append(json["max_tokens"])
        msg, finish = replies[min(len(budgets), len(replies)) - 1]
        return httpx.Response(200, json={"choices": [{"message": msg, "finish_reason": finish}]},
                              request=httpx.Request("POST", url))

    monkeypatch.setenv("MODEL_API_KEY", "k")
    monkeypatch.setattr(llm_mod.httpx, "post", fake_post)
    return ModelClient(), budgets


def test_chat_retries_with_larger_budget_when_cut_off(monkeypatch):
    c, budgets = _chat_client(monkeypatch, [({"content": "The charge is +1 because"}, "length"),
                                            ({"content": "The charge is +1 because the MM sum is 1.032 e."}, "stop")])
    out = c.chat_detailed([{"role": "user", "content": "why +1?"}], max_tokens=2500)
    assert out["reply"] == "The charge is +1 because the MM sum is 1.032 e."
    assert budgets == [2500, 7500]


def test_chat_never_returns_reasoning_as_the_answer(monkeypatch):
    # live Nemotron: the whole budget went on reasoning, content is empty both times
    c, _ = _chat_client(monkeypatch, [({"content": "", "reasoning_content": "Let me map the cards. I'll note"}, "length")])
    out = c.chat_detailed([{"role": "user", "content": "explain"}])
    assert out["reply"] is None and out["thinking"].startswith("Let me map")


def test_chat_unclosed_think_tag_is_not_shown(monkeypatch):
    c, _ = _chat_client(monkeypatch, [({"content": "<think>Okay, the user wants the energy split. I'll"}, "length")])
    assert c.chat_detailed([{"role": "user", "content": "energy?"}])["reply"] is None


def test_chat_still_cut_off_after_retry_says_so(monkeypatch):
    c, _ = _chat_client(monkeypatch, [({"content": "Part one of a long answer"}, "length")])
    reply = c.chat_detailed([{"role": "user", "content": "long"}])["reply"]
    assert reply.startswith("Part one") and reply.endswith("(answer cut off at the length limit)")
