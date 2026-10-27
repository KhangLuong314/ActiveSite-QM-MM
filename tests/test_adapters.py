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


def test_scout_ensure_pdb_downloads_when_missing(tmp_path, monkeypatch):
    import httpx
    scout = DataScout(cache_dir=tmp_path)
    target = tmp_path / "4zau.pdb"
    assert not target.exists()

    dummy_pdb_text = "HEADER    TEST PDB 4ZAU\nATOM      1  N   MET A   1       0.000   0.000   0.000  1.00 20.00           N\nEND\n"

    def fake_get(self, url, *args, **kwargs):
        assert "4zau.pdb" in str(url)
        return httpx.Response(200, text=dummy_pdb_text, request=httpx.Request("GET", str(url)))

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    result = scout.ensure_pdb(target)
    assert result.exists()
    assert result.read_text() == dummy_pdb_text
