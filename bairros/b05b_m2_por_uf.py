#!/usr/bin/env python3
"""Reparte o posterior do ADVI nacional (M2, post_BR.nc) em arquivos por UF no formato do MCMC (MC),
para que b06 (Monte Carlo) rode igual nos dois métodos e a comparação seja direta.

O efeito de UF do M2 é somado às taxas por faixa (eta) de cada UF. Municípios, RMs e unidades são
recortados na mesma ordem que b05 usa por UF (np.unique em texto preserva a ordem do subconjunto).

Uso: python bairros/b05b_m2_por_uf.py --unidade U1
"""
import argparse, os, sys
import numpy as np
import xarray as xr

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "bairros"))
import b05_ei_bairros as b5  # noqa: E402


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--unidade", default="U1")
    a = ap.parse_args()
    pasta = os.path.join(b5.VAR, a.unidade, "M2")
    post = xr.open_dataset(os.path.join(pasta, "post_BR.nc"))
    dz = np.load(os.path.join(pasta, "dados_BR.npz"), allow_pickle=True)
    d, x, y, N = b5.montar(a.unidade)
    # alinha às unidades do ajuste (a ordem das linhas de montar() não era fixa quando o M2 rodou)
    d = d.set_index("id_unidade").loc[dz["ids"]].reset_index()
    ufs = dz["uf_cats"]
    mun_c = np.unique(d["cd_mun_ibge"].fillna("__nenhum__").astype(str))
    rm_c = np.unique(d["nome_rm"].fillna("__nenhum__").astype(str))
    multi = np.bincount(dz["mun"], minlength=len(mun_c))[dz["mun"]] > 1
    pos_u = np.cumsum(multi) - 1
    eta = post["eta"].values                      # chain, draw, faixa, origem, 2
    suf = post["s_uf"].values[..., None, :, :] if post["s_uf"].ndim == 4 else post["s_uf"].values
    zuf = post["z_uf"].values                     # chain, draw, n_uf, 4, 2
    for k, uf in enumerate(ufs):
        sel = dz["uf"] == k
        m_loc = np.unique(d.loc[sel, "cd_mun_ibge"].astype(str)); r_loc = np.unique(d.loc[sel, "nome_rm"].fillna("__nenhum__").astype(str))
        im = np.searchsorted(mun_c, m_loc); ir = np.searchsorted(rm_c, r_loc)
        u_sel = sel & multi
        ds = xr.Dataset({
            "eta": (("chain", "draw", "faixa", "origem", "destino_livre"), eta + (post["s_uf"].values[:, :, None] * zuf[:, :, k][:, :, None])),
            "gamma": post["gamma"], "s_mun": post["s_mun"], "s_rm": post["s_rm"], "s_u": post["s_u"],
            "z_mun": (("chain", "draw", "zm", "d2"), post["z_mun"].values[:, :, im]),
            "z_rm": (("chain", "draw", "zr", "d2"), post["z_rm"].values[:, :, ir]),
            "z_u": (("chain", "draw", "zu", "d2"), post["z_u"].values[:, :, pos_u[u_sel]]),
            "log_k0": post["log_k0"], "rho": post["rho"]})
        ds.to_netcdf(os.path.join(pasta, f"post_{uf}.nc"))
        mm = np.searchsorted(m_loc, d.loc[sel, "cd_mun_ibge"].astype(str)); rr = np.searchsorted(r_loc, d.loc[sel, "nome_rm"].fillna("__nenhum__").astype(str))
        np.savez(os.path.join(pasta, f"dados_{uf}.npz"), ids=dz["ids"][sel], mun=mm, rm=rr, tem_rm=(r_loc != "__nenhum__").astype(float),
                 g=dz["g"][sel], w=dz["w"][sel], x=dz["x"][sel], y=dz["y"][sel], N=dz["N"][sel], logN_ref=dz["logN_ref"],
                 ref_media=dz["ref_media"], ref_desvio=dz["ref_desvio"])
    print(f"{len(ufs)} UFs -> {pasta}")


if __name__ == "__main__":
    main()
