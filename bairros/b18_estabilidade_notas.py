#!/usr/bin/env python3
"""Etapa B18: a nota de cada área muda conforme a cadeia do MCMC? (estabilidade das quantidades que o mapa usa)

O selo de "estimativa menos segura" olha a convergência de todos os parâmetros (R-hat máximo e cadeias boas). Mas a nota
de 1 a 7 só depende do modelo eleitoral por um caminho: a fração dos que não votaram que iria para Lula (efeito de levar
mais 2 em cada 100 às urnas, que entra no potencial, na "segurança" e na "certeza"). O terreno perdido não depende do
modelo, e a terceira via não entra na nota.

Para cada UF, refaz a nota de cada área com o posterior de uma cadeia por vez (com uma cadeia só, usa as duas metades
dela), mantendo as outras UFs como estão, e mede:
  * R-hat entre cadeias da fração dos que não votaram que iria para Lula, por área;
  * quantas áreas mudam de nota entre cadeias (e quantos eleitores), e quantas mudam 2+ níveis;
  * quantos municípios mudam de nota.
UFs estáveis (SP, ES, GO) entram como controle: dizem quanto muda "por acaso" (simulação finita).

Saída: variantes/<U>/MC/estabilidade_notas.csv
"""
import argparse, os, sys, time
import numpy as np
import pandas as pd
import torch
import xarray as xr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import b05_ei_bairros as b5            # noqa: E402
import b08_esforco as b8               # noqa: E402
from b06_montecarlo_bairros import dados_2026, faixa, DEV, SEMENTE   # noqa: E402

AMOSTRAS = 1000  # sorteios por conjunto de cadeias


def preparar(unidade, uf, d22, d26):
    """Mesma montagem de b06 (taxas por área em 2026) para uma UF; devolve a função de taxas e os dados da UF."""
    pasta = os.path.join(b5.VAR, unidade, "MC")
    post = xr.open_dataset(os.path.join(pasta, f"post_{uf}.nc"))
    dz = np.load(os.path.join(pasta, f"dados_{uf}.npz"))
    sub22 = d22[d22["uf"] == uf].reset_index(drop=True)
    mun_cats = np.unique(sub22["cd_mun_ibge"].fillna("__nenhum__").astype(str))
    rm_cats = np.unique(sub22["nome_rm"].fillna("__nenhum__").astype(str))
    tem_rm = (rm_cats != "__nenhum__").astype(np.float32)
    multi = np.bincount(dz["mun"], minlength=len(mun_cats))[dz["mun"]] > 1
    u_pos = {iu: k for k, iu in enumerate(dz["ids"][multi])} if "z_u" in post else {}
    du = d26[d26["uf"] == uf].reset_index(drop=True)
    L, Bv, T = (du[c].to_numpy(float) for c in ("lula", "adv", "terc"))
    g = faixa(pd.Series(100 * L / (L + Bv + T))).cat.codes.to_numpy()
    renda = du["renda_resp"].where(du["renda_resp"] > 0).fillna(sub22["renda_resp"].median()).to_numpy()
    w, _ = b5.covariaveis(du["aptos"].to_numpy(float), renda, (dz["ref_media"], dz["ref_desvio"]))
    m_i = np.searchsorted(mun_cats, du["cd_mun_ibge"].astype(str).to_numpy())
    m_i = np.where(mun_cats[np.minimum(m_i, len(mun_cats) - 1)] == du["cd_mun_ibge"].astype(str).to_numpy(), m_i, -1)
    r_i = np.minimum(np.searchsorted(rm_cats, du["nome_rm"].fillna("__nenhum__").astype(str).to_numpy()), len(rm_cats) - 1)
    u_i = np.array([u_pos.get(i, -1) for i in du["id_unidade"]])
    return post, tem_rm, (g, w, m_i, r_i, u_i), du


def fracao_lula(post_cadeia, tem_rm, idx, gen):
    """Fração dos que não votaram que iria para Lula, por sorteio e área (mesma conta de b06)."""
    g, w, mm, rr, uu = idx
    st = post_cadeia.stack(s=("chain", "draw"))
    P = st.sizes["s"]
    ss = torch.tensor(gen.integers(0, P, AMOSTRAS), device=DEV)
    T = lambda k: torch.tensor(st[k].transpose("s", ...).values, device=DEV, dtype=torch.float32)
    eta, gam, su, zu = T("eta"), T("gamma"), T("s_u"), T("z_u")
    V = lambda k: st[k].transpose("s", ...).values
    amun = torch.tensor(V("s_mun")[:, None, :] * V("z_mun"), device=DEV, dtype=torch.float32)
    arm = torch.tensor(V("s_rm")[:, None, :] * V("z_rm"), device=DEV, dtype=torch.float32) * torch.tensor(tem_rm, device=DEV)[None, :, None]
    e = eta[ss][:, g] + torch.einsum("ok,skrc->sorc", torch.tensor(w, device=DEV, dtype=torch.float32), gam[ss])
    am = amun[ss][:, torch.tensor(np.maximum(mm, 0), device=DEV)]
    if (mm < 0).any():
        novo_m = torch.randn(AMOSTRAS, len(mm), 2, device=DEV) * T("s_mun")[ss][:, None, :]
        am = torch.where(torch.tensor(mm < 0, device=DEV)[None, :, None], novo_m, am)
    ar = arm[ss][:, torch.tensor(rr, device=DEV)]
    uv = zu[ss][:, torch.tensor(np.maximum(uu, 0), device=DEV)] if zu.shape[1] > 0 else torch.zeros(AMOSTRAS, len(uu), 2, device=DEV)
    uv = torch.where(torch.tensor(uu < 0, device=DEV)[None, :, None], torch.randn(AMOSTRAS, len(uu), 2, device=DEV), uv) * su[ss][:, None, :]
    lg = e + (am + ar + uv)[:, :, None, :]
    lg = torch.cat([lg, torch.zeros(lg.shape[:3] + (1,), device=DEV)], dim=3)
    B = torch.softmax(lg, dim=3)
    return (B[:, :, 3, 0] / (B[:, :, 3, 0] + B[:, :, 3, 1])).cpu().numpy()     # amostras x áreas


def rhat(cadeias):
    """R-hat (com divisão em metades) por área; cadeias: lista de matrizes amostras x áreas."""
    meias = []
    for c in cadeias:
        h = c.shape[0] // 2
        meias += [c[:h], c[h:2 * h]]
    x = np.stack(meias)                                   # m, n, áreas
    m, n = x.shape[:2]
    W = x.var(axis=1, ddof=1).mean(0)
    Bn = n * x.mean(axis=1).var(axis=0, ddof=1)
    return np.sqrt(((n - 1) / n * W + Bn / n) / np.maximum(W, 1e-12))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unidade", default="U4")
    ap.add_argument("--ufs", nargs="*", default=["BA", "CE", "PA", "RJ", "MG", "SP", "ES", "GO"])
    a = ap.parse_args()
    t0 = time.time()
    gen = np.random.default_rng(SEMENTE + 18)
    torch.manual_seed(SEMENTE + 18)
    pasta = os.path.join(b5.VAR, a.unidade, "MC")
    base = pd.read_parquet(os.path.join(pasta, "unidades_mc.parquet"))
    for c in ("pot_p05", "pot_p50", "pot_p95", "prob_mob_rende", "mob_p50"):
        base[c] = base[c].astype("float64")      # as colunas vêm em float32; as notas por cadeia gravam float64
    nota_base = b8.classificar(base)["nivel_P2"]
    d22, *_ = b5.montar(a.unidade)
    d26 = dados_2026(a.unidade)
    linhas = []
    for uf in a.ufs:
        post, tem_rm, idx, du = preparar(a.unidade, uf, d22, d26)
        nch = post.sizes["chain"]
        D_ = post.sizes["draw"]
        # A e B: dois conjuntos independentes de cadeias (pares e ímpares); A1 e A2: metades das mesmas cadeias de A
        # (ruído da simulação, sem diferença entre cadeias). Com uma cadeia só, A e B são as duas metades dela.
        if nch >= 2:
            A, B = post.isel(chain=list(range(0, nch, 2))), post.isel(chain=list(range(1, nch, 2)))
            como = f"{nch} cadeias"
        else:
            A, B = post.isel(draw=slice(0, D_ // 2)), post.isel(draw=slice(D_ // 2, None))
            como = "1 cadeia (metades)"
        dA = A.sizes["draw"]
        A1, A2 = A.isel(draw=slice(0, dA // 2)), A.isel(draw=slice(dA // 2, None))
        fr = {k: fracao_lula(v, tem_rm, idx, gen) for k, v in (("A", A), ("B", B), ("A1", A1), ("A2", A2))}
        cad = [fracao_lula(post.isel(chain=[c]), tem_rm, idx, gen) for c in range(nch)] if nch >= 2 else [fr["A"], fr["B"]]
        rh = rhat(cad)
        sel = base.index[base["uf"] == uf]
        assert (base.loc[sel, "id_unidade"].to_numpy() == du["id_unidade"].to_numpy()).all()
        N = du["aptos"].to_numpy(float)
        terr = (base.loc[sel, "pot_p50"] - np.where(base.loc[sel, "mob_p50"] > 0, base.loc[sel, "mob_p50"], 0)).to_numpy()
        nota = {}
        for k, f in fr.items():
            mob = 0.02 * N[None, :] * (2 * f - 1)
            rende = np.median(mob, axis=0) > 0
            pot = terr[None, :] + np.where(rende[None, :], mob, 0)
            u = base.copy()
            u.loc[sel, "pot_p05"], u.loc[sel, "pot_p50"], u.loc[sel, "pot_p95"] = np.quantile(pot, [.05, .5, .95], axis=0)
            u.loc[sel, "prob_mob_rende"] = (mob > 0).mean(0)
            nota[k] = b8.classificar(u)["nivel_P2"].loc[sel]
        ok_ = nota["A"].notna() & nota["B"].notna()
        ap_ = base.loc[sel, "aptos"][ok_]
        dif = lambda x, y: (nota[x][ok_] != nota[y][ok_])
        entre, ruido = dif("A", "B"), dif("A1", "A2")
        topo = ((nota["A"][ok_] >= 6) | (nota["B"][ok_] >= 6))
        linhas.append({
            "uf": uf, "posterior": como, "areas": int(ok_.sum()),
            "rhat_mediano": round(float(np.median(rh)), 3), "pct_areas_rhat_maior_1_05": round(100 * float((rh > 1.05).mean()), 1),
            "pct_mudam_entre_cadeias": round(100 * float(entre.mean()), 1),
            "pct_mudam_por_ruido": round(100 * float(ruido.mean()), 1),
            "excesso_pp": round(100 * float(entre.mean() - ruido.mean()), 1),
            "pct_eleitores_que_mudam_entre_cadeias": round(100 * float(ap_[entre].sum() / ap_.sum()), 1),
            "pct_mudam_2_ou_mais": round(100 * float((abs(nota["A"][ok_] - nota["B"][ok_]) >= 2).mean()), 2),
            "pct_nota_6_7_concordam": round(100 * float(((nota["A"][ok_] >= 6) & (nota["B"][ok_] >= 6)).sum() / max(topo.sum(), 1)), 1),
        })
        print(linhas[-1], f"| {time.time() - t0:.0f}s", flush=True)
    out = pd.DataFrame(linhas)
    out.to_csv(os.path.join(pasta, "estabilidade_notas.csv"), index=False)
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
