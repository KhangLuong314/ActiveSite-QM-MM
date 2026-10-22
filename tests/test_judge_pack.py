"""Judge pack consistency: metadata.json, README and docs/PRE_EXISTING.md agree, and nothing unpickles reference data."""
import json
import re
from pathlib import Path

ROOT = Path(".")


def test_metadata_points_at_real_modules():
    meta = json.loads((ROOT / "metadata.json").read_text())
    assert meta["track"].startswith("Track 02")
    for sponsor, text in meta["sponsor_technologies"].items():
        paths = re.findall(r"(activesite/[\w/]+\.py|docs/[\w/]+\.md|\.cursorrules|\.cursor/mcp\.json)", text)
        assert paths, sponsor
        for p in paths:
            assert (ROOT / p).exists(), f"{sponsor}: {p} missing"
    assert (ROOT / meta["pre_existing_components"]).exists()
    assert "cached engine output (sample mode)" in meta["sample_mode"]["behaviour"]


def test_readme_and_metadata_agree():
    readme = (ROOT / "README.md").read_text()
    meta = json.loads((ROOT / "metadata.json").read_text())
    for needle in ("catalog-STANDIN (DuckDB)", "cached engine output (sample mode)", "Pre-existing components and data",
                   "## Limitations", "SAMPLE_MODE=true uv run python run.py --case ippoi_site_a", "uv run python run.py --server",
                   "docs/PRE_EXISTING.md", "scripts/make_samples.sh", meta["models"]["llm"].split(" ")[0]):
        assert needle in readme, needle
    for sponsor in meta["sponsor_technologies"]:
        assert sponsor.split(" ")[0] in readme, sponsor


def test_every_reference_file_is_declared():
    declared = (ROOT / "docs/PRE_EXISTING.md").read_text() + (ROOT / "README.md").read_text()
    for path in sorted((ROOT / "data/reference").rglob("*")):
        if path.is_file() and path.name != "LARGE_FILES.sha256":
            assert path.name in declared, f"{path} is not declared as pre-existing"


def test_no_pickle_loading_and_hash_manifest():
    for py in list((ROOT / "activesite").rglob("*.py")) + [ROOT / "run.py"] + list((ROOT / "seed").rglob("*.py")):
        src = py.read_text()
        assert "pickle" not in src and "np.load(" not in src and "barrier_res_table" not in src, py
    manifest = (ROOT / "data/reference/LARGE_FILES.sha256").read_text().splitlines()
    assert len(manifest) == 5 and all(len(l.split()[0]) == 64 for l in manifest)


def test_samples_have_inputs_and_outputs_are_never_handwritten():
    for case in ("ippoi_site_a", "ippoi_site_b", "egfr_erlotinib"):
        inp = json.loads((ROOT / "samples" / case / "input.json").read_text())
        assert inp["id"] == case
        report = ROOT / "samples" / case / "report.md"
        if report.exists():  # only make_samples.sh may create it, and it stamps the manifest
            manifest = (ROOT / "data/sample/MANIFEST.md").read_text()
            assert "commit:" in manifest and "Not generated yet" not in manifest
            assert "cached engine output (sample mode)" in report.read_text()
