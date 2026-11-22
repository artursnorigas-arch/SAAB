"""JavaScript modelis (web/model.js) dod tādus pašus rezultātus kā Python modelis (model.py)."""
import dataclasses
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from model import calibrate, sensitivity, simulate, summary
from params import Params, Policy
from scenarios import SCENARIOS

ROOT = os.path.join(os.path.dirname(__file__), "..")
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="nav node")

COLS = ["gaidisana_men", "rinda_tuks", "maksajoso_dala", "maksas_cena", "valsts_laika_dala", "apkalpots_valsts_milj",
        "kvota_milj", "kapacitate_valsts_milj", "akutie_novers_tuks", "valsts_kopa", "tiesie_maksajumi_kopa", "oop_dala",
        "prod_zaudejumi", "tarifs"]

JS = """
const RM = require(process.argv[1] + '/web/model.js');
const inp = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = {};
for (const [name, pol] of Object.entries(inp.policies)) out[name] = RM.simulate(inp.P, pol, inp.years);
out.__sens = RM.sensitivity(inp.P, inp.policies.__sens, inp.keys, 'gaidisana_men', 0.25, 10);
out.__cal = RM.calibrate(inp.P);
console.log(JSON.stringify(out));
"""


def run_js(P, policies, years=10, keys=("eta", "g_d", "p0")):
    pol = {**{n: dataclasses.asdict(p) for n, p in policies.items()}, "__sens": dataclasses.asdict(Policy(d_tarifs=0.4, d_apjoms=0.15, auto_fund=True))}
    r = subprocess.run(["node", "-e", JS, os.path.abspath(ROOT)], input=json.dumps(dict(P=dataclasses.asdict(P), policies=pol, years=years, keys=list(keys))),
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


@pytest.mark.parametrize("P", [Params(), Params(g_d=0.03, eta=1.1, crowd=0.4, g_B=0.01, W0m=7, phi0=0.4)])
def test_visi_scenariji_sakrit(P):
    js = run_js(P, SCENARIOS, 12)
    for name, pol in SCENARIOS.items():
        py = simulate(P, pol, 12)
        rows = js[name]
        assert len(rows) == len(py)
        for col in COLS:
            for a, b in zip(py[col], [r[col] for r in rows]):
                assert b == pytest.approx(a, rel=1e-9, abs=1e-9), (name, col)
        assert [r["saistosais"] for r in rows] == list(py["saistosais"])


def test_kopsavilkums_un_jutiba_un_kalibracija():
    P = Params()
    js = run_js(P, SCENARIOS)
    c = calibrate(P)
    for k in ("V0", "R0", "D0", "s0", "m", "o_other", "the0"):
        assert js["__cal"][k] == pytest.approx(c[k], rel=1e-12)
    sens = sensitivity(P, Policy(d_tarifs=0.4, d_apjoms=0.15, auto_fund=True), ["eta", "g_d", "p0"], "gaidisana_men", 0.25, 10)
    for (_, r), j in zip(sens.iterrows(), js["__sens"]):
        assert j["parametrs"] == r.parametrs
        assert j["zems"] == pytest.approx(r.zems, rel=1e-9)
        assert j["augsts"] == pytest.approx(r.augsts, rel=1e-9)


def test_html_lapa_sagatavota():
    sys.path.insert(0, os.path.join(ROOT, "web"))
    from build_html import build
    html = build()
    assert "/*@@" not in html and "function simulate" in html and "registry" in html
    assert "<title>" in html and "</script>" in html
