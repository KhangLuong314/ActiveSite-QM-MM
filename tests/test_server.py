"""Unit tests for FastAPI endpoints and server main."""
import pytest
from fastapi.testclient import TestClient
from activesite.server.main import app

client = TestClient(app)


def test_get_dashboard_html():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "ActiveSite" in resp.text
    assert "Track 02" in resp.text


def test_api_list_cases():
    resp = client.get("/api/cases")
    assert resp.status_code == 200
    data = resp.json()
    assert "cases" in data
    assert len(data["cases"]) >= 3
    case_ids = [c["id"] for c in data["cases"]]
    assert "egfr_erlotinib" in case_ids


def test_api_run_simulation_case():
    resp = client.post("/api/run", json={"case_id": "egfr_erlotinib", "sample_mode": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["system_name"] == "egfr_erlotinib"
    assert "decision_cards" in data
    assert len(data["decision_cards"]) >= 4
    assert data["energy_kcal_mol"] < 0


def test_api_get_ledger():
    resp = client.get("/api/ledger")
    assert resp.status_code == 200
    data = resp.json()
    assert "records" in data
    assert len(data["records"]) >= 1
