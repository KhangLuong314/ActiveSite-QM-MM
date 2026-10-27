"""The 3D viewer must get the case's own active site, never another protein as a fallback."""
import re

from fastapi.testclient import TestClient

from activesite.server import main
from activesite.server.structures import SERIALS_REMARK, metal_site_pdb


def _atoms(text):
    return {int(line[6:11]): (line[12:16].strip(), line[17:20].strip(), int(line[22:26]))
            for line in text.splitlines() if line.startswith(("ATOM", "HETATM"))}


def test_ippoi_site_is_the_real_system_with_topology_numbering():
    text = metal_site_pdb("ippoi_site_a").read_text()
    atoms = _atoms(text)
    assert SERIALS_REMARK in text and "1M17" not in text
    assert atoms[410] == ("P", "DG", 14) and atoms[409][0] == "O3'"         # the scissile P-O3' of the reaction coordinate
    assert any(resn == "MG" and resi == 371 for _, resn, resi in atoms.values())


def test_agent_qm_mask_selects_exactly_its_atoms():
    mask = "@385-416,5256-5266,5587-5594,6229,6255-6266"     # the agent's site-A QM region (64 atoms)
    serials = set(_atoms(metal_site_pdb("ippoi_site_a").read_text()))
    ranges = [tuple(map(int, p.split("-"))) if "-" in p else (int(p), int(p)) for p in mask[1:].split(",")]
    assert sum(1 for s in serials if any(lo <= s <= hi for lo, hi in ranges)) == 64


def test_endpoint_serves_the_site_and_refuses_unsupported_cases():
    c = TestClient(main.app)
    r = c.get("/api/structure/ippoi_site_b")
    assert r.status_code == 200 and SERIALS_REMARK in r.text
    assert re.search(r"MG\s+\S?\s*372", r.text) or " 372 " in r.text
    assert c.get("/api/structure/ecorv_endonuclease").status_code == 404
