"""Suite-wide settings: keep the DuckDB stand-in offline and the model client keyless."""
import os

os.environ.setdefault("CATALOG_OFFLINE", "1")
os.environ.pop("MODEL_API_KEY", None)
os.environ.pop("ZETARIS_REST_URL", None)
os.environ.pop("ZETARIS_API_KEY", None)
