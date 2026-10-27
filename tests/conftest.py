"""Suite-wide settings: keep the DuckDB stand-in offline and the model client keyless.

The stand-in's RCSB/EDA cache and the sample-mode cache are pointed at empty per-session directories so the
suite behaves the same whether or not data/cache/ and data/sample/ have been populated by real runs in this checkout.
Tests that need cached material create it themselves (tests/test_sample_mode.py) or opt back in explicitly.
"""
import os
import tempfile
from pathlib import Path

_ISOLATED = Path(tempfile.mkdtemp(prefix="activesite-tests-"))
os.environ.setdefault("CATALOG_OFFLINE", "1")
os.environ.setdefault("ACTIVESITE_CACHE_DIR", str(_ISOLATED / "cache"))
os.environ.pop("MODEL_API_KEY", None)
os.environ.pop("ZETARIS_REST_URL", None)
os.environ.pop("ZETARIS_API_KEY", None)


import pytest  # noqa: E402

# activesite.llm and activesite.server.main call load_dotenv() on import, which can put a developer's real
# keys back into the environment after the pops above. Clear them before every test so the suite never
# talks to live services or spends API credit; tests that need a value set it with monkeypatch.setenv.
SPONSOR_VARS = ("MODEL_API_KEY", "MODEL_BASE_URL", "MODEL_NAME", "NEMOTRON_MODEL", "NVIDIA_API_KEY", "OPENAI_API_KEY",
                "ZETARIS_REST_URL", "ZETARIS_API_KEY", "ZETARIS_ORG_ID", "ZETARIS_BASE_URL", "ZETARIS_USER", "ZETARIS_PASSWORD",
                "ZETARIS_TABLE_LAB_RUNS", "ZETARIS_TABLE_EDA", "ZETARIS_TABLE_PDB",
                "METERLESS_API_KEY", "METERLESS_ENDPOINT")


@pytest.fixture(autouse=True)
def _no_developer_secrets(monkeypatch):
    for name in SPONSOR_VARS:
        monkeypatch.delenv(name, raising=False)
