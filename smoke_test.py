"""ActiveSite — Open Agent Hackathon 2026 Official Smoke Test.

Validates the Participant Setup Guide's 3-layer architecture:
- Check 1 (Data): Zetaris web interface (via ZETARIS_BASE_URL)
- Check 2 (Data): Zetaris REST API query (POST /sql-editor/sqls/run sending 'SELECT 1')
- Check 3 (Power): NVIDIA Nemotron / Meterless model response (via openai SDK)
"""
from __future__ import annotations

import os
import sys
import uuid
from typing import Tuple
from dotenv import load_dotenv
import requests
from openai import OpenAI

load_dotenv()


def check_zetaris_web(base_url: str | None = None) -> Tuple[bool, str]:
    """Check 1 (Data): Zetaris web interface."""
    url = base_url if base_url is not None else os.getenv("ZETARIS_BASE_URL", "http://localhost:3000")
    try:
        resp = requests.get(url, timeout=10.0)
        if resp.status_code < 400:
            return True, f"HTTP {resp.status_code}"
        return False, f"HTTP {resp.status_code} - {resp.text[:100].strip()}"
    except Exception as exc:
        return False, str(exc)


def check_zetaris_rest(
    rest_url: str | None = None,
    api_key: str | None = None,
    org_id: str | None = None,
) -> Tuple[bool, str]:
    """Check 2 (Data): Zetaris REST API query."""
    base = rest_url if rest_url is not None else os.getenv("ZETARIS_REST_URL", "http://localhost:8888/api/v1.0")
    key = api_key if api_key is not None else os.getenv("ZETARIS_API_KEY", "")
    org = org_id if org_id is not None else os.getenv("ZETARIS_ORG_ID", "1")
    req_id = str(uuid.uuid4())

    url = f"{base.rstrip('/')}/sql-editor/sqls/run"
    headers = {
        "Authorization": f"Bearer {key}",
        "X-Org-ID": str(org),
        "X-Request-ID": req_id,
        "Content-Type": "application/json",
    }
    payload = {
        "sql": "SELECT 1",
        "queryId": str(uuid.uuid4()),
        "source": "SqlEditor",
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15.0)
        if resp.status_code == 200:
            return True, "Query successful (HTTP 200)"
        if resp.status_code == 400:
            # Fallback attempt with minimal payload {"sql": "SELECT 1"}
            resp_min = requests.post(
                url, headers=headers, json={"sql": "SELECT 1"}, timeout=15.0
            )
            if resp_min.status_code == 200:
                return True, "Query successful (HTTP 200)"
        return False, f"HTTP {resp.status_code} - {resp.text[:150].strip()}"
    except Exception as exc:
        return False, str(exc)


def check_power_model(
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> Tuple[bool, str]:
    """Check 3 (Power): NVIDIA Nemotron / Meterless model response."""
    url = base_url if base_url is not None else os.getenv("MODEL_BASE_URL", "https://integrate.api.nvidia.com/v1")
    key = api_key if api_key is not None else os.getenv("MODEL_API_KEY", "")
    model_name = model if model is not None else os.getenv(
        "NEMOTRON_MODEL", "nvidia/llama-3.1-nemotron-70b-instruct"
    )

    if not key or key == "your-nvidia-api-key-or-meterless-token":
        return False, "MODEL_API_KEY not configured"

    try:
        client = OpenAI(base_url=url, api_key=key, timeout=20.0)
        resp = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "Reply with the single word: ready"}],
            max_tokens=10,
        )
        content = (resp.choices[0].message.content or "").strip()
        return True, f"Response: {content}"
    except Exception as exc:
        return False, str(exc)


def main() -> int:
    """Run the official 3-layer validation logic and print standard PASS/FAIL results."""
    all_passed = True

    # Check 1 (Data): Zetaris web interface
    web_ok, web_msg = check_zetaris_web()
    if web_ok:
        print("PASS Data (Zetaris Web UI)")
    else:
        print(f"FAIL Data (Zetaris Web UI) {web_msg}")
        all_passed = False

    # Check 2 (Data): Zetaris REST API query
    rest_ok, rest_msg = check_zetaris_rest()
    if rest_ok:
        print("PASS Data (Zetaris REST API)")
    else:
        print(f"FAIL Data (Zetaris REST API) {rest_msg}")
        all_passed = False

    # Check 3 (Power): NVIDIA Nemotron / Meterless model response
    power_ok, power_msg = check_power_model()
    if power_ok:
        print("PASS Power (NVIDIA Nemotron)")
    else:
        print(f"FAIL Power (NVIDIA Nemotron) {power_msg}")
        all_passed = False

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
