#!/usr/bin/env python3
"""Etapa B3: geocodificação dos locais de votação e controle de qualidade.

Cada local de votação (TSE) é posto no setor censitário do Censo 2022 em que cai a
coordenada publicada pelo TSE. A qualidade é medida, não presumida:

  status_geo
    tse_ok          a coordenada do TSE cai num setor do município certo
    tse_outro_mun   cai em outro município: coordenada suspeita, descartada
    sem_coord       o TSE não publicou coordenada válida
    outro_ano       sem coordenada boa neste ano; usa a do mesmo local no outro ano
                    (mesmo município, zona e nº do local, ou mesmo nome e endereço)
    nome_bairro     sem coordenada; o bairro declarado ao TSE casa com o nome de um
                    bairro do IBGE no município (similaridade >= 90). Vai para o bairro,
                    mas sem setor
    municipio       nada disso: o local entra só no nível do município

  Indicador de precisão (só para os tse_ok): concordância entre o bairro que o TSE
  declara e o bairro do IBGE onde o ponto cai. Discordância não prova erro (nomes de
  bairro populares diferem dos oficiais), mas a taxa por UF mostra onde desconfiar.

Saída: dados_bairros/proc/locais_geo_{ano}.parquet
"""
import os, sys, unicodedata
import numpy as np
import pandas as pd
import geopandas as gpd
from joblib import Parallel, delayed
from rapidfuzz import fuzz, process

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(RAIZ, "dados_bairros", "proc")
IBGE = os.path.join(RAIZ, "dados_bairros", "ibge")
SETORES = os.path.join(IBGE, "BR_setores_CD2022.gpkg")
CAMPOS_SETOR = ["CD_SETOR", "CD_MUN", "CD_DIST", "CD_SUBDIST", "CD_BAIRRO", "NM_BAIRRO", "SITUACAO"]


def norm(s):
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()
    for a, b in (("JD ", "JARDIM "), ("JD.", "JARDIM "), ("VL ", "VILA "), ("VL.", "VILA "), ("PQ ", "PARQUE "),
                 ("PQ.", "PARQUE "), ("CJ ", "CONJUNTO "), ("RES ", "RESIDENCIAL "), ("STA ", "SANTA "), ("STO ", "SANTO ")):
        s = s.replace(a, b)
    return " ".join("".join(c if c.isalnum() else " " for c in s).split())


def correspondencia_municipios():
    """TSE -> IBGE, a partir do painel municipal da versão atual (5.571 municípios)."""
    p = pd.read_csv(os.path.join(RAIZ, "painel", "painel_municipios.csv"),
                    usecols=["uf", "cd_mun_tse", "cd_municipio_ibge"])
    p = p.dropna().astype({"cd_mun_tse": int, "cd_municipio_ibge": int})
    return p.rename(columns={"cd_municipio_ibge": "cd_mun_ibge"})


def juntar_uf(uf_cod, pts):
    """Ponto em polígono contra os setores de uma UF (roda em processo separado)."""
    st = gpd.read_file(SETORES, columns=CAMPOS_SETOR, where=f"CD_UF = '{uf_cod}'", engine="pyogrio")
    g = gpd.GeoDataFrame(pts, geometry=gpd.points_from_xy(pts["lon"], pts["lat"]), crs=4674)
    if st.crs is not None and st.crs.to_epsg() != 4674:
        g = g.to_crs(st.crs)
    j = gpd.sjoin(g, st, how="left", predicate="within")
    j = j[~j.index.duplicated()]
    return pd.DataFrame(j.drop(columns=["geometry", "index_right"], errors="ignore"))


def processar(ano, outro):
    saida = os.path.join(PROC, f"locais_geo_{ano}.parquet")
    loc = pd.read_parquet(os.path.join(PROC, f"locais_{ano}.parquet"))
    cw = correspondencia_municipios()
    loc = loc.merge(cw, on=["uf", "cd_mun_tse"], how="left")
    print(f"{ano}: {len(loc):,} locais; sem código IBGE: {loc['cd_mun_ibge'].isna().sum()}")

    # fallback 1: coordenada do mesmo local no outro ano (se lá ela for boa)
    oa = os.path.join(PROC, f"locais_geo_{outro}.parquet")
    if os.path.exists(oa):
        o = pd.read_parquet(oa)
        o = o[o["status_geo"] == "tse_ok"]
        k = ["uf", "cd_mun_tse", "zona", "nr_local"]
        loc = loc.merge(o[k + ["lat", "lon"]].rename(columns={"lat": "lat_o", "lon": "lon_o"}), on=k, how="left")
        o["chave_nome"] = o["nm_local"].map(norm) + "|" + o["endereco"].map(norm)
        loc["chave_nome"] = loc["nm_local"].map(norm) + "|" + loc["endereco"].map(norm)
        on = o.drop_duplicates(["cd_mun_tse", "chave_nome"])[["cd_mun_tse", "chave_nome", "lat", "lon"]]
        loc = loc.merge(on.rename(columns={"lat": "lat_n", "lon": "lon_n"}), on=["cd_mun_tse", "chave_nome"], how="left")
        loc["lat_o"] = loc["lat_o"].fillna(loc["lat_n"]); loc["lon_o"] = loc["lon_o"].fillna(loc["lon_n"])
        loc = loc.drop(columns=["lat_n", "lon_n", "chave_nome"])
    else:
        loc["lat_o"] = np.nan; loc["lon_o"] = np.nan

    loc["uf_cod"] = (loc["cd_mun_ibge"] // 100000).astype("Int64").astype(str)

    def juntar(df, colx, coly):
        tem = df[df[coly].notna() & df["cd_mun_ibge"].notna()].copy()
        tem["lat"], tem["lon"] = tem[coly], tem[colx]
        partes = Parallel(n_jobs=14)(delayed(juntar_uf)(u, g[["lat", "lon"]]) for u, g in tem.groupby("uf_cod"))
        r = pd.concat(partes)
        return r[CAMPOS_SETOR]

    # 1ª passada: coordenada do próprio ano
    j1 = juntar(loc, "lon", "lat")
    loc = loc.join(j1)
    loc["CD_MUN"] = pd.to_numeric(loc["CD_MUN"], errors="coerce")
    ok = loc["CD_MUN"].notna() & (loc["CD_MUN"] == loc["cd_mun_ibge"])
    loc["status_geo"] = np.where(ok, "tse_ok", np.where(loc["lat"].notna(), "tse_outro_mun", "sem_coord"))
    loc.loc[~ok, CAMPOS_SETOR] = np.nan

    # 2ª passada: coordenada do outro ano para quem não ficou ok
    falta = ~ok & loc["lat_o"].notna()
    if falta.any():
        j2 = juntar(loc[falta], "lon_o", "lat_o")
        j2["CD_MUN"] = pd.to_numeric(j2["CD_MUN"], errors="coerce")
        bom = j2.index[j2["CD_MUN"] == loc.loc[j2.index, "cd_mun_ibge"]]
        loc.loc[bom, CAMPOS_SETOR] = j2.loc[bom, CAMPOS_SETOR]
        loc.loc[bom, ["lat", "lon"]] = loc.loc[bom, ["lat_o", "lon_o"]].to_numpy()
        loc.loc[bom, "status_geo"] = "outro_ano"

    # 3ª: nome do bairro declarado ao TSE contra os bairros do IBGE do município
    bai = gpd.read_file(os.path.join(IBGE, "BR_bairros_CD2022.gpkg"), columns=["CD_MUN", "CD_BAIRRO", "NM_BAIRRO"],
                        ignore_geometry=True, engine="pyogrio")
    bai["CD_MUN"] = pd.to_numeric(bai["CD_MUN"])
    bai["nn"] = bai["NM_BAIRRO"].map(norm)
    por_mun = {m: g for m, g in bai.groupby("CD_MUN")}
    sem = loc.index[~loc["status_geo"].isin(["tse_ok", "outro_ano"])]
    for i in sem:
        g = por_mun.get(loc.at[i, "cd_mun_ibge"])
        nb = norm(loc.at[i, "bairro_tse"])
        if g is None or not nb:
            continue
        m = process.extractOne(nb, g["nn"].tolist(), scorer=fuzz.token_sort_ratio, score_cutoff=90)
        if m:
            r = g.iloc[m[2]]
            loc.at[i, "CD_BAIRRO"], loc.at[i, "NM_BAIRRO"] = r["CD_BAIRRO"], r["NM_BAIRRO"]
            loc.at[i, "CD_MUN"] = loc.at[i, "cd_mun_ibge"]
            loc.at[i, "status_geo"] = "nome_bairro"
    resto = ~loc["status_geo"].isin(["tse_ok", "outro_ano", "nome_bairro"])
    loc.loc[resto, "status_geo"] = "municipio"
    loc.loc[resto, "CD_MUN"] = loc.loc[resto, "cd_mun_ibge"]

    # precisão: o bairro declarado ao TSE bate com o bairro do IBGE do ponto?
    pts = loc["status_geo"].isin(["tse_ok", "outro_ano"]) & loc["NM_BAIRRO"].notna()
    a, b = loc.loc[pts, "bairro_tse"].map(norm), loc.loc[pts, "NM_BAIRRO"].map(norm)
    conc = pd.Series([float(fuzz.token_set_ratio(x, y) >= 85) if x else np.nan for x, y in zip(a, b)], index=a.index)
    loc["bairro_concorda"] = conc.reindex(loc.index)

    loc = loc.drop(columns=["lat_o", "lon_o", "uf_cod"])
    loc.to_parquet(saida, index=False)
    t = loc.groupby("status_geo")["eleitores"].agg(["size", "sum"])
    t["pct_eleitores"] = 100*t["sum"]/t["sum"].sum()
    print(t.round(2).to_string())
    print(f"concordância bairro TSE x IBGE (onde há bairro IBGE): {100*loc['bairro_concorda'].mean():.1f}% dos locais")


if __name__ == "__main__":
    anos = [int(a) for a in sys.argv[1:]] or [2026, 2022]
    # a ordem importa: o 2º ano usa o 1º como fallback; roda o 1º de novo no fim para ele usar o 2º
    processar(anos[0], anos[1])
    processar(anos[1], anos[0])
    os.remove(os.path.join(PROC, f"locais_geo_{anos[0]}.parquet"))
    processar(anos[0], anos[1])
