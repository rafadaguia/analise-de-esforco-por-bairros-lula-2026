#!/usr/bin/env python3
"""Etapa B4d: infraestrutura urbana por área (Censo 2022, agregados por setor), para os temas por bairro.

Por área: % de domicílios sem esgoto por rede geral/pluvial ou fossa ligada à rede, sem água da rede geral, sem lixo
coletado no domicílio, e % da população em setores de favelas e comunidades urbanas (código CD_FCU do IBGE).
"X" (sigilo) = ausente; as proporções usam só os setores com o dado.

Saída: variantes/<U>/infra_areas.parquet
Uso: python bairros/b04d_infra.py U4 U1
"""
import io, os, sys, zipfile
import numpy as np
import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IBGE = os.path.join(RAIZ, "dados_bairros", "ibge")
PROC = os.path.join(RAIZ, "dados_bairros", "proc")


def ler(zipn, cols):
    z = zipfile.ZipFile(os.path.join(IBGE, zipn)); n = [x for x in z.namelist() if x.endswith(".csv")][0]
    raw = z.read(n)
    try:
        txt = raw.decode("utf-8")
    except UnicodeDecodeError:
        txt = raw.decode("latin-1")
    d = pd.read_csv(io.StringIO(txt), sep=";", dtype=str)
    d.columns = ["CD_SETOR" if c.lower() in ("cd_setor", "setor") else c for c in d.columns]
    d = d[["CD_SETOR"] + [c for c in cols if c in d.columns]]
    for c in cols:
        if c in d:
            d[c] = pd.to_numeric(d[c].str.replace(",", ".").replace("X", np.nan), errors="coerce")
    return d


def setores():
    cache = os.path.join(PROC, "infra_setores.parquet")
    if os.path.exists(cache):
        return pd.read_parquet(cache)
    dic = pd.read_excel(os.path.join(IBGE, "dicionario_agregados.xlsx"), sheet_name="Dicionário não PCT")
    dic.columns = ["tipo", "tema", "var", "desc"]
    for v in ("V00309", "V00310", "V00111", "V00397"):
        print(v, dic.loc[dic["var"] == v, "desc"].iat[0][-110:])
    d2 = ler("setores_caracteristicas_domicilio2_BR_20250417.zip", ["V00309", "V00310", "V00111", "V00397"])
    b = ler("setores_basico_BR_20260520.zip", ["v0007", "v0001"]).merge(
        pd.read_csv(io.StringIO(zipfile.ZipFile(os.path.join(IBGE, "setores_basico_BR_20260520.zip")).read(
            [n for n in zipfile.ZipFile(os.path.join(IBGE, "setores_basico_BR_20260520.zip")).namelist() if n.endswith(".csv")][0]).decode("latin-1")),
            sep=";", dtype=str, usecols=["CD_SETOR", "CD_FCU"]), on="CD_SETOR", how="left")
    d = b.merge(d2, on="CD_SETOR", how="left").rename(columns={"v0007": "dom", "v0001": "pop"})
    d["favela"] = d["CD_FCU"].notna() & (d["CD_FCU"] != ".")
    d.to_parquet(cache, index=False)
    return d


def main(variantes):
    s = setores()
    print(f"setores em favela/comunidade urbana: {int(s['favela'].sum()):,} ({100*s.loc[s['favela'], 'pop'].sum()/s['pop'].sum():.1f}% da população)")
    for v in variantes:
        su = pd.read_parquet(os.path.join(RAIZ, "variantes", v, "setor_unidade.parquet")).drop_duplicates("CD_SETOR")
        x = su.merge(s, on="CD_SETOR", how="left")
        ok = x["V00309"].notna() & x["dom"].notna()
        g = x.groupby("id_unidade")
        out = pd.DataFrame({
            "pct_sem_esgoto_adequado": 100 * (1 - (x[ok]["V00309"] + x[ok]["V00310"].fillna(0)).groupby(x[ok]["id_unidade"]).sum()
                                               / x[ok].groupby("id_unidade")["dom"].sum()),
            "pct_sem_agua_rede": 100 * (1 - x[ok].groupby("id_unidade")["V00111"].sum() / x[ok].groupby("id_unidade")["dom"].sum()),
            "pct_sem_coleta_lixo": 100 * (1 - x[ok].groupby("id_unidade")["V00397"].sum() / x[ok].groupby("id_unidade")["dom"].sum()),
            "pct_pop_favela": 100 * x[x["favela"]].groupby("id_unidade")["pop"].sum().reindex(g.size().index).fillna(0) / g["pop"].sum(),
        }).clip(0, 100).reset_index()
        out.to_parquet(os.path.join(RAIZ, "variantes", v, "infra_areas.parquet"), index=False)
        print(v, out.describe().loc[["mean", "50%", "max"]].round(1).to_string())


if __name__ == "__main__":
    main(sys.argv[1:] or ["U4"])
