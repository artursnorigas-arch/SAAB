"""Rindu un maksas aprūpes modelis Latvijas ambulatorajai specialistu aprūpei.

Modelis realizē LSB raksta «Rinda budžetu neietaupa» teoriju sistēmdinamikas formā
(ceturkšņa solis, reālie euro, bāzes gads 2026):

  1. Ārstu laiks ir ierobežots un dalās starp valsts un maksas darbu.
     Valsts darbam atvēlētā laika daļa s mainās līdz ar attiecību tarifs / maksas cena.
  2. Cenu loks: vairāk maksājošo → pārprasījums maksas segmentā → cena kāpj → ārsts
     pāriet uz maksas darbu → valsts rinda garāka → vairāk maksājošo.
  3. Budžeta loks: gaidīšana pāri drošajai robežai → novēršamas akūtas hospitalizācijas →
     akūtā palīdzība izspiež ambulatoro finansējumu.
  4. Valsts apmaksāto epizožu skaitu ierobežo MIN(kvota/nauda, ārstu kapacitāte).
     Tāpēc tikai tarifa vai tikai apjoma maiņa neatrisina abus ierobežojumus.

Kalibrācija: bāzes gadā sistēma ir līdzsvarā; novirzi rada tikai ārējā dinamika (vajadzības
pieaugums, ienākumi) un politikas svirras. Tas ļauj šo modeli lietot kā «ja nekas nemainās»
salīdzinājuma līniju.
"""
from __future__ import annotations

import math
from dataclasses import replace

import pandas as pd

from params import Params, Policy

EPS = 1e-9


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def calibrate(P: Params) -> dict:
    """Aprēķina sākuma stāvokli un atvasinātos lielumus no bāzes datiem."""
    tau0, p0 = P.tau0, P.p0
    V0 = P.E0 * 1e6 / tau0                       # valsts apmaksātais apjoms (epizodes/gadā)
    S0 = V0                                      # bāzē apkalpotas tieši kvotas apmērā
    W0 = P.W0m / 12.0
    Ws = P.W_safe_m / 12.0
    Q0 = W0 * S0                                 # Little likums: rinda = gaidīšanas laiks × plūsma
    A0 = P.delta * Q0 * max(0.0, 1.0 - Ws / W0)  # novēršamas akūtas hospitalizācijas bāzē
    R0 = (S0 + A0 + P.h_ab * Q0) / (1.0 - P.phi0)  # nosūtījumi gadā, lai rinda bāzē nemainītos
    D0 = P.phi0 * R0                             # maksas pieprasījums
    cap_pub0 = S0 * P.slack0
    cap_priv0 = D0                               # maksas tirgus bāzē tīrās (cena līdzsvarā)
    s0 = cap_pub0 / (cap_pub0 + cap_priv0)       # ārstu laika daļa valsts darbā (atvasināta)
    m = (cap_pub0 + cap_priv0) / P.H0            # epizodes uz PSE gadā

    the0 = P.B0 / (1.0 - P.oop_share0 - P.vhi_share0)   # kopējie veselības izdevumi (milj. EUR)
    oop0 = P.oop_share0 * the0
    oop_amb0 = D0 * p0 / 1e6
    o_other = oop0 - oop_amb0                    # pārējie tiešie maksājumi (zāles, zobi u.c.), nemainīgi
    vhi = P.vhi_share0 * the0
    acute_cost0 = A0 * P.c_ac / 1e6
    pub_other = P.B0 - P.E0 - acute_cost0        # pārējie publiskie izdevumi, nemainīgi
    warn = []
    if o_other < 0:
        warn.append("Ambulatoro maksas izdevumu apjoms pārsniedz kopējo OOP: samaziniet phi0/p0 vai paaugstiniet OOP daļu.")
    if not (P.s_lo <= s0 <= P.s_hi):
        warn.append(f"Atvasinātā bāzes valsts laika daļa s0={s0:.2f} ir ārpus [s_lo, s_hi].")
    return dict(V0=V0, S0=S0, W0=W0, Ws=Ws, Q0=Q0, A0=A0, R0=R0, D0=D0, cap_pub0=cap_pub0,
                cap_priv0=cap_priv0, s0=s0, m=m, the0=the0, oop0=oop0, o_other=max(o_other, 0.0),
                vhi=vhi, acute_cost0=acute_cost0, pub_other=pub_other, warn=warn)


def simulate(P: Params, pol: Policy | None = None, years: float = 10, dt: float = 0.25,
             base_year: int = 2026) -> pd.DataFrame:
    """Palaiž modeli un atgriež ceturkšņa datus (naudas rādītāji – milj. EUR gadā, plūsmas – uz gadu)."""
    pol = pol or Policy()
    c = calibrate(P)
    tau0, p0 = P.tau0, P.p0
    n = int(round(years / dt))

    s, p, Q = c["s0"], p0, c["Q0"]
    W_prev = c["W0"]
    acute_cost_prev = c["acute_cost0"]
    rows = []

    for k in range(n + 1):
        t = k * dt
        # --- politika (pakāpeniska ieviešana) ---
        if pol.ramp_years > 0:
            ramp = _clip((t - pol.delay_years) / pol.ramp_years, 0.0, 1.0)
        else:
            ramp = 1.0 if t >= pol.delay_years else 0.0
        tp = max(t - pol.delay_years, 0.0)
        tau = tau0 * (1 + pol.d_tarifs * ramp) * (1 + pol.tarifs_aug) ** tp
        adm = max(0.0, P.adm0 - pol.admin_red * ramp)
        adm_factor = (1 - adm) / (1 - P.adm0)

        H = P.H0 * (1 + P.g_H) ** t * (1 + pol.fte_aug) ** max(t - pol.fte_lag, 0.0)
        y = (1 + P.g_y) ** t

        # --- finansējums un apjoms ---
        V_pol = c["V0"] * (1 + P.g_B) ** t * (1 + pol.d_apjoms * ramp) * (1 + pol.apjoms_aug) ** tp
        required = V_pol * tau
        if pol.auto_fund:
            funded = required                      # politikas izmaksas sedz papildu nauda
        else:                                      # fiksēts kopbudžets: pārsniegumu nesedz, samazinājumu ietaupa
            alloc = min(P.E0 * 1e6 * (1 + P.g_B) ** t, required)
            funded = max(alloc - P.crowd * max(acute_cost_prev - c["acute_cost0"], 0.0) * 1e6, 0.0)
        V = funded / tau

        # --- pieprasījums ---
        R_trend = c["R0"] * (1 + P.g_d) ** t
        R = R_trend * (max(W_prev, 0.02) / c["W0"]) ** (-P.xi)
        phi = _clip(P.phi0 * (max(W_prev, 0.02) / c["W0"]) ** P.e_w * ((p / p0) / y) ** (-P.e_p), 0.02, 0.9)
        D_priv = phi * R

        # --- kapacitāte ---
        cap_pub = H * s * c["m"] * adm_factor
        cap_priv = H * (1 - s) * c["m"]
        priv_del = min(D_priv, cap_priv)
        spill = D_priv - priv_del                 # nesaņēmušie maksas pakalpojumu atgriežas valsts rindā

        # --- valsts rinda ---
        inflow = R * (1 - phi) + spill
        A_av = P.delta * Q * max(0.0, 1.0 - c["Ws"] / max(W_prev, EPS))
        ab = P.h_ab * Q * (max(W_prev, EPS) / c["W0"])      # atstāj rindu (intensitāte aug ar gaidīšanu)
        ab = min(ab, Q / dt)
        S = min(V, cap_pub, max(inflow - A_av - ab + Q / dt, 0.0))
        Q_new = max(Q + dt * (inflow - A_av - ab - S), 0.0)
        W = Q / max(S, 1.0)                       # gaidīšanas laiks gados (Little likums)

        # --- izmaksas ---
        acute_cost = A_av * P.c_ac / 1e6
        pub_amb = S * tau / 1e6
        public_total = c["pub_other"] + pub_amb + acute_cost
        oop_amb = priv_del * p / 1e6
        oop_total = c["o_other"] + oop_amb
        the = public_total + oop_total + c["vhi"]
        q_excess = Q * max(0.0, 1.0 - c["Ws"] / max(W, EPS))
        prod_loss = q_excess * P.ell * P.emp * P.v_day / 1e6

        rows.append(dict(
            laiks=t, gads=base_year + t,
            gaidisana_men=W * 12, rinda_tuks=Q / 1e3,
            maksajoso_dala=phi, maksas_cena=p, cena_pret_bazi=p / p0,
            valsts_laika_dala=s, ARSTU_PSE=H,
            nosutijumi_milj=R / 1e6, apkalpots_valsts_milj=S / 1e6, kvota_milj=V / 1e6,
            kapacitate_valsts_milj=cap_pub / 1e6, maksas_epizodes_milj=priv_del / 1e6,
            maksas_kapacitate_milj=cap_priv / 1e6, parplūsme_milj=spill / 1e6,
            saistosais=("ārstu kapacitāte" if cap_pub < V - 1 else "kvota/nauda"),
            akutie_novers_tuks=A_av / 1e3, atstaj_rindu_tuks=ab / 1e3, akutie_izmaksas=acute_cost,
            valsts_ambulatori=pub_amb, valsts_kopa=public_total,
            tiesie_maksajumi_amb=oop_amb, tiesie_maksajumi_kopa=oop_total,
            kopeji_izdevumi=the, oop_dala=oop_total / the,
            prod_zaudejumi=prod_loss, tarifs=tau, nepieciesamais_finansejums=required / 1e6,
            ieklauts_finansejums=funded / 1e6,
        ))

        # --- stāvokļa atjaunināšana ---
        lam_ratio = D_priv / max(cap_priv, 1.0)
        p = _clip(p * math.exp(P.lam * dt * math.log(max(lam_ratio, 1e-6))), 0.5 * p0, 4.0 * p0)
        rho = (tau * (1 - adm) / p) / (tau0 * (1 - P.adm0) / p0)
        s_star = _clip(c["s0"] * rho ** P.eta, P.s_lo, P.s_hi)
        s = s + (s_star - s) * (1 - math.exp(-dt / P.t_adj))
        Q = Q_new
        W_prev = W
        acute_cost_prev = acute_cost

    return pd.DataFrame(rows)


def run_scenarios(P: Params, scenarios: dict[str, Policy], years: float = 10) -> dict[str, pd.DataFrame]:
    return {name: simulate(P, pol, years) for name, pol in scenarios.items()}


def summary(df: pd.DataFrame, base: pd.DataFrame | None = None, dt: float = 0.25) -> dict:
    """Kopsavilkums par periodu: gala rādītāji un uzkrātās izmaksas (milj. EUR)."""
    last = df.iloc[-1]
    out = dict(
        gaidisana_beigas_men=last.gaidisana_men,
        maksas_cena_beigas=last.maksas_cena,
        valsts_laika_dala_beigas=last.valsts_laika_dala,
        oop_dala_beigas=last.oop_dala,
        akutie_beigas_tuks=last.akutie_novers_tuks,
        saistosais_beigas=last.saistosais,
        uzkrata_valsts_izdevumi=float(df.valsts_kopa.iloc[:-1].sum() * dt),
        uzkrata_tiesie_maksajumi=float(df.tiesie_maksajumi_kopa.iloc[:-1].sum() * dt),
        uzkrata_prod_zaudejumi=float(df.prod_zaudejumi.iloc[:-1].sum() * dt),
    )
    if base is not None:
        out["d_valsts_izdevumi"] = out["uzkrata_valsts_izdevumi"] - float(base.valsts_kopa.iloc[:-1].sum() * dt)
        out["d_tiesie_maksajumi"] = out["uzkrata_tiesie_maksajumi"] - float(base.tiesie_maksajumi_kopa.iloc[:-1].sum() * dt)
        out["d_prod_zaudejumi"] = out["uzkrata_prod_zaudejumi"] - float(base.prod_zaudejumi.iloc[:-1].sum() * dt)
        out["d_sabiedriskie_kopa"] = out["d_valsts_izdevumi"] + out["d_tiesie_maksajumi"] + out["d_prod_zaudejumi"]
    return out


def sensitivity(P: Params, pol: Policy, keys: list[str], metric: str = "gaidisana_men",
                swing: float = 0.25, years: float = 10) -> pd.DataFrame:
    """Vienas svirras jutīgums: katru parametru maina ±swing un mēra gala rādītāju."""
    base_val = simulate(P, pol, years)[metric].iloc[-1]
    rows = []
    for k in keys:
        v0 = getattr(P, k)
        if v0 == 0:
            continue
        res = []
        for f in (1 - swing, 1 + swing):
            res.append(simulate(replace(P, **{k: v0 * f}), pol, years)[metric].iloc[-1])
        rows.append(dict(parametrs=k, zems=res[0], augsts=res[1], bazes=base_val,
                         amplitude=abs(res[1] - res[0])))
    return pd.DataFrame(rows).sort_values("amplitude", ascending=False).reset_index(drop=True)
