/* Rindu un maksas aprūpes modelis – JavaScript versija.
   Tiešs model.py ports (ceturkšņa solis, reālie euro). Sakritību ar Python pārbauda tests/test_js_parity.py.
   Ja maina model.py, jāmaina arī šeit. */
(function (root) {
  "use strict";
  const EPS = 1e-9;
  const clip = (x, lo, hi) => Math.max(lo, Math.min(hi, x));

  function calibrate(P) {
    const tau0 = P.tau0, p0 = P.p0;
    const V0 = P.E0 * 1e6 / tau0;
    const S0 = V0;
    const W0 = P.W0m / 12.0;
    const Ws = P.W_safe_m / 12.0;
    const Q0 = W0 * S0;
    const A0 = P.delta * Q0 * Math.max(0.0, 1.0 - Ws / W0);
    const R0 = (S0 + A0 + P.h_ab * Q0) / (1.0 - P.phi0);
    const D0 = P.phi0 * R0;
    const cap_pub0 = S0 * P.slack0;
    const cap_priv0 = D0;
    const s0 = cap_pub0 / (cap_pub0 + cap_priv0);
    const m = (cap_pub0 + cap_priv0) / P.H0;
    const the0 = P.B0 / (1.0 - P.oop_share0 - P.vhi_share0);
    const oop0 = P.oop_share0 * the0;
    const oop_amb0 = D0 * p0 / 1e6;
    const o_other = oop0 - oop_amb0;
    const vhi = P.vhi_share0 * the0;
    const acute_cost0 = A0 * P.c_ac / 1e6;
    const pub_other = P.B0 - P.E0 - acute_cost0;
    const warn = [];
    if (o_other < 0) warn.push("Ambulatoro maksas izdevumu apjoms pārsniedz kopējo tiešo maksājumu apjomu: samaziniet maksājošo daļu vai maksas cenu, vai paaugstiniet tiešo maksājumu daļu.");
    if (!(P.s_lo <= s0 && s0 <= P.s_hi)) warn.push("Atvasinātā bāzes valsts laika daļa (" + s0.toFixed(2) + ") ir ārpus ārsta laika robežām.");
    return { V0, S0, W0, Ws, Q0, A0, R0, D0, cap_pub0, cap_priv0, s0, m, the0, oop0,
             o_other: Math.max(o_other, 0.0), vhi, acute_cost0, pub_other, warn };
  }

  function simulate(P, pol, years, dt, baseYear) {
    years = years === undefined ? 10 : years;
    dt = dt || 0.25;
    baseYear = baseYear || 2026;
    const c = calibrate(P);
    const tau0 = P.tau0, p0 = P.p0;
    const n = Math.round(years / dt);
    let s = c.s0, p = p0, Q = c.Q0, W_prev = c.W0, acute_cost_prev = c.acute_cost0;
    const rows = [];

    for (let k = 0; k <= n; k++) {
      const t = k * dt;
      let ramp;
      if (pol.ramp_years > 0) ramp = clip((t - pol.delay_years) / pol.ramp_years, 0.0, 1.0);
      else ramp = t >= pol.delay_years ? 1.0 : 0.0;
      const tp = Math.max(t - pol.delay_years, 0.0);
      const tau = tau0 * (1 + pol.d_tarifs * ramp) * Math.pow(1 + pol.tarifs_aug, tp);
      const adm = Math.max(0.0, P.adm0 - pol.admin_red * ramp);
      const adm_factor = (1 - adm) / (1 - P.adm0);

      const H = P.H0 * Math.pow(1 + P.g_H, t) * Math.pow(1 + pol.fte_aug, Math.max(t - pol.fte_lag, 0.0));
      const y = Math.pow(1 + P.g_y, t);

      const V_pol = c.V0 * Math.pow(1 + P.g_B, t) * (1 + pol.d_apjoms * ramp) * Math.pow(1 + pol.apjoms_aug, tp);
      const required = V_pol * tau;
      let funded;
      if (pol.auto_fund) funded = required;
      else {
        const alloc = Math.min(P.E0 * 1e6 * Math.pow(1 + P.g_B, t), required);
        funded = Math.max(alloc - P.crowd * Math.max(acute_cost_prev - c.acute_cost0, 0.0) * 1e6, 0.0);
      }
      const V = funded / tau;

      const R_trend = c.R0 * Math.pow(1 + P.g_d, t);
      const R = R_trend * Math.pow(Math.max(W_prev, 0.02) / c.W0, -P.xi);
      const phi = clip(P.phi0 * Math.pow(Math.max(W_prev, 0.02) / c.W0, P.e_w) * Math.pow((p / p0) / y, -P.e_p), 0.02, 0.9);
      const D_priv = phi * R;

      const cap_pub = H * s * c.m * adm_factor;
      const cap_priv = H * (1 - s) * c.m;
      const priv_del = Math.min(D_priv, cap_priv);
      const spill = D_priv - priv_del;

      const inflow = R * (1 - phi) + spill;
      const A_av = P.delta * Q * Math.max(0.0, 1.0 - c.Ws / Math.max(W_prev, EPS));
      let ab = P.h_ab * Q * (Math.max(W_prev, EPS) / c.W0);
      ab = Math.min(ab, Q / dt);
      const S = Math.min(V, cap_pub, Math.max(inflow - A_av - ab + Q / dt, 0.0));
      const Q_new = Math.max(Q + dt * (inflow - A_av - ab - S), 0.0);
      const W = Q / Math.max(S, 1.0);

      const acute_cost = A_av * P.c_ac / 1e6;
      const pub_amb = S * tau / 1e6;
      const public_total = c.pub_other + pub_amb + acute_cost;
      const oop_amb = priv_del * p / 1e6;
      const oop_total = c.o_other + oop_amb;
      const the = public_total + oop_total + c.vhi;
      const q_excess = Q * Math.max(0.0, 1.0 - c.Ws / Math.max(W, EPS));
      const prod_loss = q_excess * P.ell * P.emp * P.v_day / 1e6;

      rows.push({
        laiks: t, gads: baseYear + t,
        gaidisana_men: W * 12, rinda_tuks: Q / 1e3,
        maksajoso_dala: phi, maksas_cena: p, valsts_laika_dala: s,
        nosutijumi_milj: R / 1e6, apkalpots_valsts_milj: S / 1e6, kvota_milj: V / 1e6,
        kapacitate_valsts_milj: cap_pub / 1e6, maksas_epizodes_milj: priv_del / 1e6,
        maksas_kapacitate_milj: cap_priv / 1e6,
        saistosais: cap_pub < V - 1 ? "ārstu kapacitāte" : "kvota/nauda",
        akutie_novers_tuks: A_av / 1e3, akutie_izmaksas: acute_cost,
        valsts_ambulatori: pub_amb, valsts_kopa: public_total,
        tiesie_maksajumi_kopa: oop_total, kopeji_izdevumi: the, oop_dala: oop_total / the,
        prod_zaudejumi: prod_loss, tarifs: tau
      });

      const lam_ratio = D_priv / Math.max(cap_priv, 1.0);
      p = clip(p * Math.exp(P.lam * dt * Math.log(Math.max(lam_ratio, 1e-6))), 0.5 * p0, 4.0 * p0);
      const rho = (tau * (1 - adm) / p) / (tau0 * (1 - P.adm0) / p0);
      const s_star = clip(c.s0 * Math.pow(rho, P.eta), P.s_lo, P.s_hi);
      s = s + (s_star - s) * (1 - Math.exp(-dt / P.t_adj));
      Q = Q_new;
      W_prev = W;
      acute_cost_prev = acute_cost;
    }
    return rows;
  }

  function sumCol(rows, key, dt) {
    let a = 0;
    for (let i = 0; i < rows.length - 1; i++) a += rows[i][key];
    return a * (dt || 0.25);
  }

  function summary(rows, base) {
    const last = rows[rows.length - 1];
    const out = {
      gaidisana_beigas_men: last.gaidisana_men, maksas_cena_beigas: last.maksas_cena,
      valsts_laika_dala_beigas: last.valsts_laika_dala, oop_dala_beigas: last.oop_dala,
      akutie_beigas_tuks: last.akutie_novers_tuks, saistosais_beigas: last.saistosais,
      uzkrata_valsts_izdevumi: sumCol(rows, "valsts_kopa"),
      uzkrata_tiesie_maksajumi: sumCol(rows, "tiesie_maksajumi_kopa"),
      uzkrata_prod_zaudejumi: sumCol(rows, "prod_zaudejumi")
    };
    if (base) {
      out.d_valsts_izdevumi = out.uzkrata_valsts_izdevumi - sumCol(base, "valsts_kopa");
      out.d_tiesie_maksajumi = out.uzkrata_tiesie_maksajumi - sumCol(base, "tiesie_maksajumi_kopa");
      out.d_prod_zaudejumi = out.uzkrata_prod_zaudejumi - sumCol(base, "prod_zaudejumi");
      out.d_sabiedriskie_kopa = out.d_valsts_izdevumi + out.d_tiesie_maksajumi + out.d_prod_zaudejumi;
    }
    return out;
  }

  function sensitivity(P, pol, keys, metric, swing, years) {
    const baseVal = simulate(P, pol, years).slice(-1)[0][metric];
    const rows = [];
    for (const k of keys) {
      const v0 = P[k];
      if (v0 === 0) continue;
      const res = [1 - swing, 1 + swing].map(f => {
        const Q = Object.assign({}, P); Q[k] = v0 * f;
        return simulate(Q, pol, years).slice(-1)[0][metric];
      });
      rows.push({ parametrs: k, zems: res[0], augsts: res[1], bazes: baseVal, amplitude: Math.abs(res[1] - res[0]) });
    }
    rows.sort((a, b) => b.amplitude - a.amplitude);
    return rows;
  }

  const api = { calibrate, simulate, summary, sensitivity };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.RM = api;
})(typeof window !== "undefined" ? window : globalThis);
