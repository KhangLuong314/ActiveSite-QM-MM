"""Unit tests for the official 3-layer smoke test."""
import pytest
from unittest.mock import MagicMock, patch
from smoke_test import check_power_model, check_zetaris_rest, check_zetaris_web, main


def test_check_zetaris_web_mock_pass():
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        ok, msg = check_zetaris_web("http://fake-host:3000")
        assert ok is True
        assert "HTTP 200" in msg


def test_check_zetaris_web_mock_fail():
    with patch("requests.get") as mock_get:
        mock_get.side_effect = ConnectionError("Connection refused")

        ok, msg = check_zetaris_web("http://fake-host:3000")
        assert ok is False
        assert "Connection refused" in msg


def test_check_zetaris_rest_mock_pass():
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        ok, msg = check_zetaris_rest(
            rest_url="http://fake-host:8888/api/v1.0",
            api_key="mock-key",
            org_id="1",
        )
        assert ok is True
        assert "200" in msg


def test_check_zetaris_rest_mock_fail():
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        mock_post.return_value = mock_resp

        ok, msg = check_zetaris_rest(
            rest_url="http://fake-host:8888/api/v1.0",
            api_key="bad-key",
            org_id="1",
        )
        assert ok is False
        assert "401" in msg


def test_check_power_model_mock_pass():
    with patch("smoke_test.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "ready"
        mock_resp.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_resp
        mock_openai_cls.return_value = mock_client

        ok, msg = check_power_model(
            base_url="https://fake-nvidia.com/v1",
            api_key="mock-key",
            model="nvidia/llama-3.1-nemotron-70b-instruct",
        )
        assert ok is True
        assert "ready" in msg


def test_check_power_model_missing_key():
    ok, msg = check_power_model(api_key="")
    assert ok is False
    assert "not configured" in msg


def test_smoke_test_main_pass(capsys):
    with patch("smoke_test.check_zetaris_web", return_value=(True, "OK")), \
         patch("smoke_test.check_zetaris_rest", return_value=(True, "OK")), \
         patch("smoke_test.check_power_model", return_value=(True, "OK")):
        code = main()
        assert code == 0
        captured = capsys.readouterr()
        assert "PASS Data (Zetaris Web UI)" in captured.out
        assert "PASS Data (Zetaris REST API)" in captured.out
        assert "PASS Power (NVIDIA Nemotron)" in captured.out
