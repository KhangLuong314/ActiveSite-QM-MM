# Test fixtures

- `sander_ok.out`, `sander_odd.out`: verbatim sander mdouts copied from `data/sample/ippoi_site_a/attempt1/sp.out`
  (qmcharge +1, PM6 ESCF -456.5628 kcal/mol) and `attempt0/sp.out` (qmcharge 0, odd-electron error, 203 electrons).
  Real engine runs from the in-window sample generation; they replace the earlier hand-written parser fixtures.
- `methanol.mol2`, `methanol.sdf`: small ligand files for the prep parser tests.
- `egfr_1m17_pocket.pdb`: cut from `data/reference/egfr/1m17.pdb` (RCSB 1M17): its REMARK 465 lines, chain A residues
  718-721 and 764-772 (hinge, Thr766 gatekeeper, Met769), the erlotinib ligand AQ4 A999 and the first 3 waters, coordinates
  unchanged. Used by `tests/test_custom_structures.py`; tests append synthetic SO4 / MG lines in-test where needed.
