"""Testi: modeļa iekšējā konsekvence un raksta teorijas kvalitatīvie apgalvojumi."""
import os
import sys
from dataclasses import replace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from model import calibrate, simulate, summary
from params import PAR_BY_KEY, REGISTRY, Params, Policy

P = Params()


def run(pol=None, years=10, p=P):
    return simulate(p, pol or Policy(), years)


# ---------- kalibrācija un iekšējā konsekvence ----------
def test_statika_ir_lidzsvara():
    d = simulate(replace(P, g_d=0.0, g_y=0.0), Policy(), 8)
    assert d.gaidisana_men.iloc[-1] == pytest.approx(P.W0m, rel=1e-6)
    assert d.maksas_cena.iloc[-1] == pytest.approx(P.p0, rel=1e-6)
    assert d.valsts_laika_dala.iloc[-1] == pytest.approx(calibrate(P)["s0"], rel=1e-6)


def test_bazes_stavoklis_atbilst_ievadam():
    d = run(years=0.25)
    r = d.iloc[0]
    assert r.valsts_kopa == pytest.approx(P.B0, rel=1e-9)
    assert r.oop_dala == pytest.approx(P.oop_share0, rel=1e-9)
    assert r.valsts_ambulatori == pytest.approx(P.E0, rel=1e-9)


def test_fiziskie_ierobezojumi():
    for pol in (Policy(), Policy(d_tarifs=0.4, d_apjoms=0.15, auto_fund=True), Policy(d_tarifs=-0.1, d_apjoms=-0.1)):
        d = run(pol, 15)
        assert (d.rinda_tuks >= 0).all()
        assert (d.apkalpots_valsts_milj <= d.kvota_milj + 1e-9).all()
        assert (d.apkalpots_valsts_milj <= d.kapacitate_valsts_milj + 1e-9).all()
        assert (d.maksas_epizodes_milj <= d.maksas_kapacitate_milj + 1e-9).all()
        assert d.valsts_laika_dala.between(P.s_lo - 1e-9, P.s_hi + 1e-9).all()


def test_registrs_robezas():
    for p in REGISTRY:
        assert p.lo <= p.default <= p.hi, p.key
        assert p.status in ("V", "A", "B", "C")
        assert p.source and p.rationale


# ---------- raksta teorija ----------
def test_apburtie_loki_pie_nemainiga_finansejuma():
    """Bez izmaiņām: rinda garāka, vairāk maksā paši, maksas cena kāpj, ārsti aiziet uz maksas darbu, akūtie pieaug."""
    d = run()
    a, b = d.iloc[0], d.iloc[-1]
    assert b.gaidisana_men > a.gaidisana_men
    assert b.maksajoso_dala > a.maksajoso_dala
    assert b.maksas_cena > a.maksas_cena          # cenu loks
    assert b.valsts_laika_dala < a.valsts_laika_dala
    assert b.akutie_novers_tuks > a.akutie_novers_tuks   # budžeta loks
    assert b.oop_dala > a.oop_dala


def test_budzeta_loks_izspiez_ambulatoro_finansejumu():
    d = run()
    assert d.kvota_milj.iloc[-1] < d.kvota_milj.iloc[0]
    # ja izspiešanas nav, kvota netiek samazināta
    d0 = run(p=replace(P, crowd=0.0))
    assert d0.kvota_milj.iloc[-1] == pytest.approx(d0.kvota_milj.iloc[0])


def test_tikai_tarifs_kvota_saistosa_un_rinda_nesaisinasies():
    d = run(Policy(d_tarifs=0.40, auto_fund=True))
    early = d.iloc[: int(5 / 0.25)]
    assert (early.saistosais == "kvota/nauda").all()
    assert early.valsts_laika_dala.iloc[-1] > P.s_lo and early.valsts_laika_dala.iloc[-1] > d.valsts_laika_dala.iloc[0]  # ārsti atgriežas
    assert early.apkalpots_valsts_milj.max() == pytest.approx(d.kvota_milj.iloc[0])                # apjoms nepieaug
    base = run()
    assert d.gaidisana_men.iloc[int(3 / 0.25)] >= d.gaidisana_men.iloc[0] * 0.98                   # rinda nesaīsinās


def test_tikai_apjoms_ierobezo_arstu_kapacitate():
    d = run(Policy(d_apjoms=0.15, auto_fund=True))
    row = d.iloc[int(3 / 0.25)]
    assert row.saistosais == "ārstu kapacitāte"
    assert row.apkalpots_valsts_milj < row.kvota_milj - 0.1       # kvota paliek neizmantota


def test_kopa_labak_par_katru_atseviski_vidusperioda():
    t = int(3 / 0.25)
    w_tarifs = run(Policy(d_tarifs=0.40, auto_fund=True)).gaidisana_men.iloc[t]
    w_apjoms = run(Policy(d_apjoms=0.15, auto_fund=True)).gaidisana_men.iloc[t]
    w_kopa = run(Policy(d_tarifs=0.40, d_apjoms=0.15, auto_fund=True)).gaidisana_men.iloc[t]
    assert w_kopa < w_tarifs
    assert w_kopa <= w_apjoms + 0.1


def test_samazinajums_pasliktina_un_parcel_izdevumus_uz_pacientu():
    base, cut = run(), run(Policy(d_tarifs=-0.10, d_apjoms=-0.10))
    s = summary(cut, base)
    assert s["d_valsts_izdevumi"] < 0                 # budžetā «ietaupījums»
    assert s["d_tiesie_maksajumi"] > 0                # ... pārceļas uz pacienta maku
    assert s["d_prod_zaudejumi"] > 0                  # ... un uz darbaspēka zaudējumiem
    assert cut.gaidisana_men.iloc[-1] > base.gaidisana_men.iloc[-1] or \
        cut.gaidisana_men.iloc[int(5 / 0.25)] > base.gaidisana_men.iloc[int(5 / 0.25)]


def test_administrativais_slogs_palidz():
    a = run(Policy(d_tarifs=0.4, d_apjoms=0.15, auto_fund=True))
    b = run(Policy(d_tarifs=0.4, d_apjoms=0.15, admin_red=0.05, auto_fund=True))
    t = int(4 / 0.25)
    assert b.gaidisana_men.iloc[t] <= a.gaidisana_men.iloc[t]


def test_ieguldijums_pirms_ietaupijuma_J_lokne():
    """Raksta 2. princips: izmaksas rodas uzreiz, ieguvums (akūtie, produktivitāte) – vēlāk/mazāks."""
    base = run()
    pol = run(Policy(d_tarifs=0.40, d_apjoms=0.15, auto_fund=True))
    d_cost = pol.valsts_kopa - base.valsts_kopa
    assert d_cost.iloc[int(1 / 0.25)] > 0
    d_acute = pol.akutie_izmaksas - base.akutie_izmaksas
    assert d_acute.iloc[1] <= 0 + 1e-9
    # papildu nauda pilnībā neatmaksājas ar akūtās palīdzības ietaupījumu (Russell 2009)
    cum_cost = (d_cost.iloc[:-1] * 0.25).sum()
    cum_acute_saving = -(d_acute.iloc[:-1] * 0.25).sum()
    assert cum_cost > cum_acute_saving


def test_jutiba_pret_elastibu():
    """Ja ārsti pret tarifu nereaģē (eta≈0), tarifa kāpums neatgriež ārstu laiku."""
    d = simulate(replace(P, eta=0.1), Policy(d_tarifs=0.4, auto_fund=True), 6)
    d2 = simulate(replace(P, eta=1.2), Policy(d_tarifs=0.4, auto_fund=True), 6)
    assert d2.valsts_laika_dala.max() > d.valsts_laika_dala.max()


def test_ricibas_atbilstiba_eksogenajam():
    """Palielināta vajadzības izaugsme pasliktina situāciju."""
    lo = simulate(replace(P, g_d=0.005), Policy(), 10).gaidisana_men.iloc[-1]
    hi = simulate(replace(P, g_d=0.025), Policy(), 10).gaidisana_men.iloc[-1]
    assert hi > lo
