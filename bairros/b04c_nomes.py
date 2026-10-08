#!/usr/bin/env python3
"""Etapa B4c: nome para todas as áreas, com a fonte de cada nome registrada.

Ordem de preferência (coluna nome_fonte):
  ibge_bairro   bairro do IBGE (Censo 2022) com mais moradores na área. Se a área junta bairros e o maior
                tem menos de 60% da população: "A e B" (dois bairros com 20%+) ou "A e arredores"
  prefeitura    U3: nome do bairro na malha da prefeitura (já vem de b04)
  tse           área de locais de votação (U2/U4): bairro que o TSE mais declara entre os locais (eleitores)
  osm           OpenStreetMap: lugar place=suburb/neighbourhood/quarter que cai nos setores da área; o do setor
                mais populoso (suburb antes de neighbourhood). © colaboradores do OpenStreetMap, ODbL
  ibge_distrito subdistrito ou distrito do IBGE ("Distrito de X")
  rural         "Zona rural de <município>" (setores majoritariamente rurais, sem nenhum nome acima)
  municipio     o próprio município (área única)
Corrige o erro de b04 em que a área resultante da fusão de áreas pequenas podia herdar o rótulo (vazio) da
parte absorvida.

Uso: python bairros/b04c_nomes.py U1 U2 U3 U4
"""
import json, os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
from joblib import Parallel, delayed

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(RAIZ, "dados_bairros", "proc")
VAR = os.path.join(RAIZ, "variantes")
OSM = os.path.join(RAIZ, "dados_bairros", "osm", "bairros_osm_br.json")
SETORES = os.path.join(RAIZ, "dados_bairros", "ibge", "BR_setores_CD2022.gpkg")
ORDEM_OSM = {"suburb": 0, "quarter": 1, "neighbourhood": 2}


import re, unicodedata

PARTICULAS = (" De ", " Da ", " Do ", " Dos ", " Das ", " E ", " Di ", " Du ")


def titulo(s):
    s = " ".join(str(s).split())
    if not any(c.islower() for c in s):
        s = s.title()
    for p in PARTICULAS:
        s = s.replace(p, p.lower())
    return s


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s).lower()) if c.isalnum())


def limpar_tse(nm):
    """'SAO RAIMUNDO-ZONA URBANA' -> 'Sao Raimundo'; vazio se for só 'zona rural' ou genérico."""
    nm = re.sub(r"\s*[-–/]?\s*\(?\s*zona\s+(urbana|rural)\s*\)?\s*$", "", str(nm), flags=re.I)
    nm = re.sub(r"\s*[-–]\s*$", "", nm).strip(" -")
    if sem_acento(nm) in ("", "zonarural", "zonaurbana", "rural", "urbana", "naoinformado", "sembairro"):
        return ""
    return titulo(nm)


def osm_por_setor():
    """Lugares do OSM -> setor censitário onde caem (cache)."""
    cache = os.path.join(PROC, "osm_setor.parquet")
    if os.path.exists(cache):
        return pd.read_parquet(cache)
    el = json.load(open(OSM))["elements"]
    linhas = []
    for e in el:
        t = e.get("tags", {})
        if "name" not in t:
            continue
        lat, lon = (e["lat"], e["lon"]) if e["type"] == "node" else (e.get("center", {}).get("lat"), e.get("center", {}).get("lon"))
        if lat is None:
            continue
        linhas.append({"osm_id": f"{e['type'][0]}{e['id']}", "nome_osm": t["name"], "place": t.get("place"), "lat": lat, "lon": lon})
    o = pd.DataFrame(linhas)
    g = gpd.GeoDataFrame(o, geometry=gpd.points_from_xy(o["lon"], o["lat"]), crs=4326).to_crs(4674)
    ufs = [str(u) for u in (11, 12, 13, 14, 15, 16, 17, 21, 22, 23, 24, 25, 26, 27, 28, 29, 31, 32, 33, 35, 41, 42, 43, 50, 51, 52, 53)]
    def uf(c):
        st = gpd.read_file(SETORES, columns=["CD_SETOR"], where=f"CD_UF = '{c}'")
        b = st.total_bounds
        sub = g.cx[b[0]:b[2], b[1]:b[3]]
        j = gpd.sjoin(sub, st, how="inner", predicate="within")
        return pd.DataFrame(j[["osm_id", "nome_osm", "place", "CD_SETOR"]])
    r = pd.concat(Parallel(n_jobs=8)(delayed(uf)(u) for u in ufs)).drop_duplicates("osm_id")
    r.to_parquet(cache, index=False)
    print(f"OSM: {len(o):,} lugares com nome; {len(r):,} dentro de algum setor")
    return r


def nomear(variante, osm):
    pasta = os.path.join(VAR, variante)
    un = pd.read_parquet(os.path.join(pasta, "unidades.parquet"))
    su = pd.read_parquet(os.path.join(pasta, "setor_unidade.parquet")).drop_duplicates("CD_SETOR")
    cs = pd.read_parquet(os.path.join(PROC, "censo_setores.parquet"),
                         columns=["CD_SETOR", "CD_MUN", "NM_MUN", "NM_DIST", "NM_SUBDIST", "CD_BAIRRO", "NM_BAIRRO", "SITUACAO", "pop"])
    s = su.merge(cs, on="CD_SETOR", how="left")
    s["pop"] = s["pop"].fillna(0)
    nomes, fontes = {}, {}

    # 1) bairro do IBGE dominante (por população)
    b = s[s["CD_BAIRRO"].notna() & (s["CD_BAIRRO"] != ".") & s["NM_BAIRRO"].notna()]
    pb = b.groupby(["id_unidade", "NM_BAIRRO"])["pop"].sum().reset_index()
    tot = s.groupby("id_unidade")["pop"].sum()
    for uid, g in pb.sort_values("pop", ascending=False).groupby("id_unidade", sort=False):
        t = max(tot.get(uid, 0), 1)
        top, sh = g.iloc[0]["NM_BAIRRO"], g.iloc[0]["pop"] / t
        if sh >= 0.6 or len(g) == 1:
            nome = titulo(top)
        elif len(g) >= 2 and g.iloc[1]["pop"] / t >= 0.2 and (len(g) == 2 or g.iloc[2]["pop"] / t < 0.2):
            nome = f"{titulo(top)} e {titulo(g.iloc[1]['NM_BAIRRO'])}"
        else:
            nome = f"{titulo(top)} e arredores"
        nomes[uid], fontes[uid] = nome, "ibge_bairro"

    # grafia do OSM (com acentos) para nomes do TSE do mesmo município
    osm_mun = osm.merge(s[["CD_SETOR", "CD_MUN"]], on="CD_SETOR")
    grafia = {(int(m), sem_acento(n)): titulo(n) for m, n in zip(osm_mun["CD_MUN"], osm_mun["nome_osm"])}
    # bairro declarado ao TSE para o maior local de votação de cada área (2026)
    lu = pd.read_parquet(os.path.join(pasta, "local_unidade.parquet"))
    lg = pd.read_parquet(os.path.join(PROC, "locais_geo_2026.parquet"))
    lg["id_local"] = "2026-" + lg["uf"] + "-" + lg["cd_mun_tse"].astype(str) + "-" + lg["zona"].astype(str) + "-" + lg["nr_local"].astype(str)
    lt = lg.merge(lu[lu["ano"] == 2026][["id_local", "id_unidade"]], on="id_local")
    lt["limpo"] = lt["bairro_tse"].map(limpar_tse)
    lt = lt[lt["limpo"] != ""]
    lt["limpo"] = [grafia.get((int(m), sem_acento(n)), n) for m, n in zip(lt["cd_mun_ibge"], lt["limpo"])]
    tse = (lt.groupby(["id_unidade", "limpo"])["eleitores"].sum().reset_index()
           .sort_values("eleitores", ascending=False).drop_duplicates("id_unidade").set_index("id_unidade")["limpo"])

    # 2) prefeitura (U3) e TSE (áreas de locais): o nome já gravado por b04, quando válido
    for _, r in un.iterrows():
        uid, nm = r["id_unidade"], r["nome"]
        valido = isinstance(nm, str) and nm.strip() and not nm.startswith("Área de locais") and "nan" != nm.strip().lower()
        if uid.startswith("P") and valido:
            nomes[uid], fontes[uid] = titulo(nm), "prefeitura"
        elif uid.startswith("A") and uid not in nomes and uid in tse.index:
            nomes[uid], fontes[uid] = f"{tse[uid]} e entorno", "tse"

    # 3) OpenStreetMap: lugar no setor mais populoso da área
    o = osm.merge(s[["CD_SETOR", "id_unidade", "pop"]], on="CD_SETOR")
    o["ordem"] = o["place"].map(ORDEM_OSM).fillna(3)
    o = o.sort_values(["id_unidade", "ordem", "pop"], ascending=[True, True, False])
    cont = o.groupby("id_unidade")["nome_osm"].nunique()
    for uid, g in o.groupby("id_unidade", sort=False):
        if uid in nomes or uid.startswith("R"):
            continue
        nm = titulo(g.iloc[0]["nome_osm"])
        nomes[uid], fontes[uid] = (nm if cont[uid] == 1 else f"{nm} e arredores"), "osm"

    # 3b) demais áreas sem nome: localidade que o TSE declara para os locais da área (povoados, vilas)
    for _, r in un.iterrows():
        uid = r["id_unidade"]
        if uid not in nomes and not uid.startswith(("R", "M")) and uid in tse.index:
            nomes[uid], fontes[uid] = f"{tse[uid]} e entorno", "tse"

    # 4) distrito/subdistrito, zona rural, município
    info = s.groupby("id_unidade").agg(mun=("NM_MUN", "first"), dist=("NM_DIST", lambda x: x.mode().iat[0] if x.notna().any() else None),
                                       sub=("NM_SUBDIST", lambda x: x.mode().iat[0] if x.notna().any() else None),
                                       rural=("SITUACAO", lambda x: (x == "Rural").mean()),
                                       ndist=("NM_DIST", "nunique"))
    for _, r in un.iterrows():
        uid = r["id_unidade"]
        if uid in nomes:
            continue
        if uid.startswith("R"):
            nomes[uid], fontes[uid] = "Locais de votação não localizados", "residual"; continue
        i = info.loc[uid] if uid in info.index else None
        mun = titulo(i["mun"]) if i is not None and isinstance(i["mun"], str) else titulo(r.get("municipio") or "")
        if uid.startswith("M"):
            nomes[uid], fontes[uid] = mun, "municipio"
        elif i is not None and isinstance(i["sub"], str) and uid.startswith("S"):
            nomes[uid], fontes[uid] = f"Subdistrito {titulo(i['sub'])}", "ibge_distrito"
        elif i is not None and i["rural"] >= 0.5:
            d = titulo(i["dist"]) if isinstance(i["dist"], str) else mun
            nomes[uid], fontes[uid] = (f"Zona rural do distrito de {d}" if d != mun else f"Zona rural de {mun}"), "rural"
        elif i is not None and isinstance(i["dist"], str) and titulo(i["dist"]) != mun:
            nomes[uid], fontes[uid] = f"Distrito de {titulo(i['dist'])}", "ibge_distrito"
        else:
            nomes[uid], fontes[uid] = f"Demais áreas de {mun}", "municipio"

    un["nome"] = un["id_unidade"].map(nomes)
    un["nome_fonte"] = un["id_unidade"].map(fontes)
    # nomes repetidos no mesmo município: acrescenta o distrito ou um número para distinguir
    dup = un.duplicated(["cd_mun_ibge", "nome"], keep=False) & un["nome"].notna()
    for (m, n), g in un[dup].groupby(["cd_mun_ibge", "nome"]):
        for k, idx in enumerate(g.sort_values("eleitores_2026", ascending=False).index):
            if k:
                un.at[idx, "nome"] = f"{n} ({k + 1})"
    tmp = os.path.join(pasta, "unidades.parquet.tmp")
    un.to_parquet(tmp, index=False)
    os.replace(tmp, os.path.join(pasta, "unidades.parquet"))   # troca atômica: quem estiver lendo não pega arquivo pela metade
    vazios = un["nome"].isna().sum()
    print(f"{variante}: {len(un):,} áreas | sem nome: {vazios} | fontes: {un['nome_fonte'].value_counts().to_dict()}")


if __name__ == "__main__":
    osm = osm_por_setor()
    for v in sys.argv[1:] or ["U1", "U2", "U3", "U4"]:
        nomear(v, osm)
