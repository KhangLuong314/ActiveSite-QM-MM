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
