"""Unit tests for DataScout (case loading and PDB resolution)."""
from activesite.adapters.scout import DataScout


def test_scout_list_and_load_cases():
    scout = DataScout()
    cases = scout.list_benchmark_cases()
    assert "egfr_erlotinib" in cases
    assert "ippoi_site_a" in cases

    egfr_case = scout.load_benchmark_case("egfr_erlotinib")
    assert egfr_case["id"] == "egfr_erlotinib"
    assert egfr_case["ligand"] == "AQ4"
    assert egfr_case["ph"] == 7.4


def test_scout_resolve_local_pdb():
    scout = DataScout()
    # Resolve EGFR 1M17 pdb from local reference
    meta = scout.resolve_pdb("1m17")
    assert meta.identifier == "1M17"
    assert meta.is_offline_cached is True
    assert meta.local_pdb_path is not None
    assert "AQ4" in meta.ligands or len(meta.ligands) > 0
