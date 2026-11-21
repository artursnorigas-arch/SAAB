"""Gatavi scenāriji – atbilst raksta «Kāpēc puspasākumi nedarbosies» argumentiem.

Lielumi (tarifs +40 %, apjoms +15 %) ir ilustratīvi: tarifam jābūt pietiekami augstam, lai ārstu laiks
valsts darbā palielinātos līdzvērtīgi apjoma kāpumam (modelī – līdz s_hi robežai). Lietotājs tos maina lietotnē.
"""
from params import Policy

SCENARIOS: dict[str, Policy] = {
    "0. Bāze: finansējums nemainīgs": Policy(auto_fund=False),
    "1. Samazina tarifu un apjomu (−10 % / −10 %)": Policy(d_tarifs=-0.10, d_apjoms=-0.10, auto_fund=False),
    "2. Tikai tarifs (+40 %)": Policy(d_tarifs=0.40, auto_fund=True),
    "3. Tikai apjoms (+15 %)": Policy(d_apjoms=0.15, auto_fund=True),
    "4. Tarifs un apjoms kopā (+40 % / +15 %)": Policy(d_tarifs=0.40, d_apjoms=0.15, auto_fund=True),
    "5. Kopā + administratīvais slogs −5 pp": Policy(d_tarifs=0.40, d_apjoms=0.15, admin_red=0.05, auto_fund=True),
    "6. Daudzgadu plāns: kā 5. + tarifs +1 %/g., apjoms +1,5 %/g., ārstu PSE +1,5 %/g. pēc 5 gadiem":
        Policy(d_tarifs=0.40, d_apjoms=0.15, admin_red=0.05, tarifs_aug=0.01, apjoms_aug=0.015,
               fte_aug=0.015, fte_lag=5, auto_fund=True),
}
