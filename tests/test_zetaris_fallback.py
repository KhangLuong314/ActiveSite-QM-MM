"""Zetaris outage during a run must degrade to the labelled stand-in, never to empty results labelled 'zetaris'."""
import httpx

from activesite.adapters.zetaris import ResilientCatalog, ZetarisAdapter, get_adapter


class FakeStandin:
    label = "catalog-STANDIN (DuckDB)"
    tables = {"lab_runs": "pg.public.lab_runs", "eda": "eda_synthetic", "pdb": "rcsb_entries"}

    def __init__(self):
        self.queries = []

    def prepare(self, case):
        self.prepared = case

    def run_sql(self, sql):
        self.queries.append(sql)
        return [{"source": "standin"}]


def _zetaris(monkeypatch, behaviour):
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append(json["sql"])
        return behaviour(json["sql"], len(calls))

    monkeypatch.setattr(httpx, "post", fake_post)
    return ZetarisAdapter(base_url="http://zetaris.test/api", api_key="k", org_id="1"), calls


def _ok(rows):
    return httpx.Response(200, json=rows, request=httpx.Request("POST", "http://zetaris.test"))


def test_unreachable_zetaris_falls_back_with_honest_label(monkeypatch):
    def refuse(sql, n):
        raise httpx.ConnectError("refused")
    primary, _ = _zetaris(monkeypatch, refuse)
    cat = ResilientCatalog(primary=primary, fallback_factory=FakeStandin)
    cat.prepare({"id": "ippoi_site_a"})
    assert cat.run_sql("SELECT * FROM pg.public.lab_runs") == [{"source": "standin"}]
    assert cat.label == "catalog-STANDIN (DuckDB) (Zetaris unreachable: ConnectError)"
    assert cat.tables["eda"] == "eda_synthetic" and cat.active.prepared == {"id": "ippoi_site_a"}


def test_reachable_zetaris_is_used_and_labelled(monkeypatch):
    primary, calls = _zetaris(monkeypatch, lambda sql, n: _ok([{"x": 1}]))
    cat = ResilientCatalog(primary=primary, fallback_factory=FakeStandin)
    assert cat.label == "zetaris"
    assert cat.run_sql("SELECT * FROM lab_runs") == [{"x": 1}]
    assert calls == ["SELECT 1", "SELECT * FROM lab_runs"]


def test_zetaris_dropping_mid_run_switches_and_translates_tables(monkeypatch):
    def flaky(sql, n):
        if n == 1:
            return _ok([{"1": 1}])
        raise httpx.ReadTimeout("slow")
    primary, _ = _zetaris(monkeypatch, flaky)
    cat = ResilientCatalog(primary=primary, fallback_factory=FakeStandin)
    assert cat.label == "zetaris"
    cat.run_sql("SELECT residue FROM eda_residues")
    assert cat.active.queries == ["SELECT residue FROM eda_synthetic"]
    assert "Zetaris unreachable: ReadTimeout" in cat.label


def test_get_adapter_wraps_zetaris_only_when_configured(monkeypatch):
    monkeypatch.delenv("ZETARIS_REST_URL", raising=False)
    monkeypatch.delenv("ZETARIS_API_KEY", raising=False)
    assert not isinstance(get_adapter(), ResilientCatalog)
    monkeypatch.setenv("ZETARIS_REST_URL", "http://127.0.0.1:9/api")
    monkeypatch.setenv("ZETARIS_API_KEY", "k")
    assert isinstance(get_adapter(), ResilientCatalog)
