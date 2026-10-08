#!/usr/bin/env python3
"""Validação fora da amostra, como em inferencia_ecologica.validar(): o modelo é ajustado em 80% das áreas
de cada UF (b05 --validacao) e prevê a margem do 2º turno de 2022 nas outras 20%.

Para a área deixada de fora: o efeito da área é sorteado da priori hierárquica N(0, s_u); o do município
também, se o município não tiver área no ajuste. Predição com sorteio Dirichlet (mesma verossimilhança).
Métricas: cobertura do intervalo de 90% e erro absoluto mediano da margem (pp dos aptos), por faixa e no total.

Saída: variantes/<U>/<M>/validacao.csv
Uso: python bairros/b05c_validacao.py --unidade U1 --metodo MC
"""
import argparse, glob, os, sys
import numpy as np
import pandas as pd
import xarray as xr

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from inferencia_ecologica import ROTULOS, SEMENTE  # noqa: E402


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--unidade", default="U1"); ap.add_argument("--metodo", default="MC")
    a = ap.parse_args()
    pasta = os.path.join(RAIZ, "variantes", a.unidade, a.metodo)
    rng = np.random.default_rng(SEMENTE + 1)
    linhas = []
    for f in sorted(glob.glob(os.path.join(pasta, "post_??_val.nc"))):
        uf = os.path.basename(f)[5:7]
        st = xr.open_dataset(f).stack(s=("chain", "draw"))
        dz = np.load(os.path.join(pasta, f"dados_{uf}_val.npz"))
        tr, te = dz["treino"], ~dz["treino"]
        if te.sum() == 0:
            continue
        S = min(st.sizes["s"], 1000)
        idx = rng.choice(st.sizes["s"], S, replace=False)
        V = lambda k: st[k].transpose("s", ...).values[idx]
        eta, gam = V("eta"), V("gamma")
        smun, zmun, srm, zrm, su = V("s_mun"), V("z_mun"), V("s_rm"), V("z_rm"), V("s_u")
        mun, rm, g, w, x, y, N = (dz[k] for k in ("mun", "rm", "g", "w", "x", "y", "N"))
        mun_tr = set(mun[tr])
        n = int(te.sum())
        mi, ri = mun[te], rm[te]
        tem = np.isin(mi, list(mun_tr)) & (mi < zmun.shape[1])
        am = np.where(tem[None, :, None], (smun[:, None, :] * zmun)[:, np.minimum(mi, zmun.shape[1] - 1)],
                      rng.normal(size=(S, n, 2)) * smun[:, None, :])
        ar = (srm[:, None, :] * zrm)[:, np.minimum(ri, zrm.shape[1] - 1)] * dz["tem_rm"][np.minimum(ri, len(dz["tem_rm"]) - 1)][None, :, None]
        uv = rng.normal(size=(S, n, 2)) * su[:, None, :]
        lg = eta[:, g[te]] + np.einsum("ok,skrc->sorc", w[te], gam) + (am + ar + uv)[:, :, None, :]
        lg = np.concatenate([lg, np.zeros(lg.shape[:3] + (1,))], axis=3)
        lg -= lg.max(3, keepdims=True); e = np.exp(lg); B = e / e.sum(3, keepdims=True)
        th = np.einsum("or,sorc->soc", x[te], B)
        logN = np.log(N[te]) - float(dz["logN_ref"])
        kap = np.exp(V("log_k0")[:, None] + V("rho")[:, None] * logN[None])
        G = rng.gamma(kap[..., None] * th + 1e-6); pr = G / G.sum(2, keepdims=True)
        mg = pr[..., 0] - pr[..., 1]
        lo, md, hi = np.quantile(mg, [.05, .5, .95], axis=0)
        obs = y[te, 0] - y[te, 1]
        for j in range(n):
            linhas.append({"uf": uf, "faixa": ROTULOS[g[te][j]], "dentro_ic90": lo[j] <= obs[j] <= hi[j],
                           "erro_abs_pp": 100 * abs(md[j] - obs[j]), "aptos": N[te][j]})
    d = pd.DataFrame(linhas)
    t = d.groupby("faixa").agg(areas=("dentro_ic90", "size"), cobertura_ic90=("dentro_ic90", "mean"),
                               erro_mediano_pp=("erro_abs_pp", "median")).reindex(ROTULOS)
    t.loc["TODAS"] = [len(d), d["dentro_ic90"].mean(), d["erro_abs_pp"].median()]
    t.reset_index().to_csv(os.path.join(pasta, "validacao.csv"), index=False)
    u = d.groupby("uf").agg(areas=("dentro_ic90", "size"), cobertura_ic90=("dentro_ic90", "mean"), erro_mediano_pp=("erro_abs_pp", "median"))
    u.reset_index().to_csv(os.path.join(pasta, "validacao_uf.csv"), index=False)
    print(t.round(3).to_string()); print(u.round(3).sort_values("cobertura_ic90").head(8).to_string())


if __name__ == "__main__":
    main()
