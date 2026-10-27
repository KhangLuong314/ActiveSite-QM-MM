"""Bring-your-own-structure flow in the page, against mocked endpoints (the upload backend lives on another branch).

Every request the page makes is answered here by Playwright route interception: the page itself is read from
activesite/server/index.html, CDN scripts are refused, and /api/* returns fixtures. No server and no network.
Skipped when Playwright or its Chromium is not installed:  uv run --with playwright pytest tests/test_ui_upload_flow.py
"""
import json
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

PAGE = Path(__file__).resolve().parents[1] / "activesite" / "server" / "index.html"
ORIGIN = "http://activesite.test"
TINY_PDB = "\n".join([
    "HEADER    MOCK STRUCTURE FOR THE UI TEST",
    "ATOM      1  N   TYR A  61       1.000   0.000   0.000  1.00  0.00           N",
    "ATOM      2  CA  TYR A  61       2.400   0.000   0.000  1.00  0.00           C",
    "ATOM      3  C   TYR A  61       3.000   1.300   0.000  1.00  0.00           C",
    "HETATM    4  C1  LIG A 901       2.000   2.000   1.000  1.00  0.00           C",
    "HETATM    5  N1  LIG A 901       2.800   2.600   1.400  1.00  0.00           N",
    "HETATM    6  O1  LIG A 901       1.300   2.700   0.600  1.00  0.00           O",
    "HETATM    7 MG    MG A 950       4.000   3.000   2.000  1.00  0.00          MG",
    "END", ""])
SUMMARY = {"structure_id": "s_mock1", "name": "my_mutant", "format": "pdb", "n_atoms": 7,
           "chains": [{"id": "A", "n_residues": 1}], "ligands": [{"resname": "LIG", "chain": "A", "resi": 901, "n_heavy_atoms": 3}],
           "metals": [{"resname": "MG", "element": "Mg", "chain": "A", "resi": 950}], "warnings": ["2 alternate locations kept as A"]}
MUTATED = dict(SUMMARY, structure_id="s_mock2", parent_id="s_mock1", applied=[{"chain": "A", "resi": 61, "from": "Y", "to": "F"}],
               method="side chain rebuilt from template, no repacking")
# an uploaded structure in sample mode: the agents decide, the engine does not run, so every energy is null
RESULT = {"stats": {"run_id": "run_mock", "kind": "ligand", "mask": ":LIG", "qmcharge": 0, "retries": 0, "qm_ok": False,
                    "engine_label": "proposal only: engine not run (sample mode)", "qm_escf_kcal": None, "total_energy_kcal": None,
                    "errors": [], "model_mode": "offline", "model_calls": 0, "catalog": "catalog-STANDIN (DuckDB)"},
          "cards": [{"decision_id": "DEC_QM_1", "category": "residue_inclusion", "target": "LIG901", "choice": "Include LIG901",
                     "rationale": "The chosen small molecule.", "confidence": 0.9, "alternatives": [], "evidence": {"source": "mock"}}],
          "validation": {}, "checks": [], "result": {"qm_escf_kcal": None, "total_energy_kcal": None}, "sql": {},
          "report_markdown": "# Report\n\nProposal only.\n"}
STEPS = [{"ts": "2026-10-27T10:00:00", "agent_name": "Planner", "action": "plan", "status": "ok", "output_summary": "3 steps, theory PM6,"},
         {"ts": "2026-10-27T10:00:01", "agent_name": "Orchestrator", "action": "done", "status": "ok", "output_summary": "done"}]


def _sse():
    body = "".join(f"event: step\ndata: {json.dumps(s)}\n\n" for s in STEPS)
    return body + f"event: result\ndata: {json.dumps(RESULT)}\n\n"


def _chromium(p):
    exes = sorted(Path.home().glob("Library/Caches/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell"))
    try:
        return p.chromium.launch(executable_path=str(exes[-1])) if exes else p.chromium.launch()
    except Exception as exc:  # no browser on this machine
        pytest.skip(f"no Chromium for Playwright: {exc}")


def _page(browser, upload_status=200, calls=None):
    calls = [] if calls is None else calls
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    def handle(route):
        url, method = route.request.url, route.request.method
        path = url.split(ORIGIN, 1)[1].split("?")[0] if url.startswith(ORIGIN) else None
        if path is None:
            return route.abort()                      # fonts, CDN scripts: offline on purpose
        calls.append((method, path, route.request.post_data if method == "POST" and "upload" not in path else None))
        if path == "/":
            return route.fulfill(status=200, content_type="text/html", body=PAGE.read_text())
        if path == "/api/cases":
            return route.fulfill(json={"cases": [{"id": "ippoi_site_a", "system": "ippoi_wt", "kind": "metal", "ligand": "", "question": "q"}]})
        if path == "/api/ledger":
            return route.fulfill(json={"memories": [], "ledger": [], "ledger_total": 0})
        if path == "/api/structures/upload":
            return route.fulfill(status=upload_status, json=SUMMARY if upload_status == 200 else {"detail": "Not Found"})
        if path == "/api/structures/s_mock1/mutate":
            return route.fulfill(json=MUTATED)
        if path.startswith("/api/structures/") and path.endswith("/file"):
            return route.fulfill(status=200, content_type="chemical/x-pdb", body=TINY_PDB)
        if path == "/api/run":
            return route.fulfill(json={"stream_id": "stream_mock", "sample_mode": True})
        if path == "/run/stream":
            return route.fulfill(status=200, content_type="text/event-stream", body=_sse())
        return route.fulfill(status=404, json={"detail": "Not Found"})

    page.route("**/*", handle)
    page.goto(ORIGIN + "/?view=simple")
    return page, errors


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        b = _chromium(p)
        yield b
        b.close()


def test_upload_404_degrades_to_one_plain_line(browser):
    page, errors = _page(browser, upload_status=404)
    page.set_input_files("#byoFile", files=[{"name": "x.pdb", "mimeType": "chemical/x-pdb", "buffer": TINY_PDB.encode()}])
    page.wait_for_selector("text=Upload is not available on this server yet")
    assert page.inner_text("#byoBody").strip() == "Upload is not available on this server yet."
    assert page.locator("#flowCases .libitem").count() >= 1          # the library still works
    assert not errors


def test_upload_mutate_run_shows_proposal_only_with_not_computed_chips(browser):
    calls = []
    page, errors = _page(browser, calls=calls)
    page.set_input_files("#byoFile", files=[{"name": "my_mutant.pdb", "mimeType": "chemical/x-pdb", "buffer": TINY_PDB.encode()}])
    page.wait_for_selector("#byoSummary")
    summary = page.inner_text("#byoSummary")
    assert "Chains:" in summary and "A (1 residues)" in summary and "LIG" in summary and "alternate locations" in summary
    # inline validation of the mutation list
    page.fill("#byoMut", "A:Y61")
    assert "not in the form A:Y61F" in page.inner_text("#byoMutErr")
    page.fill("#byoMut", "C:Y61F")
    assert "chain C is not in this file" in page.inner_text("#byoMutErr")
    page.click("#byoRun")
    assert not any(p.endswith("/mutate") for _, p, _ in calls)          # invalid input never reaches the server
    page.fill("#byoMut", "A:Y61F")
    assert page.inner_text("#byoMutErr") == ""
    page.check("input[name=byoTarget][value=l0]")
    page.click("#byoRun")
    page.wait_for_selector("#flowSeeResult:not([hidden])")
    mutate = next(body for m, p, body in calls if p.endswith("/mutate"))
    assert json.loads(mutate) == {"mutations": ["A:Y61F"]}
    run = json.loads(next(body for m, p, body in calls if p == "/api/run"))
    assert run["custom"] == {"structure_id": "s_mock2", "ligand_resname": "LIG", "ligand_smiles": None, "metal_resi": None, "chain": "A", "ph": 7.4}
    page.click("#flowSeeResult")
    head = page.inner_text("#s3h")
    assert "proposal only" in head and "engine was not run" in head
    energy = page.locator("#flowTiles .tile.p-nc").filter(has_text="Energy of the quantum part")
    assert energy.locator(".tv .chip-nc").count() == 1 and "—" in energy.locator(".tv").inner_text()
    assert "your own structure" in page.inner_text("#s3kicker").lower()      # the kicker is uppercased by CSS
    # Expert view shows the same nulls as "not computed"
    page.click("#expertSwitch")
    assert "not computed" in page.inner_text("#metricEnergy")
    assert page.locator("#metricEnergy .chip-nc").count() == 1
    assert page.evaluate("structureIds(lastStats)") == ["upload:s_mock2"]
    assert not errors
