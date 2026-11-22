"""Sagatavo vienas datnes HTML lapu `web/rindu_modelis.html` no šablona, model.js un parametru reģistra.

    python web/build_html.py

Lapā ir tas pats parametru reģistrs (params.py), scenāriji (scenarios.py) un pārbaudītie dati
(dati/verificeti_dati.json); modeļa kodu veido web/model.js (sakritību ar Python pārbauda tests).
"""
import dataclasses
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from params import REGISTRY, STATUS_TEXT  # noqa: E402
from scenarios import SCENARIOS  # noqa: E402


def build() -> str:
    data = dict(
        registry=[dict(key=p.key, label=p.label, unit=p.unit, default=p.default, lo=p.lo, hi=p.hi, step=p.step, group=p.group,
                       status=p.status, source=p.source, rationale=p.rationale, scale=p.scale) for p in REGISTRY],
        status_text=STATUS_TEXT,
        scenarios=[dict(name=n, policy=dataclasses.asdict(pol)) for n, pol in SCENARIOS.items()],
        verified=json.load(open(os.path.join(HERE, "..", "dati", "verificeti_dati.json"), encoding="utf-8")),
    )
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
    model = open(os.path.join(HERE, "model.js"), encoding="utf-8").read().replace("</", "<\\/")
    html = html.replace("/*@@MODEL_JS@@*/", model).replace("/*@@DATA@@*/", blob)
    return html


if __name__ == "__main__":
    out = os.path.join(HERE, "rindu_modelis.html")
    open(out, "w", encoding="utf-8").write(build())
    print("Saglabāts:", out, os.path.getsize(out) // 1024, "KB")
