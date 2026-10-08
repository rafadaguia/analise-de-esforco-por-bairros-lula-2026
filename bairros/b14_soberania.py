#!/usr/bin/env python3
"""Etapa B14: onde o tema "soberania nacional" pode ter força (hipótese derivada de dados agregados).

Não há pesquisa com recorte geográfico sobre o tema. Nacionalmente, 64% consideram correta a defesa da soberania
diante das tarifas dos EUA (Genial/Quaest, set/2025) e 47% concordam mais com Lula do que com Flávio (35%) sobre o
tarifaço (Genial/Quaest, 5–8/6/2026, BR-07661/2026). A força local do tema é aproximada por dois sinais objetivos:

  1. Exposição ao mercado dos EUA (Comex Stat/MDIC, exportações de 2025 por município, via API oficial):
     valor exportado aos EUA por eleitor e parcela das exportações do município que vai aos EUA. É o canal concreto
     do tarifaço (café, carne, suco de laranja, calçados, aviões, aço, frutas...).
     Limite: o Comex Stat atribui a exportação ao município do estabelecimento exportador (muitas vezes a sede),
     não ao local de produção. Municípios com exportação total por eleitor no 1% mais alto são marcados como
     "sede exportadora": o valor pode refletir a sede de grandes empresas (ex.: Rio de Janeiro, Petrobras).
  2. Amazônia Legal (defesa da Amazônia como pauta de soberania). Aproximação: AC, AM, AP, PA, RO, RR, TO, MT e os
     municípios do MA a oeste do meridiano de 44° W.

Nível de exposição (entre municípios que exportam aos EUA): índice = 0,6 × posto(US$ aos EUA por eleitor, em log)
+ 0,4 × posto(parcela EUA). Alta = 10% maiores, desde que exportem US$ 10 mi+ aos EUA e 20%+ do total vá para lá
(senão, média); média = 10–30%; baixa = o resto; "sem exportação aos EUA" à parte.

Saídas: bairros/insumos/contexto/soberania_municipios.csv; variantes/<U>/soberania_{rm,uf,areas}.csv
Uso: python bairros/b14_soberania.py --unidade U4
"""
import argparse, json, os, re, unicodedata
import numpy as np
import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CX = os.path.join(RAIZ, "dados_bairros", "outros", "comexstat")
AMAZONIA_UF = {"AC", "AM", "AP", "PA", "RO", "RR", "TO", "MT"}


def chave(nome, uf):
    s = unicodedata.normalize("NFKD", str(nome).lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", s) + "|" + uf


def municipios():
    p = pd.read_csv(os.path.join(RAIZ, "painel", "painel_municipios.csv"), usecols=["uf", "municipio", "cd_municipio_ibge", "aptos_26"])
    p = p.dropna(subset=["cd_municipio_ibge"]).astype({"cd_municipio_ibge": int})
    co = pd.read_csv(os.path.join(RAIZ, "dados", "geo", "municipios_coordenadas.csv"))[["codigo_ibge", "nome", "longitude"]]
    p = p.merge(co, left_on="cd_municipio_ibge", right_on="codigo_ibge", how="left")
    p["k"] = [chave(n if isinstance(n, str) else m, u) for n, m, u in zip(p["nome"], p["municipio"], p["uf"])]
    p["k2"] = [chave(m, u) for m, u in zip(p["municipio"], p["uf"])]
    return p


def exportacoes(p):
    def ler(n):
        d = pd.DataFrame(json.load(open(os.path.join(CX, f"exp_2025_{n}.json")))["data"]["list"])
        d[["nm", "uf"]] = d["noMunMinsgUf"].str.rsplit(" - ", n=1, expand=True)
        d["k"] = [chave(a, b) for a, b in zip(d["nm"], d["uf"])]
        return d.groupby("k")["metricFOB"].sum().astype(float)
    eua, tot = ler("eua"), ler("total")
    k_ok = set(p["k"]) | set(p["k2"])
    sem = [k for k in tot.index if k not in k_ok]
    m = p.copy()
    for col, s in (("exp_eua_usd", eua), ("exp_total_usd", tot)):
        m[col] = m["k"].map(s).fillna(m["k2"].map(s)).fillna(0.0)
    return m, sem


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--unidade", default="U4")
    a = ap.parse_args()
    p = municipios()
    m, sem_par = exportacoes(p)
    m["parcela_eua"] = np.where(m["exp_total_usd"] > 0, m["exp_eua_usd"] / m["exp_total_usd"], 0)
    m["eua_por_eleitor"] = m["exp_eua_usd"] / m["aptos_26"]
    tot_el = m["exp_total_usd"] / m["aptos_26"]
    m["sede_exportadora"] = tot_el > tot_el.quantile(0.99)
    exp = m["exp_eua_usd"] > 0
    idx = 0.6 * np.log1p(m.loc[exp, "eua_por_eleitor"]).rank(pct=True) + 0.4 * m.loc[exp, "parcela_eua"].rank(pct=True)
    m["indice_exposicao"] = np.nan
    m.loc[exp, "indice_exposicao"] = idx
    r = m["indice_exposicao"].rank(pct=True, ascending=False)
    m["exposicao_eua"] = np.where(~exp, "sem exportação aos EUA", np.where(r <= 0.10, "alta", np.where(r <= 0.30, "média", "baixa")))
    # "alta" exige economia local de fato exposta: US$ 10 mi+ aos EUA e 20%+ das exportações do município
    fraca = (m["exposicao_eua"] == "alta") & ((m["exp_eua_usd"] < 10e6) | (m["parcela_eua"] < 0.20))
    m.loc[fraca, "exposicao_eua"] = "média"
    m["amazonia_legal"] = m["uf"].isin(AMAZONIA_UF) | ((m["uf"] == "MA") & (m["longitude"] < -44))
    m["forca_soberania"] = np.select(
        [m["exposicao_eua"] == "alta", (m["exposicao_eua"] == "média") | m["amazonia_legal"]], ["alta", "média"], "baixa")
    m["motivo"] = [";".join(x for x, c in (("exportação aos EUA", e in ("alta", "média")), ("Amazônia Legal", am)) if c)
                   for e, am in zip(m["exposicao_eua"], m["amazonia_legal"])]
    cols = ["cd_municipio_ibge", "municipio", "uf", "aptos_26", "exp_eua_usd", "exp_total_usd", "parcela_eua", "eua_por_eleitor",
            "sede_exportadora", "exposicao_eua", "amazonia_legal", "forca_soberania", "motivo"]
    out_ctx = os.path.join(RAIZ, "bairros", "insumos", "contexto", "soberania_municipios.csv")
    m[cols].sort_values("eua_por_eleitor", ascending=False).to_csv(out_ctx, index=False)
    print(f"municípios: {len(m)} | exportam aos EUA: {int(exp.sum())} | nomes do Comex sem par no IBGE: {len(sem_par)}")
    print(m["forca_soberania"].value_counts().to_dict())
    print(m[exp].sort_values("indice_exposicao", ascending=False)[["municipio", "uf", "exp_eua_usd", "parcela_eua", "eua_por_eleitor", "sede_exportadora"]]
          .head(15).assign(exp_eua_usd=lambda x: (x.exp_eua_usd/1e6).round(0), parcela_eua=lambda x: (100*x.parcela_eua).round(0),
                           eua_por_eleitor=lambda x: x.eua_por_eleitor.round(0)).to_string(index=False))

    # RM, UF e áreas (bairros) da variante
    V = os.path.join(RAIZ, "variantes", a.unidade)
    es = pd.read_parquet(os.path.join(V, "MC", "esforco.parquet")) if os.path.exists(os.path.join(V, "MC", "esforco.parquet")) else None
    un = pd.read_parquet(os.path.join(V, "unidades.parquet"))[["id_unidade", "cd_mun_ibge", "nome", "uf", "nome_rm", "eleitores_2026"]]
    mm = m.set_index("cd_municipio_ibge")
    rmm = un.groupby("cd_mun_ibge")["nome_rm"].first()
    m["nome_rm"] = m["cd_municipio_ibge"].map(rmm)
    for nv, col in (("rm", "nome_rm"), ("uf", "uf")):
        g = m.dropna(subset=[col]).groupby(col).agg(aptos=("aptos_26", "sum"), exp_eua_usd=("exp_eua_usd", "sum"), exp_total_usd=("exp_total_usd", "sum"),
                                                     municipios_forca_alta=("forca_soberania", lambda s: int((s == "alta").sum())))
        g["eua_por_eleitor"] = g["exp_eua_usd"] / g["aptos"]; g["parcela_eua"] = g["exp_eua_usd"] / g["exp_total_usd"].replace(0, np.nan)
        g.sort_values("eua_por_eleitor", ascending=False).to_csv(os.path.join(V, f"soberania_{nv}.csv"))
        print(f"\n{nv.upper()} com mais exportação aos EUA por eleitor:\n" + g.sort_values("eua_por_eleitor", ascending=False).head(8)
              .assign(exp_eua_usd=lambda x: (x.exp_eua_usd/1e6).round(0), eua_por_eleitor=lambda x: x.eua_por_eleitor.round(0),
                      parcela_eua=lambda x: (100*x.parcela_eua).round(0))[["exp_eua_usd", "eua_por_eleitor", "parcela_eua", "municipios_forca_alta"]].to_string())
    ar = un.merge(m[["cd_municipio_ibge", "forca_soberania", "exposicao_eua", "amazonia_legal", "motivo", "sede_exportadora"]],
                  left_on="cd_mun_ibge", right_on="cd_municipio_ibge", how="left")
    if es is not None:
        ar = ar.merge(es[["id_unidade", "nivel_P2", "pot_p50"]], on="id_unidade", how="left")
        ar["coincide_baixo_esforco"] = (ar["forca_soberania"] == "alta") & (ar["nivel_P2"] >= 6)
        print(f"\náreas com força alta do tema e nível de esforço 6–7: {int(ar['coincide_baixo_esforco'].sum())}, "
              f"potencial somado {ar.loc[ar['coincide_baixo_esforco'], 'pot_p50'].sum():,.0f}")
    ar.to_csv(os.path.join(V, "soberania_areas.csv"), index=False)


if __name__ == "__main__":
    main()
