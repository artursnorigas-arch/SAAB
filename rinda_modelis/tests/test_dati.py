"""Pārbauda, ka modeļa noklusējuma pieņēmumi sakrīt ar nolasītajiem primārajiem datiem (dati/verificeti_dati.json)."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from params import Params

PATH = os.path.join(os.path.dirname(__file__), "..", "dati", "verificeti_dati.json")
pytestmark = pytest.mark.skipif(not os.path.exists(PATH), reason="nav dati/verificeti_dati.json")
P = Params()


@pytest.fixture(scope="module")
def V():
    return json.load(open(PATH, encoding="utf-8"))


def test_oop_dala_atbilst_eurostat(V):
    hf3 = V["eurostat"]["sha_hf_PC_CHE"]["LV|HF3"]
    avg = sum(hf3[str(y)] for y in range(2019, 2025)) / 6
    assert abs(P.oop_share0 * 100 - avg) < 1.5


def test_apdrosinasanas_dala(V):
    assert abs(P.vhi_share0 * 100 - V["eurostat"]["sha_hf_PC_CHE"]["LV|HF2"]["2024"]) < 1.0


def test_darba_dienas_vertiba(V):
    E = V["eurostat"]
    v = E["ikp_meur"]["LV"]["2024"] * 1e6 / (E["nodarbinati_tuks"]["LV"]["2024"] * 1e3) / 250
    assert abs(P.v_day - v) / v < 0.05


def test_arstu_skaits_nemainigs(V):
    a = V["eurostat"]["arsti_nr"]["PRACT"]
    assert abs((a["2024"] / a["2022"]) ** 0.5 - 1) < 0.01 and P.g_H == 0.0


def test_tarifs_atbilst_nvd_apjomam(V):
    n = V["nvd_ambulatorie"]["2025"]["sava_epizodes_bez_laboratorijas"]
    assert abs(P.tau0 - P.E0 * 1e6 / n) / P.tau0 < 0.05


def test_apjoms_nemainigs(V):
    n = V["nvd_ambulatorie"]
    a, b = n["2023"]["sava_apmeklejumi"], n["2025"]["sava_apmeklejumi"]
    assert abs(b / a - 1) < 0.02            # bāzes scenārijs «reāli nemainīgs finansējums» atbilst faktam


def test_ambulatoro_oop_augsta_robeza(V):
    from model import calibrate
    hc = V["eurostat"]["sha_hc_hf_EUR_HAB"]
    pop = V["eurostat"]["iedzivotaji"]["TOTAL"]["2025"] / 1e6
    upper = hc["LV|HC13_23|HF3"]["2024"] * pop
    c = calibrate(P)
    assert c["D0"] * P.p0 / 1e6 < upper     # specialistu maksas izdevumi nepārsniedz VISU ambulatoro OOP
