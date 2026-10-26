"""Chat replies may only state numbers a run produced (AGENTS.md rule 2).

The provenance guard marks any unit-bearing number that is neither in the run context nor a method setting.
These tests send every preset question in the UI through /api/chat with no model key (rule-based path) and
require zero unverified numbers, and check that unsupported systems get no numbers at all.
"""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from activesite.server import main
from activesite.server.provenance import FLAG, guard

PRESETS = re.findall(r"sendQuickQuery\('([^']+)'\)", Path("activesite/server/index.html").read_text())


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "")
    return TestClient(main.app)


def test_guard_flags_numbers_not_in_the_run():
    ctx = {"stats": {"qm_escf_kcal": -456.5628, "total_energy_kcal": -302060.0}}
    text, flagged = guard("ESCF -456.5628 kcal/mol, total -302060.00 kcal/mol, barrier 18.43 kcal/mol, contact 4.0 Å", ctx)
    assert flagged == ["18.43 kcal/mol"]
    assert text.count(FLAG) == 1 and "18.43 kcal/mol" + FLAG in text


def test_presets_exist():
    assert len(PRESETS) >= 5


@pytest.mark.parametrize("question", PRESETS)
def test_every_preset_reply_has_only_run_numbers(client, question):
    r = client.post("/api/chat", json={"message": question}).json()
    assert r["unverified_numbers"] == [], r["unverified_numbers"]
    assert FLAG not in r["reply"]


@pytest.mark.parametrize("question", ["Set up EcoRV endonuclease with Mg and give its PM6 energy",
                                      "Set up TEM-1 beta-lactamase with benzylpenicillin"])
def test_unsupported_systems_get_no_numbers(client, question):
    reply = client.post("/api/chat", json={"message": question}).json()["reply"]
    assert "not one of ActiveSite's supported cases" in reply
    assert not re.search(r"\d+(\.\d+)?\s*(kcal|Å)", reply)


def test_fallback_is_not_labelled_as_a_model(client):
    r = client.post("/api/chat", json={"message": "who are you"}).json()
    assert r["source"] == "rule_based_fallback" and r["model"].startswith("none")


def test_context_has_no_typed_in_results():
    ctx = main.get_current_simulation_context("ippoi_site_a")
    st = ctx.get("stats") or {}
    assert st.get("qm_escf_kcal") in (None, pytest.approx(-456.5628)) and st.get("qmcharge") in (None, 1)
    assert main.get_current_simulation_context("ecorv_endonuclease").get("supported") is False
