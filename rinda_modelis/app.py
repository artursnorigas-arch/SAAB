"""Interaktīvs modelis «Rinda budžetu neietaupa» – Latvijas ambulatorā specialistu aprūpe.

Palaišana:  streamlit run app.py
"""
from __future__ import annotations

import io
from collections import defaultdict
from dataclasses import replace

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from datu_avoti import SOURCES
from model import calibrate, sensitivity, simulate, summary
from params import PAR_BY_KEY, REGISTRY, STATUS_TEXT, Params, Policy
from scenarios import SCENARIOS

st.set_page_config(page_title="Rindu un maksas aprūpes modelis – Latvija", layout="wide")

C_BASE, C_POL, C_WARN = "#8a8f98", "#1f5fbf", "#c0392b"


# ------------------------------------------------------------------ stāvoklis
def _init():
    for p in REGISTRY:
        st.session_state.setdefault(f"par_{p.key}", p.default * p.scale)
    pol = Policy()
    st.session_state.setdefault("pol_d_tarifs", pol.d_tarifs * 100)
    st.session_state.setdefault("pol_d_apjoms", pol.d_apjoms * 100)
    st.session_state.setdefault("pol_admin_red", pol.admin_red * 100)
    st.session_state.setdefault("pol_ramp", pol.ramp_years)
    st.session_state.setdefault("pol_delay", pol.delay_years)
    st.session_state.setdefault("pol_tarifs_aug", 0.0)
    st.session_state.setdefault("pol_apjoms_aug", 0.0)
    st.session_state.setdefault("pol_fte_aug", 0.0)
    st.session_state.setdefault("pol_fte_lag", pol.fte_lag)
    st.session_state.setdefault("pol_auto", pol.auto_fund)
    st.session_state.setdefault("years", 10)


def _load_preset():
    pol = SCENARIOS[st.session_state["preset"]]
    st.session_state.update(
        pol_d_tarifs=pol.d_tarifs * 100, pol_d_apjoms=pol.d_apjoms * 100, pol_admin_red=pol.admin_red * 100,
        pol_ramp=pol.ramp_years, pol_delay=pol.delay_years, pol_tarifs_aug=pol.tarifs_aug * 100,
        pol_apjoms_aug=pol.apjoms_aug * 100, pol_fte_aug=pol.fte_aug * 100, pol_fte_lag=pol.fte_lag,
        pol_auto=pol.auto_fund)


def current_params() -> Params:
    return Params(**{p.key: st.session_state[f"par_{p.key}"] / p.scale for p in REGISTRY})


def current_policy() -> Policy:
    s = st.session_state
    return Policy(d_tarifs=s.pol_d_tarifs / 100, d_apjoms=s.pol_d_apjoms / 100, admin_red=s.pol_admin_red / 100,
                  ramp_years=s.pol_ramp, delay_years=s.pol_delay, tarifs_aug=s.pol_tarifs_aug / 100,
                  apjoms_aug=s.pol_apjoms_aug / 100, fte_aug=s.pol_fte_aug / 100, fte_lag=s.pol_fte_lag,
                  auto_fund=s.pol_auto)


@st.cache_data(show_spinner=False)
def _sim(P: Params, pol: Policy, years: float) -> pd.DataFrame:
    return simulate(P, pol, years)


@st.cache_data(show_spinner=False)
def _sens(P: Params, pol: Policy, metric: str, swing: float, years: float, keys: tuple) -> pd.DataFrame:
    return sensitivity(P, pol, list(keys), metric, swing, years)


_init()
P, POL, YEARS = current_params(), current_policy(), st.session_state["years"]

# ------------------------------------------------------------------ sānjosla
with st.sidebar:
    st.header("Politikas svirras")
    st.selectbox("Ielādēt gatavu scenāriju", list(SCENARIOS), key="preset", on_change=_load_preset,
                 index=None, placeholder="Izvēlieties scenāriju…")
    st.slider("Tarifa maiņa, %", -40, 100, key="pol_d_tarifs", step=1,
              help="Vidējā valsts tarifa maiņa pret šodienas reālo līmeni.")
    st.slider("Apmaksātā apjoma (kvotas) maiņa, %", -40, 60, key="pol_d_apjoms", step=1)
    st.slider("Administratīvā sloga samazinājums, procentpunkti no darba laika", 0, 15, key="pol_admin_red", step=1)
    st.checkbox("Politikas izmaksas sedz ar papildu naudu", key="pol_auto",
                help="Ja nav atzīmēts: kopbudžets ir fiksēts, tarifa kāpums bez papildu naudas samazina apjomu, "
                     "samazinājums budžetā paliek kā ietaupījums.")
    with st.expander("Ieviešana un daudzgadu plāns"):
        st.slider("Ieviešanas periods, gadi", 0.0, 6.0, key="pol_ramp", step=0.5)
        st.slider("Kavēšanās līdz sākumam, gadi", 0.0, 5.0, key="pol_delay", step=0.5)
        st.slider("Papildu tarifa izaugsme gadā, %", 0.0, 5.0, key="pol_tarifs_aug", step=0.5)
        st.slider("Papildu apjoma izaugsme gadā, %", 0.0, 5.0, key="pol_apjoms_aug", step=0.5)
        st.slider("Papildu ārstu PSE izaugsme gadā (rezidentūra), %", 0.0, 5.0, key="pol_fte_aug", step=0.5)
        st.slider("Kavēšanās līdz jauno ārstu nonākšanai, gadi", 1.0, 10.0, key="pol_fte_lag", step=1.0)
    st.slider("Modelēšanas horizonts, gadi", 3, 20, key="years")
    st.caption("Pieņēmumus (elastības, bāzes dati) maina cilnē «Pieņēmumi».")

st.title("Rinda budžetu neietaupa – modelis Latvijas apstākļiem")
st.caption("LSB teorētiskā modeļa skaitliska realizācija. Ilustratīvs rīks politikas lēmumu salīdzināšanai, **nevis prognoze**: "
           "lielākā daļa ievaddatu ir aptuveni vai pieņēmumi (skatīt cilni «Pieņēmumi» un «Datu avoti»).")

df = _sim(P, POL, YEARS)
base = _sim(P, Policy(), YEARS)
cal = calibrate(P)
for w in cal["warn"]:
    st.warning(w)

tab_res, tab_sc, tab_sens, tab_par, tab_data, tab_meth = st.tabs(
    ["Rezultāti", "Scenāriju salīdzinājums", "Jutīgums", "Pieņēmumi", "Datu avoti", "Metodika"])


def _line(fig, row, col, x, y, name, color, dash=None, **kw):
    fig.add_trace(go.Scatter(x=x, y=y, name=name, mode="lines", line=dict(color=color, dash=dash, width=2.2),
                             showlegend=kw.pop("legend", False), legendgroup=name), row=row, col=col)


# ------------------------------------------------------------------ rezultāti
with tab_res:
    S, B = summary(df, base), summary(base)
    c = st.columns(5)
    c[0].metric("Gaidīšana beigās, mēneši", f"{S['gaidisana_beigas_men']:.1f}",
                f"{S['gaidisana_beigas_men'] - B['gaidisana_beigas_men']:+.1f} pret bāzi", delta_color="inverse")
    c[1].metric("Pacientu tiešo maksājumu daļa", f"{S['oop_dala_beigas']:.1%}",
                f"{(S['oop_dala_beigas'] - B['oop_dala_beigas']) * 100:+.1f} pp pret bāzi", delta_color="inverse")
    c[2].metric("Maksas cena beigās, EUR", f"{S['maksas_cena_beigas']:.0f}",
                f"{S['maksas_cena_beigas'] - B['maksas_cena_beigas']:+.0f} pret bāzi", delta_color="inverse")
    c[3].metric("Novēršamas akūtas hospitalizācijas, tūkst./g.", f"{S['akutie_beigas_tuks']:.0f}",
                f"{S['akutie_beigas_tuks'] - B['akutie_beigas_tuks']:+.0f} pret bāzi", delta_color="inverse")
    c[4].metric("Saistošais ierobežojums beigās", S["saistosais_beigas"])

    x = df.gads
    fig = make_subplots(rows=3, cols=2, vertical_spacing=0.11, subplot_titles=(
        "Gaidīšanas laiks valsts rindā, mēneši", "Maksājošo daļa un tiešo maksājumu daļa",
        "Maksas cena, EUR/epizode", "Ārstu laika daļa valsts darbā",
        "Valsts apmaksātais apjoms: kvota un ārstu kapacitāte, milj.", "Novēršamas akūtas hospitalizācijas, tūkst./g."))
    _line(fig, 1, 1, x, base.gaidisana_men, "Bāze", C_BASE, "dash", legend=True)
    _line(fig, 1, 1, x, df.gaidisana_men, "Izvēlētais scenārijs", C_POL, legend=True)
    fig.add_hline(y=P.W_safe_m, line=dict(color=C_WARN, dash="dot"), row=1, col=1, annotation_text="droša robeža")
    _line(fig, 1, 2, x, base.maksajoso_dala * 100, "Bāze", C_BASE, "dash")
    _line(fig, 1, 2, x, df.maksajoso_dala * 100, "Maksājošo daļa, %", C_POL)
    _line(fig, 1, 2, x, df.oop_dala * 100, "Tiešo maksājumu daļa kopējos izdevumos, %", C_WARN)
    _line(fig, 2, 1, x, base.maksas_cena, "Bāze", C_BASE, "dash")
    _line(fig, 2, 1, x, df.maksas_cena, "Maksas cena", C_POL)
    _line(fig, 2, 1, x, df.tarifs, "Valsts tarifs", "#2e8b57")
    _line(fig, 2, 2, x, base.valsts_laika_dala * 100, "Bāze", C_BASE, "dash")
    _line(fig, 2, 2, x, df.valsts_laika_dala * 100, "Valsts laika daļa, %", C_POL)
    _line(fig, 3, 1, x, df.kvota_milj, "Kvota", "#2e8b57", "dash")
    _line(fig, 3, 1, x, df.kapacitate_valsts_milj, "Ārstu kapacitāte", C_WARN, "dot")
    _line(fig, 3, 1, x, df.apkalpots_valsts_milj, "Faktiski apkalpots", C_POL)
    _line(fig, 3, 2, x, base.akutie_novers_tuks, "Bāze", C_BASE, "dash")
    _line(fig, 3, 2, x, df.akutie_novers_tuks, "Akūtās", C_POL)
    fig.update_layout(height=900, margin=dict(t=60, b=30), legend=dict(orientation="h", y=1.07))
    st.plotly_chart(fig, width="stretch")
    st.caption("Zilā līnija – izvēlētais scenārijs; pelēkā raustītā – «finansējums nemainīgs». "
               "Zaļā raustītā (kvota) un sarkanā punktētā (ārstu kapacitāte): **mazākā no tām ierobežo apkalpoto apjomu** – "
               "tas ir raksta galvenais arguments, kāpēc jāpalielina gan tarifs, gan apjoms.")

    st.subheader("Uzkrātā ietekme pret «finansējums nemainīgs» (milj. EUR, reālās cenas)")
    S2 = summary(df, base)
    k = st.columns(4)
    k[0].metric("Valsts izdevumi", f"{S2['d_valsts_izdevumi']:+,.0f}")
    k[1].metric("Pacientu tiešie maksājumi", f"{S2['d_tiesie_maksajumi']:+,.0f}")
    k[2].metric("Darba zaudējumi (ilustratīvi)", f"{S2['d_prod_zaudejumi']:+,.0f}")
    k[3].metric("Sabiedriskās izmaksas kopā", f"{S2['d_sabiedriskie_kopa']:+,.0f}",
                help="Valsts + pacientu maksājumi + darba zaudējumi. Negatīvs = scenārijs sabiedrībai izdevīgāks nekā bāze.")
    cum = pd.DataFrame({
        "gads": df.gads,
        "Valsts izdevumi": ((df.valsts_kopa - base.valsts_kopa) * 0.25).cumsum(),
        "Pacientu tiešie maksājumi": ((df.tiesie_maksajumi_kopa - base.tiesie_maksajumi_kopa) * 0.25).cumsum(),
        "Darba zaudējumi": ((df.prod_zaudejumi - base.prod_zaudejumi) * 0.25).cumsum()})
    cum["Kopā"] = cum.iloc[:, 1:4].sum(axis=1)
    f2 = go.Figure()
    for col, colr in zip(cum.columns[1:], ["#1f5fbf", "#e08a1e", "#8e5bb5", "#222222"]):
        f2.add_trace(go.Scatter(x=cum.gads, y=cum[col], name=col, line=dict(color=colr, width=3 if col == "Kopā" else 2)))
    f2.add_hline(y=0, line=dict(color="#999", width=1))
    f2.update_layout(height=340, margin=dict(t=20, b=20), yaxis_title="milj. EUR, uzkrāti")
    st.plotly_chart(f2, width="stretch")
    st.caption("Ieguldījums nāk pirms ieguvuma (raksta 2. princips): valsts izdevumu līkne aug uzreiz, ieguvumi uzkrājas vēlāk. "
               "Akūtās palīdzības ietaupījums sedz tikai daļu papildu izdevumu – kā norāda Russell (2009).")

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        df.to_excel(xw, sheet_name="Scenārijs", index=False)
        base.to_excel(xw, sheet_name="Bāze", index=False)
        pd.DataFrame([(p.label, getattr(P, p.key) * p.scale, p.unit, p.status) for p in REGISTRY],
                     columns=["Parametrs", "Vērtība", "Vienība", "Statuss"]).to_excel(xw, sheet_name="Pieņēmumi", index=False)
    st.download_button("Lejupielādēt rezultātus (.xlsx)", buf.getvalue(), "rindu_modelis_rezultati.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ------------------------------------------------------------------ scenāriju salīdzinājums
with tab_sc:
    st.markdown("Visi gatavie scenāriji ar **pašreizējiem pieņēmumiem**. Politikas lielumus katram scenārijam nosaka "
                "`scenarios.py`; tos var pārrakstīt vai pievienot jaunus.")
    pick = st.multiselect("Salīdzināmie scenāriji", list(SCENARIOS), default=list(SCENARIOS)[:6])
    res = {n: _sim(P, SCENARIOS[n], YEARS) for n in pick}
    b0 = _sim(P, SCENARIOS[list(SCENARIOS)[0]], YEARS)
    metric_opts = {"Gaidīšanas laiks, mēneši": "gaidisana_men", "Maksas cena, EUR": "maksas_cena",
                   "Tiešo maksājumu daļa kopējos izdevumos": "oop_dala",
                   "Valsts darba laika daļa": "valsts_laika_dala",
                   "Apkalpotās valsts epizodes, milj.": "apkalpots_valsts_milj",
                   "Novēršamas akūtas hospitalizācijas, tūkst.": "akutie_novers_tuks"}
    m_label = st.selectbox("Rādītājs", list(metric_opts))
    fig3 = go.Figure()
    for n, d in res.items():
        fig3.add_trace(go.Scatter(x=d.gads, y=d[metric_opts[m_label]], name=n[:55], mode="lines"))
    fig3.update_layout(height=430, margin=dict(t=20, b=20), legend=dict(orientation="h", y=-0.25))
    st.plotly_chart(fig3, width="stretch")
    rows = []
    for n, d in res.items():
        s_ = summary(d, b0)
        t3 = d.iloc[int(3 / 0.25)]
        rows.append({"Scenārijs": n, "Gaidīšana 3. g., mēn.": round(t3.gaidisana_men, 1),
                     "Gaidīšana beigās, mēn.": round(s_["gaidisana_beigas_men"], 1),
                     "Saistošais beigās": s_["saistosais_beigas"],
                     "Tiešo maksājumu daļa beigās": f"{s_['oop_dala_beigas']:.1%}",
                     "Δ valsts izd., milj. EUR": round(s_["d_valsts_izdevumi"]),
                     "Δ pacientu maksājumi": round(s_["d_tiesie_maksajumi"]),
                     "Δ darba zaudējumi": round(s_["d_prod_zaudejumi"]),
                     "Δ kopā": round(s_["d_sabiedriskie_kopa"])})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.info("**Kā lasīt.** Ja «Tikai tarifs» un «Tikai apjoms» abi paliek sliktāki par «Kopā» gaidīšanas laikā, modelis apstiprina raksta tēzi. "
            "Ja nē – tas parasti nozīmē, ka elastība `eta` vai kapacitātes rezerve `slack0` ir jāpārbauda pret datiem. "
            "Sabiedrisko izmaksu kolonna ir jutīga pret `ell`, `delta`, `c_ac` – tie ir visneskaidrākie pieņēmumi.")

# ------------------------------------------------------------------ jutīgums
with tab_sens:
    st.markdown("Katrs parametrs tiek mainīts ±X % (pārējie nemainīgi) un mēra izvēlētā scenārija galarezultātu. "
                "Garākās joslas = parametri, kuru precizēšana ar datiem ir visvērtīgākā.")
    cA, cB = st.columns(2)
    swing = cA.slider("Svārstība, ±%", 5, 50, 25) / 100
    sm = cB.selectbox("Rādītājs", ["gaidisana_men", "maksas_cena", "oop_dala", "akutie_novers_tuks"],
                      format_func=lambda k: {"gaidisana_men": "Gaidīšanas laiks beigās, mēn.", "maksas_cena": "Maksas cena beigās",
                                             "oop_dala": "Tiešo maksājumu daļa beigās",
                                             "akutie_novers_tuks": "Akūtās hospitalizācijas beigās"}[k])
    keys = tuple(p.key for p in REGISTRY if p.key not in ("B0", "vhi_share0", "s_lo", "s_hi", "crowd")
                 and getattr(P, p.key) != 0)
    sdf = _sens(P, POL, sm, swing, YEARS, keys)
    sdf["Parametrs"] = sdf.parametrs.map(lambda k: PAR_BY_KEY[k].label[:70])
    sdf["Statuss"] = sdf.parametrs.map(lambda k: PAR_BY_KEY[k].status)
    top = sdf.head(14).iloc[::-1]
    f4 = go.Figure()
    f4.add_trace(go.Bar(y=top.Parametrs, x=top.zems - top.bazes, orientation="h", name=f"−{swing:.0%}", marker_color="#1f5fbf",
                        customdata=top.Statuss, hovertemplate="%{y}<br>Δ %{x:.2f} (statuss %{customdata})<extra></extra>"))
    f4.add_trace(go.Bar(y=top.Parametrs, x=top.augsts - top.bazes, orientation="h", name=f"+{swing:.0%}", marker_color="#e08a1e",
                        customdata=top.Statuss, hovertemplate="%{y}<br>Δ %{x:.2f} (statuss %{customdata})<extra></extra>"))
    f4.update_layout(barmode="overlay", height=520, margin=dict(l=10, t=20, b=20), xaxis_title="Izmaiņa pret pamatvērtību")
    st.plotly_chart(f4, width="stretch")
    st.dataframe(sdf[["Parametrs", "Statuss", "zems", "bazes", "augsts"]].round(2), hide_index=True, width="stretch")

# ------------------------------------------------------------------ pieņēmumi
with tab_par:
    st.markdown("**Statusi:** A – atrasts publiskā avotā, jāapstiprina primārajā dokumentā; B – aptuvens novērtējums; "
                "C – modeļa pieņēmums. Mainiet vērtības – visi grafiki pārrēķinās.")
    if st.button("Atjaunot noklusējuma vērtības"):
        for p in REGISTRY:
            st.session_state[f"par_{p.key}"] = p.default * p.scale
        st.rerun()
    groups = defaultdict(list)
    for p in REGISTRY:
        groups[p.group].append(p)
    for g, ps in groups.items():
        st.subheader(g)
        for p in ps:
            c1, c2 = st.columns([1, 2])
            with c1:
                lo, hi, stp = p.lo * p.scale, p.hi * p.scale, p.step * p.scale
                st.number_input(f"{p.label} [{p.unit}]", float(lo), float(hi), step=float(stp), key=f"par_{p.key}",
                                format="%.4g")
                st.caption(f"`{p.key}` · statuss **{p.status}**")
            with c2:
                st.markdown(f"**Avots / pamatojums:** {p.source}")
                st.markdown(f"**Kāpēc šāda vērtība un ko tā ietekmē:** {p.rationale}")
            st.divider()
    st.subheader("No bāzes datiem atvasinātie lielumi (kalibrācija)")
    st.dataframe(pd.DataFrame([
        ("Valsts apmaksātais apjoms V0, milj. epizodes/g.", cal["V0"] / 1e6),
        ("Nosūtījumi R0, milj./g.", cal["R0"] / 1e6),
        ("Maksas pieprasījums D0, milj./g.", cal["D0"] / 1e6),
        ("Rinda bāzē Q0, tūkst. epizožu", cal["Q0"] / 1e3),
        ("Ārstu laika daļa valsts darbā s0", cal["s0"]),
        ("Epizodes uz PSE gadā", cal["m"]),
        ("Kopējie veselības izdevumi, milj. EUR", cal["the0"]),
        ("Pārējie tiešie maksājumi (zāles, zobi u.c.), milj. EUR", cal["o_other"]),
        ("Novēršamas akūtas hospitalizācijas bāzē, tūkst./g.", cal["A0"] / 1e3)],
        columns=["Lielums", "Vērtība"]).round(3), hide_index=True)

# ------------------------------------------------------------------ datu avoti
with tab_data:
    st.markdown("""
**Datu pieejamības pārbaude.** Izstrādes sesijā visi zemāk minētie serveri (Eurostat, OECD, CSP, NVD, SPKC, data.gov.lv, lvportals, LSM)
**nebija sasniedzami** – vides tīkla politika tos bloķēja. Tāpēc pārbaudīts ir tikai tas, ko izdevās atrast meklētājā
(statuss **A** pie parametriem); pārējais ir balstīts uz zināmu avotu struktūru un **jāapstiprina lokāli**:
palaidiet `python datu_avoti.py`.""")
    st.dataframe(pd.DataFrame(SOURCES)[["avots", "dati", "kods", "piekluve", "modelim", "pieejams_no_zinasanam", "url"]]
                 .rename(columns={"avots": "Avots", "dati": "Dati", "kods": "Kods/datne", "piekluve": "Piekļuve",
                                  "modelim": "Kam modelī", "pieejams_no_zinasanam": "Pieejamība (pēc zināšanām, nepārbaudīta)"}),
                 hide_index=True, width="stretch")
    st.markdown("""
**Kas Latvijā publiski NAV pieejams (jāpieprasa NVD/VM):** svērtais vidējais gaidīšanas laiks pa specialitātēm; tarifu un apjomu sadalījums
pa epizodēm; maksas vizīšu skaits privātajās prakses; ārstu darba laika sadalījums starp valsti un privāto sektoru.
Šīs ir tieši tās vietas, kur raksts atsaucas uz VM un NVD datiem.

**Atrastie fakti (meklētājā, nav pārbaudīti primārajos dokumentos):**
- Veselības nozares budžets 2026. gadam 1,97 mljrd. EUR; speciālistu konsultācijām un izmeklējumiem ambulatori 379,6 milj. EUR; stacionāram 684 milj. EUR (lvportals.lv, 04.12.2025.).
- 2024. gadā NVD administrētais budžets > 1,7 mljrd. EUR (NVD).
- 2024. g. nov.: rindu mazināšanai piešķirti 16 milj. EUR, NVD: rindas nemazinās; galvenais iemesls – speciālistu un naudas trūkums (LSM, 24.11.2024.).
- Tiešo maksājumu daļa: 31,9 % (2020., Sabiedrības veselības pamatnostādnes) un ~27 % (2021., WHO/EK profils); ES vidēji ~15 %. Skaitļi atšķiras pēc definīcijas.
- Rindu uzskaite: iestādes uzrāda rindu dienās, ja gaidīšana >5 darba dienas; dati mēneša pārskatos uz katra mēneša 1. datumu (NVD).
""")

# ------------------------------------------------------------------ metodika
with tab_meth:
    st.markdown(r"""
### Struktūra (ceturkšņa solis, reālie euro)
1. **Ārstu laiks.** Kopējais PSE `H`. Valsts darbam atvēlētā daļa `s` pielāgojas mērķim
   `s* = s0 · ρ^η`, kur `ρ = [τ(1−adm)/p] / [τ0(1−adm0)/p0]` – valsts neto ieņēmuma pret maksas cenu attiecība pret bāzes attiecību.
   Pielāgošanās notiek ar kavēšanos `t_adj`. *(Biglaiser & Ma 2007 – kvalitatīvi.)*
2. **Valsts kapacitāte** `Cap_pub = H·s·m·(1−adm)/(1−adm0)`; **maksas kapacitāte** `Cap_priv = H·(1−s)·m`.
3. **Pieprasījums.** Nosūtījumi `R = R0(1+g_d)^t · (W/W0)^−ξ` (inducētais pieprasījums, Martin & Smith 1999).
   Maksājošo daļa `φ = φ0 · (W/W0)^e_w · ((p/p0)/y)^−e_p` – pacienti maksā, ja rinda gara un cena salīdzinājumā ar ienākumiem pieņemama.
4. **Maksas cena (cenu loks).** `p' = p · exp(λ · ln(φR / Cap_priv))` – pārprasījums paaugstina cenu. Nesaņemtie maksas pakalpojumi atgriežas valsts rindā.
5. **Valsts rinda.** `S = min(kvota, Cap_pub, pieejamie)`; `dQ/dt = R(1−φ) + pārplūde − akūtie − atstāj − S`; `W = Q/S` (Little likums).
6. **Budžeta loks.** Novēršamas akūtas hospitalizācijas `A = δ · Q · max(0, 1 − W_safe/W)`; to izmaksas `c_ac` samazina ambulatoro budžetu
   (izspiešanas koeficients `crowd`), ja kopbudžets fiksēts.
7. **Kvota.** `V = finansējums / τ`; finansējums = min(politikas prasītais, fiksētais budžets − akūtā izspiešana), vai pilnā politikas prasība, ja ieslēgta «papildu nauda».

### Kalibrācija
Bāzes gadā sistēma ir līdzsvarā: nosūtījumi `R0` tiek aprēķināti tā, lai rinda nemainītos; ārstu laika daļa `s0` izriet no apjoma un maksas pieprasījuma,
nevis tiek ievadīta. Tāpēc scenārijs «finansējums nemainīgs» novirzās tikai ārējās dinamikas (`g_d`, `g_y`, `g_H`) dēļ.

### Ko modelis nedara
- Neprognozē. Tas nesatur kalibrāciju pret Latvijas vēsturiskajām rindu laika rindām (dati nav publiski pieejami).
- Neaplūko primāro aprūpi, stacionāro, medikamentus; tie ir fiksēti.
- Nesadala pa specialitātēm un reģioniem – viens agregēts «vidējais specialists».
- Izlaiž kvalitāti, nevienlīdzību pēc ienākumiem (augstāk apdrošinātie, maksātspējīgie) – tā ir nākamā modeļa kārta.
- Darba zaudējumu ieguvums (cilne «Rezultāti») ir ilustratīvs un atkarīgs no `ell`, kam nav Latvijas novērtējuma.
""")
