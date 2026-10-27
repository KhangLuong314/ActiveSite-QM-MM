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


def _sse(steps=None, result=None):
    body = "".join(f"event: step\ndata: {json.dumps(s)}\n\n" for s in (steps or STEPS))
    return body + f"event: result\ndata: {json.dumps(result or RESULT)}\n\n"


# The event sequence the real backend sends for an uploaded structure in sample mode (1m17 + A:T766M, 2026-10-27).
_PROPOSAL = "proposal only: engine not run (sample mode); uploaded structures are never replayed from cached output"
REAL_STEPS = [
    {"agent_name": "Planner", "action": "plan", "status": "ok", "output_summary": "6 steps, theory PM6, mode fallback"},
    {"agent_name": "LigandSetup", "action": "prep", "status": "skipped", "output_summary": _PROPOSAL},
    {"agent_name": "LigandCritic", "action": "precheck", "status": "blocked", "output_summary": "flagged ['prep_available']; BLOCKING ['prep_available']"},
    {"agent_name": "Orchestrator", "action": "blocked", "status": "error", "output_summary": "QM/MM not run: " + _PROPOSAL},
    {"agent_name": "LigandCritic", "action": "validate", "status": "ok", "output_summary": "no minimised model; validation skipped"},
    {"agent_name": "Orchestrator", "action": "done", "status": "ok", "output_summary": "qm_ok False, blocked ['prep_available'], memory_used True"}]
REAL_RESULT = json.loads(json.dumps(RESULT))
REAL_RESULT["stats"].update(blocked=["prep_available"], sample_mode=True, errors=["blocked by prep_available: " + _PROPOSAL],
                            custom={"structure_id": "s_mock1", "name": "my_mutant", "mutations": ["A:Y61F"]})
REAL_RESULT["validation"] = {"published": 0, "recovered": {}, "missed": [], "expected_absent": {}, "extra": [], "contacts": [], "available": False}
REAL_RESULT["checks"] = [{"name": "prep_available", "passed": False, "detail": _PROPOSAL}]


def _chromium(p):
    exes = sorted(Path.home().glob("Library/Caches/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell"))
    try:
        return p.chromium.launch(executable_path=str(exes[-1])) if exes else p.chromium.launch()
    except Exception as exc:  # no browser on this machine
        pytest.skip(f"no Chromium for Playwright: {exc}")


def _page(browser, upload_status=200, calls=None, run_error=None, steps=None, result=None):
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
        if path == "/api/run" and run_error:
            return route.fulfill(status=422, json={"detail": run_error})
        if path == "/api/run":
            return route.fulfill(json={"stream_id": "stream_mock", "sample_mode": True})
        if path == "/run/stream":
            return route.fulfill(status=200, content_type="text/event-stream", body=_sse(steps, result))
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


@pytest.mark.parametrize("pick, detail", [
    ("m0", "metal sites from uploaded files: QM-region proposal not supported yet"),
    ("l0", [{"loc": ["body", "custom", "ligand_smiles"], "msg": "ligand_smiles is required for a ligand the server does not know", "type": "value_error"}]),
])
def test_run_422_is_shown_as_a_plain_message(browser, pick, detail):
    page, errors = _page(browser, run_error=detail)
    page.set_input_files("#byoFile", files=[{"name": "m.pdb", "mimeType": "chemical/x-pdb", "buffer": TINY_PDB.encode()}])
    page.wait_for_selector("#byoSummary")
    page.check(f"input[name=byoTarget][value={pick}]")
    page.click("#byoRun")
    page.wait_for_selector("#flowRetry:not([hidden])")
    want = detail if isinstance(detail, str) else detail[0]["msg"]
    assert f"Your structure could not be run: {want}" in page.inner_text("#flowChecklist")
    assert "[object Object]" not in page.inner_text("body")
    page.click("#flowRetry")
    assert want in page.inner_text("#byoRunErr")
    assert not errors


INTERNALS = ("BLOCKING", "];", "['", "could not finish", "prep available")


def test_expected_sample_mode_stop_is_information_not_an_error(browser):
    page, errors = _page(browser, steps=REAL_STEPS, result=REAL_RESULT)
    page.set_input_files("#byoFile", files=[{"name": "my_mutant.pdb", "mimeType": "chemical/x-pdb", "buffer": TINY_PDB.encode()}])
    page.wait_for_selector("#byoSummary")
    page.click("#byoRun")
    page.wait_for_selector("#flowSeeResult:not([hidden])")
    s2 = page.inner_text("#flowChecklist")
    assert not [x for x in INTERNALS if x in s2], s2
    assert page.locator("#flowChecklist li.c-bad").count() == 0
    info = page.locator("#flowChecklist li.c-info").all_inner_texts()
    assert any("Preparation and the energy step need Docker; in sample mode the agents stop after proposing the setup." in t for t in info)
    assert any("No energy was computed: this is a proposal only" in t for t in info)
    assert "your uploaded structure" in s2 and "published structure" not in s2
    assert page.inner_text("#flowStatus") == "Proposal only" and "warn" in page.get_attribute("#flowStatus", "class")
    page.click("#flowSeeResult")
    s3 = page.inner_text("#screen3")
    assert not [x for x in INTERNALS if x in s3] and "safety check" not in s3 and "published data" not in s3
    page.click("#expertSwitch")
    page.evaluate("document.querySelector('#traceFold').open = true")
    assert page.locator("#stages .st.error").count() == 0 and page.locator("#thoughtStream .ev.bad").count() == 0
    assert "BLOCKING" not in page.inner_text("#thoughtStream") and "];" not in page.inner_text("#thoughtStream")
    assert page.locator("#pipeline .node.fail").count() == 0
    assert not errors


def test_real_block_stays_red_in_plain_words_and_sanitizer(browser):
    page, errors = _page(browser)
    page.evaluate("customRun = null; flow.running = true; flow.lines = []; flow.seen = new Set()")
    page.evaluate("""() => {
      flowStep({agent_name: 'LigandCritic', action: 'precheck', status: 'blocked', output_summary: "flagged ['pocket_built', 'ligand_charge_sum']; BLOCKING ['pocket_built']"});
      flowStep({agent_name: 'Orchestrator', action: 'blocked', status: 'error', output_summary: 'QM/MM not run: blocked by pocket_built: ligand moved 4.2 A'});
      flowStep({agent_name: 'Mystery', action: 'odd_step', status: 'failed', output_summary: "x ['a', 'b']; BLOCKING ['a']"});
    }""")
    bad = page.locator("#flowChecklist li.c-bad").all_inner_texts()
    assert len(bad) == 3
    assert "The Critic stopped the run before the calculation: “the drug sits in its crystal pocket” did not hold." in bad[0]
    assert "The run stopped before the calculation: “the drug sits in its crystal pocket” did not hold." in bad[1]
    text = page.inner_text("#flowChecklist")
    assert "BLOCKING" not in text and "];" not in text and "['" not in text
    assert page.evaluate("plainInternals(\"flagged ['a', 'b']; BLOCKING ['a']\")") == "flagged a, b; blocking a"
    assert page.evaluate("expectedStop({action: 'precheck', output_summary: \"flagged ['prep_available']; BLOCKING ['prep_available']\"})") is False
    assert not errors
