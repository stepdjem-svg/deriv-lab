import os, sys, random, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from phase2 import statistician, auditor, developer, orchestrator

class Fake:
    def __init__(self):
        self.calls = {}
    def call(self, req):
        k = next(iter(req))
        sym = req.get(k) if isinstance(req.get(k), str) else (req.get("underlying_symbol") or req.get("symbol"))
        self.calls[(k, sym)] = self.calls.get((k, sym), 0) + 1
        if k == "contracts_for":
            return {"contracts_for": {"available": [{"contract_type": "CALL", "contract_category": "callput",
                    "barrier_category": "euro_atm", "min_contract_duration": "5t", "max_contract_duration": "10t"}]}}
        if k == "proposal":
            return {"proposal": {"ask_price": 1.0, "payout": 1.95}}
        if k == "ticks_history":
            rnd = random.Random(7)
            p, x = [], 100.0
            for _ in range(5000):
                x += rnd.gauss(0, 1); p.append(round(x, 3))
            return {"history": {"prices": p}}
        return {}

def test_stat_small_sample():
    assert statistician.evaluate(5, 10, 0.5)["verdict"] == "INSUFFISANT"

def test_stat_no_edge():
    assert statistician.evaluate(500, 1000, 0.513, n_tests=10)["verdict"].startswith("AUCUN")

def test_stat_edge():
    assert statistician.evaluate(700, 1000, 0.513, n_tests=10)["verdict"].startswith("AVANTAGE")

def test_auditor_leak():
    res = {"train_end": 10, "test_start": 5}
    ev = {"n": 500, "verdict": "AUCUN", "p_adj": 1}
    assert any("fuite" in i for i in auditor.audit(res, ev, 3, {"source": "proposal"}))

def test_auditor_secret():
    assert auditor.has_secret("ghp_" + "A" * 30)
    assert not auditor.has_secret("ghp_FAKE_TEST_0000")

def test_outcomes_simple():
    w, n = developer.outcomes([1, 2, 3, 4, 5, 6, 7], 1, 1)
    assert n > 0 and w == n

def test_orchestrator_resume():
    api = Fake()
    with tempfile.TemporaryDirectory() as base:
        orchestrator.run(api, base, symbols=["A", "B"])
        a_before = api.calls[("proposal", "A")]
        rep = orchestrator.run(api, base, symbols=["A", "B", "C"])
        assert api.calls[("proposal", "A")] == a_before == 1
        assert rep["n_tradable"] == 3 and rep["n_tests"] == 3


class Pager:
    N = 12000
    def call(self, req):
        end = len(range(self.N)) if req["end"] == "latest" else int(req["end"]) + 1
        start = max(0, end - min(req["count"], 1500))
        idx = list(range(start, end))
        return {"history": {"prices": [100.0 + i * 0.001 for i in idx], "times": idx}}

def test_fetch_ticks_pagination():
    p = developer.fetch_ticks(Pager(), "X", target=6000)
    assert len(p) >= 6000 and len(p) == len(set(p))
