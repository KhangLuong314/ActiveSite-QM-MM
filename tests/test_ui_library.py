"""The page's system library must say only what the repo can show (status chips are claims, not decoration)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "activesite" / "server" / "index.html").read_text()


def _meta():
    m = re.search(r'<script type="application/json" id="libraryMeta">(.*?)</script>', HTML, re.S)
    assert m, "libraryMeta block missing"
    return json.loads(m.group(1))


def test_every_case_file_is_in_the_library_and_nothing_else():
    ids = {s["id"] for s in _meta()["systems"]}
    assert ids == {p.stem for p in (ROOT / "cases").glob("*.json")}


def test_status_chips_follow_repo_facts():
    groups = {g["id"] for g in _meta()["groups"]}
    for s in _meta()["systems"]:
        case = json.loads((ROOT / "cases" / f"{s['id']}.json").read_text())
        sample = (ROOT / "data" / "sample" / s["id"]).is_dir()
        assert s["group"] in groups
        if s["status"] in ("verified", "replay"):
            assert sample, f"{s['id']}: a replayable or verified run needs data/sample/{s['id']}"
        if s["status"] == "docker":
            assert not sample, f"{s['id']}: has a sample, so it can be replayed"
        if s["status"] == "verified" and s.get("basis") == "literature":
            src = case.get("literature_source", "")
            assert src and "not yet cited" not in src, f"{s['id']}: literature claim needs a cited source"
        if s["status"] == "verified" and s.get("basis") == "expert":
            assert case.get("metal_resid") and case.get("parm7"), f"{s['id']}: expert comparison needs the lab topology case"
        if s.get("pdb"):
            assert s["pdb"].lower() in (case.get("pdb", "") + case.get("question", "")).lower()
    by_id = {s["id"]: s["status"] for s in _meta()["systems"]}
    assert by_id["ecorv_endonuclease"] == "unsupported"


def test_page_loads_no_new_scripts_and_keeps_chat_presets():
    srcs = re.findall(r'<script[^>]+src="([^"]+)"', HTML)
    assert srcs == ["https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js", "https://cdnjs.cloudflare.com/ajax/libs/3Dmol/2.0.4/3Dmol-min.js"]
    assert len(re.findall(r"sendQuickQuery\('([^']+)'\)", HTML)) == 7
