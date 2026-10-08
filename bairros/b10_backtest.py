#!/usr/bin/env python3
"""Etapa B10: série histórica e backtesting no nível de bairro (mesmas unidades de 2026).

1. Estabilidade geográfica: correlação, entre eleições, da fatia do PT nos dois candidatos do 2º turno
   por unidade (2010, 2014, 2018, 2022) e do 1º turno (até 2026).
2. Transferências entre turnos, por eleição: quanto o PT ganhou entre os turnos, por eleitor de terceira via.
3. Backtesting: ajusta as transferências da eleição X (b05 --ano X) e prevê o 2º turno da eleição X+4 a
   partir do 1º turno de X+4, unidade a unidade. Compara com o resultado real e com o swing uniforme
   (2º turno de X+4 = 1º turno de X+4 + variação nacional entre os turnos de X).
   Métricas: erro absoluto mediano da margem (pp dos aptos) e cobertura do intervalo de 90%.

Uso: python bairros/b10_backtest.py --unidade U1 --pares 2018:2022 2014:2018 2010:2014 [--metodo MC_rapido]
"""
import argparse, glob, json, os, sys
import numpy as np
import pandas as pd
import xarray as xr

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ); sys.path.insert(0, os.path.join(RAIZ, "bairros"))
import b05_ei_bairros as b5  # noqa: E402
from inferencia_ecologica import SEMENTE  # noqa: E402


def estabilidade(variante):
    anos = [2010, 2014, 2018, 2022]
    t = {}
    for a in anos:
        g = b5.agregar(variante, a)
        for turno in (1, 2):
            s = g[g["turno"] == turno].set_index("id_unidade")
            t[(a, turno)] = s["lula"] / (s["lula"] + s["adv"] + (s["terc"] if turno == 1 else 0))
    g26 = b5.agregar(variante, 2026, turnos=(1,)).set_index("id_unidade")
    t[(2026, 1)] = g26["lula"] / (g26["lula"] + g26["adv"] + g26["terc"])
    linhas = []
    pares = [((2010, 2), (2014, 2)), ((2014, 2), (2018, 2)), ((2018, 2), (2022, 2)),
             ((2010, 1), (2014, 1)), ((2014, 1), (2018, 1)), ((2018, 1), (2022, 1)), ((2022, 1), (2026, 1))]
    for p1, p2 in pares:
        j = pd.concat([t[p1], t[p2]], axis=1).dropna()
        sw = j.iloc[:, 1] - j.iloc[:, 0]
        linhas.append({"de": f"{p1[0]} T{p1[1]}", "para": f"{p2[0]} T{p2[1]}", "unidades": len(j),
                       "correlacao": round(j.corr().iloc[0, 1], 3), "variacao_media_pp": round(100*sw.mean(), 2),
                       "desvio_da_variacao_pp": round(100*sw.std(), 2)})
    return pd.DataFrame(linhas)


def transferencias(variante):
    linhas = []
    for a in (2010, 2014, 2018, 2022):
        g = b5.agregar(variante, a)
        t1, t2 = g[g["turno"] == 1].sum(numeric_only=True), g[g["turno"] == 2].sum(numeric_only=True)
        linhas.append({"ano": a, "pt_1t": int(t1["lula"]), "pt_2t": int(t2["lula"]), "adv_1t": int(t1["adv"]), "adv_2t": int(t2["adv"]),
                       "terceiros_1t": int(t1["terc"]), "ganho_pt_por_voto_terceiro": round((t2["lula"] - t1["lula"]) / t1["terc"], 3),
                       "ganho_adv_por_voto_terceiro": round((t2["adv"] - t1["adv"]) / t1["terc"], 3)})
    return pd.DataFrame(linhas)


def prever(pasta, uf, variante, ano_alvo, rng, S=300):
    """Prevê o 2º turno de ano_alvo nas unidades da UF, com o posterior ajustado em outro ano."""
    post = xr.open_dataset(os.path.join(pasta, f"post_{uf}.nc")).stack(s=("chain", "draw"))
    dz = np.load(os.path.join(pasta, f"dados_{uf}.npz"))
    d, x, y, N = b5.montar(variante, ano_alvo)
    sel = (d["uf"] == uf).to_numpy()
    d, x, y, N = d[sel].reset_index(drop=True), x[sel], y[sel], N[sel]
    w, _ = b5.covariaveis(N, d["renda_resp"], (dz["ref_media"], dz["ref_desvio"]))
    g = d["faixa_ei"].cat.codes.to_numpy()
    # índices de município/RM/unidade do ajuste (mesma ordem de np.unique em b05.indices)
    ids_fit = dz["ids"]
    # reconstrói categorias a partir do arquivo de dados do ajuste
    d_fit = b5.montar(variante, int(os.path.basename(pasta).split("_")[-1]))[0]
    d_fit = d_fit[d_fit["uf"] == uf].reset_index(drop=True)
    mun_c = np.unique(d_fit["cd_mun_ibge"].fillna("__nenhum__").astype(str))
    rm_c = np.unique(d_fit["nome_rm"].fillna("__nenhum__").astype(str))
    tem_rm = (rm_c != "__nenhum__").astype(float)
    mi = {c: i for i, c in enumerate(mun_c)}; ri = {c: i for i, c in enumerate(rm_c)}
    m_i = np.array([mi.get(c, -1) for c in d["cd_mun_ibge"].astype(str)])
    r_i = np.array([ri.get(c, ri.get("__nenhum__", 0)) for c in d["nome_rm"].fillna("__nenhum__").astype(str)])
    multi = np.bincount(dz["mun"], minlength=len(mun_c))[dz["mun"]] > 1
    upos = {k: j for j, k in enumerate(ids_fit[multi])}
    u_i = np.array([upos.get(k, -1) for k in d["id_unidade"]])
    P = post.sizes["s"]; idx = rng.choice(P, size=min(S, P), replace=False)
    eta = post["eta"].transpose("s", ...).values[idx]; gam = post["gamma"].transpose("s", ...).values[idx]
    V = lambda k: post[k].transpose("s", ...).values[idx]
    amun = V("s_mun")[:, None, :] * V("z_mun")
    arm = V("s_rm")[:, None, :] * V("z_rm") * tem_rm[None, :, None]
    su = post["s_u"].transpose("s", ...).values[idx]; zu = post["z_u"].transpose("s", ...).values[idx]
    smun = post["s_mun"].transpose("s", ...).values[idx]
    k0 = post["log_k0"].values[idx]; rho = post["rho"].values[idx]
    s_ = len(idx); n = len(N)
    am = np.where((m_i >= 0)[None, :, None], amun[:, np.maximum(m_i, 0)], rng.normal(size=(s_, n, 2)) * smun[:, None, :])
    uv = np.where((u_i >= 0)[None, :, None], zu[:, np.maximum(u_i, 0)] if zu.shape[1] else 0, rng.normal(size=(s_, n, 2))) * su[:, None, :]
    lg = eta[:, g] + np.einsum("ok,skrc->sorc", w, gam) + (am + arm[:, r_i] + uv)[:, :, None, :]
    lg = np.concatenate([lg, np.zeros(lg.shape[:3] + (1,))], axis=3)
    lg -= lg.max(3, keepdims=True); e = np.exp(lg); B = e / e.sum(3, keepdims=True)
    th = np.einsum("or,sorc->soc", x, B)
    logN = np.log(N) - float(dz["logN_ref"])
    kap = np.exp(k0[:, None] + rho[:, None] * logN[None])
    G = rng.gamma(kap[..., None] * th + 1e-6); pr = G / G.sum(2, keepdims=True)
    marg = pr[..., 0] - pr[..., 1]
    lo, md, hi = np.quantile(marg, [.05, .5, .95], axis=0)
    return pd.DataFrame({"id_unidade": d["id_unidade"], "uf": uf, "aptos": N, "obs": y[:, 0] - y[:, 1],
                         "p05": lo, "p50": md, "p95": hi, "lula1": x[:, 0], "adv1": x[:, 1]})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unidade", default="U1"); ap.add_argument("--metodo", default="MC_rapido")
    ap.add_argument("--pares", nargs="*", default=["2018:2022", "2014:2018", "2010:2014"])
    a = ap.parse_args()
    rng = np.random.default_rng(SEMENTE + 11)
    out = os.path.join(b5.VAR, a.unidade, "historico")
    os.makedirs(out, exist_ok=True)
    est = estabilidade(a.unidade); est.to_csv(os.path.join(out, "estabilidade.csv"), index=False); print(est.to_string(index=False))
    tr = transferencias(a.unidade); tr.to_csv(os.path.join(out, "transferencias.csv"), index=False); print(tr.to_string(index=False))
    res = []
    for par in a.pares:
        x_, y_ = map(int, par.split(":"))
        pasta = os.path.join(b5.VAR, a.unidade, f"{a.metodo}_{x_}")
        ufs = sorted(os.path.basename(p)[5:7] for p in glob.glob(os.path.join(pasta, "post_??.nc")))
        if not ufs:
            print(f"{par}: sem ajuste de {x_} em {pasta}"); continue
        pr = pd.concat([prever(pasta, u, a.unidade, y_, rng) for u in ufs])
        # swing uniforme: margem do 2º turno = margem do 1º turno + variação nacional entre turnos em X
        tX = tr.set_index("ano").loc[x_]
        tot = b5.agregar(a.unidade, x_)
        aptos = tot[tot["turno"] == 1]["aptos"].sum()
        dsw = ((tX["pt_2t"] - tX["adv_2t"]) - (tX["pt_1t"] - tX["adv_1t"])) / aptos
        pr["swing"] = pr["lula1"] - pr["adv1"] + dsw
        dentro = (pr["obs"] >= pr["p05"]) & (pr["obs"] <= pr["p95"])
        e_m = (100*(pr["p50"] - pr["obs"]).abs()).median(); e_s = (100*(pr["swing"] - pr["obs"]).abs()).median()
        nac_obs = (pr["obs"]*pr["aptos"]).sum(); nac_mod = (pr["p50"]*pr["aptos"]).sum(); nac_sw = (pr["swing"]*pr["aptos"]).sum()
        res.append({"ajuste": x_, "previsto": y_, "ufs": len(ufs), "unidades": len(pr), "cobertura_ic90": round(dentro.mean(), 3),
                    "erro_mediano_pp_modelo": round(e_m, 2), "erro_mediano_pp_swing_uniforme": round(e_s, 2),
                    "margem_total_obs_mi": round(nac_obs/1e6, 2), "margem_total_modelo_mi": round(nac_mod/1e6, 2),
                    "margem_total_swing_mi": round(nac_sw/1e6, 2)})
        pr.to_parquet(os.path.join(out, f"backtest_{x_}_{y_}.parquet"), index=False)
    if res:
        r = pd.DataFrame(res); r.to_csv(os.path.join(out, "backtest.csv"), index=False); print(r.to_string(index=False))


if __name__ == "__main__":
    main()
