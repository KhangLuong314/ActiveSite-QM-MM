# Test fixtures

- `sander_ok.out`, `sander_odd.out`: verbatim sander mdouts copied from `data/sample/ippoi_site_a/attempt1/sp.out`
  (qmcharge +1, PM6 ESCF -456.5628 kcal/mol) and `attempt0/sp.out` (qmcharge 0, odd-electron error, 203 electrons).
  Real engine runs from the in-window sample generation; they replace the earlier hand-written parser fixtures.
- `methanol.mol2`, `methanol.sdf`: small ligand files for the prep parser tests.
