#!/usr/bin/env python3
"""Etapa B7b: pesquisas levadas ao bairro por MRP sintético (MrsP), com intervalos por bootstrap.

Os institutos publicam só marginais (Lula entre as mulheres, entre os pretos...), não o cruzamento
completo. Por isso:

  1. Modelo: logit P(Lula | Lula ou Flávio) = a + b_sexo + b_idade + b_cor + b_geo (aditivo).
     Ajustado para que as marginais previstas reproduzam as publicadas, dada a composição conjunta
     do eleitorado 15+ do Censo 2022 (sexo x idade conjuntos; cor independente de sexo x idade,
     hipótese da pós-estratificação sintética, Leemann e Wasserfallen 2017). Priori N(0, 1) nos
     efeitos (penalização ridge).
  2. Incerteza: 1.000 reamostragens paramétricas das marginais (binomial com a base ponderada
     publicada, ou a amostra x a fração do grupo no Censo, dividida por um efeito de desenho de 1,5).
  3. Pós-estratificação: em cada unidade, composição 15+ por sexo x idade e cor ou raça (Censo 2022).

Só entram na pós-estratificação variáveis que o Censo tem por setor: sexo, idade e cor ou raça.
Renda familiar, escolaridade e religião aparecem nos cruzamentos, mas não há composição por bairro
no Censo 2022 publicado: elas NÃO entram (efeito absorvido em parte por cor e região). Orientação
sexual: não há dado oficial por bairro; não é usada.

Variantes:
  R1  Datafolha (nacional, 29/09 a 01/10/2026): sexo, idade, cor, região
  R2  AtlasIntel (estaduais, 27/09 a 02/10/2026): sexo e UF, nas UFs com relatório legível
  R3  combinada: efeitos de sexo, idade e cor do Datafolha; nível de cada UF calibrado pela AtlasIntel
      (onde houver), senão pela região do Datafolha

Saída: variantes/<U>/mrp.parquet (lula2 = fatia de Lula entre os dois, mediana e intervalo de 90%)
"""
import argparse, os, sys
import numpy as np
import pandas as pd
from scipy.optimize import minimize

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAR = os.path.join(RAIZ, "variantes")
INS = os.path.join(RAIZ, "bairros", "insumos", "pesquisas")
SEMENTE = 20261007
B = 1000
DEFF = 1.5
SEXO = ["masculino", "feminino"]
IDADE = ["16-24", "25-34", "35-44", "45-59", "60+"]
COR = ["branca", "preta", "parda"]
REG = {"SE": ["SP", "RJ", "MG", "ES"], "S": ["PR", "SC", "RS"], "NE": ["BA", "PE", "CE", "MA", "PI", "RN", "PB", "AL", "SE"],
       "CO_N": ["GO", "DF", "MT", "MS", "TO", "AM", "PA", "AC", "AP", "RO", "RR"]}
UF_REG = {u: r for r, us in REG.items() for u in us}
UF_NOME = {"acre": "AC", "alagoas": "AL", "amapa": "AP", "distrito federal": "DF", "espirito santo": "ES", "goias": "GO",
           "maranhao": "MA", "mato grosso": "MT", "mato grosso do sul": "MS", "para": "PA", "paraiba": "PB", "parana": "PR",
           "pernambuco": "PE", "rio grande do norte": "RN", "rio grande do sul": "RS", "rondonia": "RO", "roraima": "RR",
           "santa catarina": "SC", "sergipe": "SE", "tocantins": "TO"}
# faixas do Censo (15+) -> faixas das pesquisas; 30-39 e 40-49 divididas ao meio entre as faixas vizinhas
MAPA_IDADE = {"15_19": {"16-24": 1}, "20_24": {"16-24": 1}, "25_29": {"25-34": 1}, "30_39": {"25-34": .5, "35-44": .5},
              "40_49": {"35-44": .5, "45-59": .5}, "50_59": {"45-59": 1}, "60_69": {"60+": 1}, "70m": {"60+": 1}}


def composicao(un):
    """Por unidade: fração de cada célula sexo x idade (15+) e de cada cor (branca, preta, parda+outras)."""
    sx = np.zeros((len(un), 2, 5))
    for s_i, s in enumerate("mf"):
        for f, dest in MAPA_IDADE.items():
            v = un[f"{s}_{f}"].fillna(0).to_numpy(float)
            for faixa, peso in dest.items():
                sx[:, s_i, IDADE.index(faixa)] += peso * v
    tot = sx.sum((1, 2), keepdims=True)
    sx = np.where(tot > 0, sx / np.maximum(tot, 1), 1 / 10)
    cor = np.c_[un["branca"].fillna(0), un["preta"].fillna(0), un[["parda", "amarela", "indigena"]].fillna(0).sum(1)].astype(float)
    ct = cor.sum(1, keepdims=True)
    cor = np.where(ct > 0, cor / np.maximum(ct, 1), 1 / 3)
    return sx, cor   # (n,2,5), (n,3)


def celulas(sx, cor):
    """Fração de cada célula (sexo, idade, cor) sob independência de cor: (n, 2, 5, 3)."""
    return sx[:, :, :, None] * cor[:, None, None, :]


def ajustar(marg, comp, geo_niveis, geo_comp, lam=1.0):
    """marg: lista de (variavel, categoria, q, n, geo|None). comp: composição conjunta nacional (2,5,3).
    geo_comp: dict geo -> composição (2,5,3) da área. Devolve os efeitos."""
    nG = len(geo_niveis)
    def unpack(th):
        a, bs, bi, bc = th[0], np.r_[0, th[1:2]], np.r_[0, th[2:6]], np.r_[0, th[6:8]]
        bg = dict(zip(geo_niveis, np.r_[0, th[8:8 + nG - 1]] if nG else []))
        return a, bs, bi, bc, bg
    def pred(th, var, cat, geo):
        a, bs, bi, bc, bg = unpack(th)
        eta = a + bs[:, None, None] + bi[None, :, None] + bc[None, None, :] + (bg.get(geo, 0.0) if geo else 0.0)
        w = (geo_comp.get(geo, comp) if geo else comp).copy()
        if var == "sexo":
            m = np.zeros_like(w); m[SEXO.index(cat)] = 1
        elif var == "idade":
            m = np.zeros_like(w); m[:, IDADE.index(cat)] = 1
        elif var == "cor_raca":
            m = np.zeros_like(w); m[:, :, COR.index(cat)] = 1
        else:   # total ou geografia
            m = np.ones_like(w)
        ww = w * m
        return (ww * 1/(1 + np.exp(-eta))).sum() / ww.sum()
    def perda(th):
        e = sum(n * (pred(th, v, c, g) - q)**2 / max(q*(1 - q), 1e-3) for v, c, q, n, g in marg)
        return e + lam * (th[1:]**2).sum()
    th0 = np.zeros(8 + max(nG - 1, 0))
    r = minimize(perda, th0, method="L-BFGS-B")
    return unpack(r.x)


def pos_estratificar(ef, cel, geo_por_unidade):
    a, bs, bi, bc, bg = ef
    eta = a + bs[:, None, None] + bi[None, :, None] + bc[None, None, :]
    g = np.array([bg.get(x, 0.0) for x in geo_por_unidade])
    p = 1/(1 + np.exp(-(eta[None] + g[:, None, None, None])))
    return (cel * p).sum((1, 2, 3))


def marginais_datafolha(c, comp_nac, base_total):
    d = c[(c["instituto"] == "Datafolha") & (c["registro_tse"] == "BR-08039/2026")]
    out = []
    for _, r in d.iterrows():
        v, k = r["variavel"], r["categoria_padrao"]
        q = r["pct_lula"] / (r["pct_lula"] + r["pct_flavio"])
        n = (r["base_ponderada"] if pd.notna(r["base_ponderada"]) else base_total) * (r["pct_lula"] + r["pct_flavio"]) / 100 / DEFF
        if v == "sexo" and k in SEXO or v == "idade" and k in IDADE or v == "cor_raca" and k in COR:
            out.append((v, k, q, n, None))
        elif v == "regiao" and k in REG:
            out.append(("geo", k, q, n, k))
        elif v == "total":
            out.append(("total", "total", q, n, None))
    # a mesma coluna "Total" aparece nos três blocos: fica uma vez
    vistos, uni = set(), []
    for m in out:
        if m[:2] not in vistos:
            vistos.add(m[:2]); uni.append(m)
    return uni


def marginais_atlas(c, pesq, comp_uf):
    a = c[c["instituto"] == "AtlasIntel"].copy()
    a["uf"] = a["abrangencia_uf"].map(UF_NOME)
    amostra = pesq.assign(uf=pesq["abrangencia_uf"].map(UF_NOME)).set_index("uf")["amostra"]
    out = []
    for _, r in a[a["variavel"] == "sexo"].iterrows():
        if r["categoria_padrao"] not in SEXO or pd.isna(r["uf"]):
            continue
        q = r["pct_lula"] / (r["pct_lula"] + r["pct_flavio"])
        frac = comp_uf[r["uf"]][SEXO.index(r["categoria_padrao"])].sum()
        n = float(amostra.get(r["uf"], 1000)) * frac * (r["pct_lula"] + r["pct_flavio"]) / 100 / DEFF
        out.append(("sexo", r["categoria_padrao"], q, n, r["uf"]))
    return out


def reamostrar(marg, rng):
    return [(v, k, rng.binomial(max(int(n), 1), q) / max(int(n), 1), n, g) for v, k, q, n, g in marg]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unidade", default="U1"); ap.add_argument("--reamostragens", type=int, default=B)
    a = ap.parse_args()
    rng = np.random.default_rng(SEMENTE)
    c = pd.read_csv(os.path.join(INS, "cruzamentos.csv"))
    pesq = pd.read_csv(os.path.join(INS, "pesquisas.csv"))
    un = pd.read_parquet(os.path.join(VAR, a.unidade, "unidades.parquet"))
    un = un[un["uf"].notna()].reset_index(drop=True)
    sx, cor = composicao(un)
    cel = celulas(sx, cor)
    peso = un["pop_15m"].fillna(0).to_numpy(float)[:, None, None, None]
    comp_nac = (cel * peso).sum(0) / peso.sum()
    comp_reg = {r: (cel[un["uf"].isin(us)] * peso[un["uf"].isin(us)]).sum(0) / peso[un["uf"].isin(us)].sum() for r, us in REG.items()}
    comp_uf = {u: (cel[un["uf"] == u] * peso[un["uf"] == u]).sum(0) / peso[un["uf"] == u].sum() for u in un["uf"].unique()}

    md = marginais_datafolha(c, comp_nac, 2506)
    ma = marginais_atlas(c, pesq, comp_uf)
    ufs_atlas = sorted({m[4] for m in ma})
    geo_reg = list(REG)
    reg_unid = un["uf"].map(UF_REG).to_numpy()
    uf_unid = un["uf"].to_numpy()

    res = {}
    for nome in ("R1", "R2", "R3"):
        draws = np.full((a.reamostragens, len(un)), np.nan, np.float32)
        for b in range(a.reamostragens):
            md_b = reamostrar(md, rng) if b else md
            ma_b = reamostrar(ma, rng) if b else ma
            if nome == "R1":
                ef = ajustar(md_b, comp_nac, geo_reg, comp_reg)
                draws[b] = pos_estratificar(ef, cel, reg_unid)
            elif nome == "R2":
                # só sexo e UF: os efeitos de idade e cor ficam zerados (a Atlas não os traz legíveis)
                ef = ajustar(ma_b, comp_nac, ufs_atlas, comp_uf)
                p = pos_estratificar(ef, cel, uf_unid)
                draws[b] = np.where(np.isin(uf_unid, ufs_atlas), p, np.nan)
            else:
                ef_d = ajustar(md_b, comp_nac, geo_reg, comp_reg)
                # nível da UF: desloca o intercepto até a fatia da UF (pela Atlas) bater, mantendo os efeitos do Datafolha
                a0, bs, bi, bc, bg = ef_d
                geo = {r: bg.get(r, 0.0) for r in geo_reg}
                desloc = {}
                for u in ufs_atlas:
                    qs = [m for m in ma_b if m[4] == u]
                    alvo = sum(m[2]*m[3] for m in qs) / sum(m[3] for m in qs)
                    base = UF_REG[u]
                    f = lambda d: (pos_estratificar((a0, bs, bi, bc, {"x": geo[base] + d}), comp_uf[u][None], ["x"])[0] - alvo)**2
                    desloc[u] = minimize(lambda d: f(d[0]), [0.0], method="Nelder-Mead").x[0]
                gu = {u: geo[UF_REG[u]] + desloc.get(u, 0.0) for u in set(uf_unid) if u in UF_REG}
                draws[b] = pos_estratificar((a0, bs, bi, bc, gu), cel, uf_unid)
            if b == 0:
                print(f"{nome}: estimativa pontual nacional (ponderada pela pop. 15+) = "
                      f"{np.nansum(draws[0]*peso[:, 0, 0, 0])/peso[~np.isnan(draws[0]), 0, 0, 0].sum():.3f}", flush=True)
        res[nome] = draws
    out = un[["id_unidade", "uf", "cd_mun_ibge", "nome", "tipo", "pop_15m"]].copy()
    for nome, d in res.items():
        out[f"{nome}_p05"], out[f"{nome}_p50"], out[f"{nome}_p95"] = np.nanquantile(d, [.05, .5, .95], axis=0) \
            if not np.isnan(d).all() else (np.nan,)*3
    out.to_parquet(os.path.join(VAR, a.unidade, "mrp.parquet"), index=False)
    print(out[[c for c in out.columns if c.endswith("_p50")]].describe().round(3).to_string())


if __name__ == "__main__":
    main()
