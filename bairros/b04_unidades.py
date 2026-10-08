#!/usr/bin/env python3
"""Etapa B4: unidades de análise abaixo do município, em três variantes.

  U1  malha de bairros do IBGE (Censo 2022). Setor sem bairro cai no subdistrito, depois no
      distrito e, por último, no município (só quando o município tem mais de uma dessas
      divisões; senão a unidade é o próprio município).
  U2  áreas de influência dos locais de votação: cada setor censitário vai para o local de
      votação de 2026 mais próximo no mesmo município, e os locais são agrupados (k-means sobre
      as coordenadas, semente fixa) em áreas de cerca de ALVO_U2 eleitores.
  U3  malhas de bairros das prefeituras, onde existirem e forem abertas (dados_bairros/prefeituras);
      nos demais municípios, U1.
  U4  híbrida (versão principal desde 08/10): U1 onde o IBGE divide o município; onde a U1 deixaria o
      município numa área só (95 municípios com 50 mil+ eleitores, entre eles São Luís, Sorocaba e Rio
      Branco), as áreas de influência dos locais de votação da U2, nomeadas pelo bairro que o TSE mais
      declara entre os locais de cada área.

Em todas: unidades com menos de MIN_APTOS eleitores aptos em 2026 são fundidas à unidade
mais próxima do mesmo município (distância entre centróides de locais), para não haver
unidades em que meia dúzia de seções decida a taxa. Locais sem localização formam a unidade
residual "não localizado" do município (tipo = residual); ela entra nos totais, mas não no ranking.

Limite essencial: o eleitor vota no local de votação, não onde mora. A unidade descreve quem
vota ali; o perfil do Censo descreve quem mora ali. As duas coisas se sobrepõem, mas não são iguais.

Saídas em variantes/<U>/:
  unidades.parquet         id_unidade, tipo, nome, município, UF, RM, perfil do Censo
  secao_unidade.parquet    (ano, uf, cd_mun_tse, zona, secao) -> id_local, id_unidade, município, RM, UF
  unidades.gpkg            contornos (para o mapa; dissolve dos setores ou polígono da prefeitura)
  medidas.json             cobertura, tamanho médio, precisão da geocodificação
"""
import argparse, json, os, sys, unicodedata
import numpy as np
import pandas as pd
import geopandas as gpd
from joblib import Parallel, delayed
from scipy.spatial import cKDTree
from sklearn.cluster import KMeans

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(RAIZ, "dados_bairros", "proc")
IBGE = os.path.join(RAIZ, "dados_bairros", "ibge")
PREF = os.path.join(RAIZ, "dados_bairros", "prefeituras")
CTX = os.path.join(RAIZ, "bairros", "insumos", "contexto")
VAR = os.path.join(RAIZ, "variantes")
MIN_APTOS = 1000
ALVO_U2 = 10000
SEMENTE = 20261007
CONTAGENS = ["pop", "domicilios", "pop_15m", "homens_15m", "mulheres_15m", "branca", "preta", "amarela", "parda",
             "indigena", "alfabetizados_15m", "resp_com_renda", "renda_resp_soma"] + \
            [f"{s}_{f}" for s in "mf" for f in ("15_19", "20_24", "25_29", "30_39", "40_49", "50_59", "60_69", "70m")]

# camada escolhida em cada município com malha da prefeitura (arquivo relativo à pasta do município).
# São Paulo não tem bairros oficiais: os 96 distritos municipais são a divisão usada pela prefeitura.
# Brasília: regiões administrativas. Goiânia veio vazia e Palmas em vários KML regionais: ficam com U1.
CAMADAS_U3 = {
    1100205: "ba_bairros.geojson", 1302603: "bairros_implurb_semed.geojson", 2211001: "BAIRROS_2013/BAIRROS_2013.shp",
    2304400: "bairros_2025.kmz", 2408102: "limite_bairros.zip", 2507507: "bairros.zip",
    2611606: "bairros-do-recife.geojson", 2704302: "bairros de maceio.shp", 2800308: "bairros_2023.geojson",
    2927408: "bairro_oficial.geojson", 3106200: "bairro_oficial.geojson", 3136702: "ter_limites_bairros.geojson",
    3205309: "limite_bairros_lei_8611_2013.geojson", 3301702: "limite_bairro_gpu_smu.geojson",
    3303302: "limite_de_bairros.geojson", 3304557: "limite_de_bairros.geojson", 3513801: "bairro.geojson",
    3518800: "pg_bairros.zip", 3530607: "abairramento.kml", 3547809: "SIGA_LIM_BAIRROS_OFICIAL.geojson",
    3548500: "santos_bairros.geojson", 3548708: "bairro_SBC.zip", 3550308: "distrito_municipal.geojson",
    4106902: "DIVISA_DE_BAIRROS_SIRGAS.zip", 4113700: "bairros_londrina_lei13718.geojson",
    4115200: "bairro_maringa.geojson", 4119905: "limites_bairros.zip", 4205407: "gvw_bairros.geojson",
    4314902: "bairros_lc12112_16.zip", 5300108: "regioes_administrativas.geojson",
}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return "".join(c for c in s if c.isalnum())


# ------------------------------------------------------------------ insumos comuns

def pontos_setores():
    """Ponto representativo de cada setor (cache), calculado em paralelo por UF."""
    cache = os.path.join(PROC, "setores_pontos.parquet")
    if os.path.exists(cache):
        return pd.read_parquet(cache)
    def uf(c):
        g = gpd.read_file(os.path.join(IBGE, "BR_setores_CD2022.gpkg"), columns=["CD_SETOR"], where=f"CD_UF = '{c}'")
        p = g.geometry.representative_point()
        return pd.DataFrame({"CD_SETOR": g["CD_SETOR"], "lon": p.x, "lat": p.y})
    ufs = sorted(pd.read_parquet(os.path.join(PROC, "censo_setores.parquet"), columns=["CD_UF"])["CD_UF"].unique())
    d = pd.concat(Parallel(n_jobs=14)(delayed(uf)(str(int(u))) for u in ufs))
    d.to_parquet(cache, index=False)
    return d


def rm_por_municipio():
    """RM/RIDE/aglomeração urbana oficial (IBGE). Sem ela, a concentração urbana do Censo 2022."""
    arq = os.path.join(CTX, "rm.csv")
    if os.path.exists(arq):
        r = pd.read_csv(arq, dtype={"cd_municipio_ibge": int})
        r = r[r["nome_rm"].notna()][["cd_municipio_ibge", "nome_rm", "tipo"]]
        return r.rename(columns={"cd_municipio_ibge": "cd_mun_ibge", "tipo": "tipo_rm"})
    return pd.DataFrame(columns=["cd_mun_ibge", "nome_rm", "tipo_rm"])


def xy(lat, lon):
    """Coordenadas planas aproximadas em km (suficiente para vizinho mais próximo dentro de um município)."""
    return np.c_[np.asarray(lon) * 111.32 * np.cos(np.radians(np.asarray(lat))), np.asarray(lat) * 110.57]


# ---------------------------------------------------------------- atribuição

def unidade_u1(cs):
    """Código U1 de cada setor."""
    sub_n = cs[cs["CD_SUBDIST"] != "."].groupby("CD_MUN")["CD_SUBDIST"].nunique()
    dis_n = cs.groupby("CD_MUN")["CD_DIST"].nunique()
    tem_b = cs["CD_BAIRRO"].notna() & (cs["CD_BAIRRO"] != ".")
    m = cs["CD_MUN"]
    usa_sub = m.map(sub_n).fillna(0) > 1
    usa_dis = m.map(dis_n).fillna(0) > 1
    uid = np.where(tem_b, "B" + cs["CD_BAIRRO"].astype(str),
          np.where(usa_sub & (cs["CD_SUBDIST"] != "."), "S" + cs["CD_SUBDIST"].astype(str),
          np.where(usa_dis, "D" + cs["CD_DIST"].astype(str), "M" + m.astype(int).astype(str))))
    tipo = np.where(tem_b, "bairro", np.where(usa_sub & (cs["CD_SUBDIST"] != "."), "subdistrito",
           np.where(usa_dis, "distrito", "municipio")))
    nome = np.where(tem_b, cs["NM_BAIRRO"], np.where(tipo == "subdistrito", cs["NM_SUBDIST"],
           np.where(tipo == "distrito", cs["NM_DIST"], cs["NM_MUN"])))
    # setores sem bairro dentro de municípios com bairros: "demais áreas" do distrito
    nome = np.where((tipo != "bairro") & m.isin(cs.loc[tem_b, "CD_MUN"]), "Demais áreas: " + pd.Series(nome).astype(str), nome)
    return pd.DataFrame({"CD_SETOR": cs["CD_SETOR"], "id_unidade": uid, "tipo": tipo, "nome": nome})


def unidade_u2(cs, pts, loc26):
    """Setor -> local de 2026 mais próximo (mesmo município) -> grupo de locais de ~ALVO_U2 eleitores."""
    s = cs[["CD_SETOR", "CD_MUN", "NM_MUN"]].merge(pts, on="CD_SETOR")
    l = loc26[loc26["status_geo"].isin(["tse_ok", "outro_ano"])].copy()
    saida_setor, saida_local = [], []
    for mun, ls in l.groupby("cd_mun_ibge"):
        ss = s[s["CD_MUN"] == mun]
        k = max(1, int(round(ls["eleitores"].sum() / ALVO_U2)))
        k = min(k, len(ls))
        if k > 1:
            km = KMeans(n_clusters=k, n_init=4, random_state=SEMENTE).fit(xy(ls["lat"], ls["lon"]), sample_weight=ls["eleitores"])
            grupo = km.labels_
        else:
            grupo = np.zeros(len(ls), int)
        ids = np.array([f"A{int(mun)}_{g:03d}" if k > 1 else f"M{int(mun)}" for g in grupo])
        saida_local.append(pd.DataFrame({"id_local": ls["id_local"].values, "id_unidade": ids}))
        if len(ss):
            _, j = cKDTree(xy(ls["lat"], ls["lon"])).query(xy(ss["lat"], ss["lon"]))
            saida_setor.append(pd.DataFrame({"CD_SETOR": ss["CD_SETOR"].values, "id_unidade": ids[j]}))
    st = pd.concat(saida_setor)
    st["tipo"] = np.where(st["id_unidade"].str.startswith("A"), "area_local", "municipio")
    return st, pd.concat(saida_local)


def escolher_campo_nome(g):
    """Campo com o nome do bairro: texto, quase único por polígono, curto, com nome sugestivo."""
    melhor, nota_max = None, -1
    for c in g.columns:
        if c == "geometry":
            continue
        v = g[c].dropna().astype(str)
        if len(v) == 0 or v.str.fullmatch(r"[\d.,\-\s]+").mean() > 0.5:
            continue
        unic = v.nunique() / len(g)
        tam = v.str.len().median()
        nome = c.lower()
        nota = unic + (2 if any(k in nome for k in ("nome_bairr", "nm_bairr", "nomebairr", "no_bairr", "nm_distr", "nome_distr", "nm_ra", "nome_ra")) else 0) \
            + (1 if any(k in nome for k in ("bairro", "nome", "name", "nm_", "distrito", "ra_", "regiao")) else 0) \
            - (2 if any(k in nome for k in ("usuario", "editor", "hist", "obs", "data", "cod", "id", "area", "perim", "lei", "description", "descr")) else 0) \
            - (1 if not (3 <= tam <= 45) else 0)
        if nota > nota_max:
            melhor, nota_max = c, nota
    return melhor


def ler_camada(mun, rel):
    caminho = os.path.join(PREF, [d for d in os.listdir(PREF) if d.startswith(str(mun))][0], rel)
    if caminho.endswith(".kmz") or caminho.endswith(".zip"):
        caminho = "/vsizip/" + caminho
        if rel.endswith(".zip"):
            import zipfile
            z = zipfile.ZipFile(caminho[len("/vsizip/"):])
            shp = [n for n in z.namelist() if n.lower().endswith((".shp", ".geojson", ".gpkg", ".kml"))]
            caminho += "/" + shp[0]
        else:
            caminho += "/doc.kml"
    import pyogrio
    camadas = pyogrio.list_layers(caminho)
    # KML com várias camadas (Fortaleza: rótulos e polígonos): a camada com polígonos
    poli = [c for c, t in camadas if t and "Polygon" in t] or [c for c, _ in camadas if "POLIG" in c.upper()] or [camadas[0][0]]
    try:
        g = gpd.read_file(caminho, layer=poli[0])
    except UnicodeDecodeError:
        g = gpd.read_file(caminho, layer=poli[0], encoding="latin-1")
    if g.crs is None:
        g = g.set_crs(4674 if g.total_bounds[0] < 0 and abs(g.total_bounds[0]) < 180 else 31983, allow_override=True)
    g = g.to_crs(4674)
    # KML/KMZ trazem polígonos dentro de coleções: fica só a parte poligonal
    from shapely.geometry import MultiPolygon
    def poligonal(geom):
        if geom is None or geom.geom_type in ("Polygon", "MultiPolygon"):
            return geom
        partes = [p for p in getattr(geom, "geoms", []) if p.geom_type in ("Polygon", "MultiPolygon")]
        polys = [q for p in partes for q in (p.geoms if p.geom_type == "MultiPolygon" else [p])]
        return MultiPolygon(polys) if polys else None
    g["geometry"] = g.geometry.apply(poligonal)
    g = g[g.geometry.notna() & ~g.geometry.is_empty].copy()
    campo = escolher_campo_nome(g)
    rotulos = [c for c, _ in camadas if c != poli[0]]
    if campo is None and rotulos:  # nomes numa camada de pontos à parte (Fortaleza)
        r = gpd.read_file(caminho, layer=rotulos[0]).to_crs(4674)
        cr = escolher_campo_nome(r)
        if cr:
            j = gpd.sjoin(g, r[[cr, "geometry"]], how="left", predicate="contains")
            g = j[~j.index.duplicated()].drop(columns="index_right")
            campo = cr
    def conserta(t):  # UTF-8 lido como Latin-1 ("GalvÃ£o")
        try:
            return t.encode("latin-1").decode("utf-8") if "Ã" in t else t
        except (UnicodeEncodeError, UnicodeDecodeError):
            return t
    g["nome"] = g[campo].astype(str).map(conserta) if campo else [f"Área {i+1}" for i in range(len(g))]
    g["id_unidade"] = [f"P{mun}_{i:04d}" for i in range(len(g))]
    return g[["id_unidade", "nome", "geometry"]], campo


def unidade_u3(cs, pts, u1, loc_todos):
    """Malha da prefeitura onde houver; U1 no resto. Devolve setor->unidade e local->unidade (só onde há malha)."""
    st, lc, meta = [], [], {}
    for mun, rel in CAMADAS_U3.items():
        try:
            g, campo = ler_camada(mun, rel)
        except Exception as e:  # noqa: BLE001 — malha ilegível: o município fica com U1
            meta[mun] = {"erro": str(e)[:200]}
            continue
        ss = cs[cs["CD_MUN"] == mun][["CD_SETOR"]].merge(pts, on="CD_SETOR")
        sp = gpd.GeoDataFrame(ss, geometry=gpd.points_from_xy(ss["lon"], ss["lat"]), crs=4674)
        j = gpd.sjoin(sp, g, how="left", predicate="within")
        j = j[~j.index.duplicated()]
        # setor fora de todos os polígonos (borda, ilha, área rural): polígono mais próximo
        fora = j["id_unidade"].isna()
        if fora.any():
            near = gpd.sjoin_nearest(sp[fora.values].to_crs(5880), g.to_crs(5880), how="left")
            near = near[~near.index.duplicated()]
            j.loc[fora, "id_unidade"] = near["id_unidade"].values
            j.loc[fora, "nome"] = near["nome"].values
        st.append(pd.DataFrame({"CD_SETOR": j["CD_SETOR"].values, "id_unidade": j["id_unidade"].values,
                                "tipo": "bairro_prefeitura", "nome": j["nome"].values}))
        ll = loc_todos[(loc_todos["cd_mun_ibge"] == mun) & loc_todos["lat"].notna()]
        lp = gpd.GeoDataFrame(ll[["id_local"]], geometry=gpd.points_from_xy(ll["lon"], ll["lat"]), crs=4674)
        jl = gpd.sjoin_nearest(lp.to_crs(5880), g.to_crs(5880), how="left")
        jl = jl[~jl.index.duplicated()]
        lc.append(pd.DataFrame({"id_local": jl["id_local"].values, "id_unidade": jl["id_unidade"].values}))
        meta[mun] = {"arquivo": rel, "campo_nome": campo, "poligonos": len(g)}
    st = pd.concat(st) if st else pd.DataFrame(columns=["CD_SETOR", "id_unidade", "tipo", "nome"])
    resto = u1[~u1["CD_SETOR"].isin(st["CD_SETOR"])]
    return pd.concat([st, resto]), (pd.concat(lc) if lc else pd.DataFrame(columns=["id_local", "id_unidade"])), meta


# ---------------------------------------------------------------- montagem

def montar(variante):
    out = os.path.join(VAR, variante)
    os.makedirs(out, exist_ok=True)
    cs = pd.read_parquet(os.path.join(PROC, "censo_setores.parquet"))
    pts = pontos_setores()
    loc = {a: pd.read_parquet(os.path.join(PROC, f"locais_geo_{a}.parquet")) for a in (2022, 2026)}
    for a, l in loc.items():
        l["id_local"] = f"{a}-" + l["uf"] + "-" + l["cd_mun_tse"].astype(str) + "-" + l["zona"].astype(str) + "-" + l["nr_local"].astype(str)
        l["ano"] = a
    todos = pd.concat(loc.values(), ignore_index=True)

    u1 = unidade_u1(cs)
    if variante == "U1":
        st = u1
        lu = todos[["id_local", "CD_SETOR"]].merge(st[["CD_SETOR", "id_unidade"]], on="CD_SETOR", how="left")[["id_local", "id_unidade"]]
        meta_extra = {}
    elif variante == "U2":
        st, lu26 = unidade_u2(cs, pts, loc[2026])
        lu = todos[["id_local", "CD_SETOR"]].merge(st[["CD_SETOR", "id_unidade"]], on="CD_SETOR", how="left")[["id_local", "id_unidade"]]
        # locais de 2026 usam o próprio grupo (o setor onde caem pode ter outro local mais perto)
        lu = lu.set_index("id_local"); lu.update(lu26.set_index("id_local")); lu = lu.reset_index()
        st = st.merge(u1[["CD_SETOR", "nome"]], on="CD_SETOR")
        moda = st.dropna(subset=["nome"]).groupby("id_unidade")["nome"].agg(lambda s: s.value_counts().index[0])
        st["nome"] = st["id_unidade"].map(moda)  # nome do bairro IBGE mais comum na área
        meta_extra = {"alvo_eleitores": ALVO_U2}
    elif variante == "U4":
        st2, lu26 = unidade_u2(cs, pts, loc[2026])
        n1 = u1.assign(CD_MUN=u1["CD_SETOR"].str[:7].astype(int)).groupby("CD_MUN")["id_unidade"].nunique()
        unica = set(n1[n1 <= 1].index)                           # municípios que a U1 deixa inteiros
        st2 = st2.assign(CD_MUN=st2["CD_SETOR"].str[:7].astype(int))
        troca = set(st2.loc[st2["CD_MUN"].isin(unica) & st2["id_unidade"].str.startswith("A"), "CD_MUN"])
        st = pd.concat([u1[~u1["CD_SETOR"].str[:7].astype(int).isin(troca)],
                        st2[st2["CD_MUN"].isin(troca)].drop(columns="CD_MUN").assign(nome=None)])
        lu = todos[["id_local", "CD_SETOR"]].merge(st[["CD_SETOR", "id_unidade"]], on="CD_SETOR", how="left")[["id_local", "id_unidade"]]
        l26 = lu26[lu26["id_unidade"].str[1:8].astype(int).isin(troca) & lu26["id_unidade"].str.startswith("A")]
        lu = lu.set_index("id_local"); lu.update(l26.set_index("id_local")); lu = lu.reset_index()
        meta_extra = {"municipios_com_areas_de_locais": len(troca)}
    else:
        st, lu3, meta3 = unidade_u3(cs, pts, u1, todos)
        lu = todos[["id_local", "CD_SETOR"]].merge(st[["CD_SETOR", "id_unidade"]], on="CD_SETOR", how="left")[["id_local", "id_unidade"]]
        lu = lu.set_index("id_local"); lu.update(lu3.set_index("id_local")); lu = lu.reset_index()
        meta_extra = {"malhas_prefeitura": {str(k): v for k, v in meta3.items()}}

    todos = todos.merge(lu, on="id_local", how="left")
    # local sem setor mas com bairro IBGE pelo nome (U1 e U3 fora das malhas de prefeitura)
    sem = todos["id_unidade"].isna() & todos["CD_BAIRRO"].notna() & (todos["CD_BAIRRO"] != ".")
    if variante != "U2":
        todos.loc[sem, "id_unidade"] = "B" + todos.loc[sem, "CD_BAIRRO"].astype(str)
    # sem localização: unidade residual do município (ou o próprio município, se ele for unidade única)
    nun = st.assign(CD_MUN=st["CD_SETOR"].str[:7].astype(int)).groupby("CD_MUN")["id_unidade"].nunique()
    sem = todos["id_unidade"].isna()
    unica = todos.loc[sem, "cd_mun_ibge"].map(nun).fillna(1) <= 1
    todos.loc[sem, "id_unidade"] = np.where(unica, "M" + todos.loc[sem, "cd_mun_ibge"].astype(int).astype(str),
                                            "R" + todos.loc[sem, "cd_mun_ibge"].astype(int).astype(str))

    # ---- fusão de unidades pequenas (aptos 2026 < MIN_APTOS) com a vizinha mais próxima do mesmo município
    l26 = todos[todos["ano"] == 2026]
    tam = l26.groupby("id_unidade")["eleitores"].sum()
    cen = l26[l26["lat"].notna()].groupby("id_unidade").apply(
        lambda g: pd.Series({"lat": np.average(g["lat"], weights=g["eleitores"] + 1),
                             "lon": np.average(g["lon"], weights=g["eleitores"] + 1),
                             "mun": g["cd_mun_ibge"].iat[0]}), include_groups=False)
    destino = {}
    for mun, g in cen.groupby("mun"):
        g = g.assign(apt=tam.reindex(g.index).fillna(0))
        grandes = g[(g["apt"] >= MIN_APTOS) & ~g.index.str.startswith("R")]
        peq = g[(g["apt"] < MIN_APTOS) & ~g.index.str.startswith("R")]
        if len(peq) == 0 or len(grandes) == 0:
            continue
        _, j = cKDTree(xy(grandes["lat"], grandes["lon"])).query(xy(peq["lat"], peq["lon"]))
        destino.update(dict(zip(peq.index, grandes.index[j])))
    todos["id_unidade_original"] = todos["id_unidade"]
    todos["id_unidade"] = todos["id_unidade"].replace(destino)
    st["id_unidade"] = st["id_unidade"].replace(destino)
    # unidades que só têm locais de 2022 (sem eleitores em 2026) também vão para a vizinha
    so22 = set(todos.loc[todos["ano"] == 2022, "id_unidade"]) - set(todos.loc[todos["ano"] == 2026, "id_unidade"])
    if so22:
        c22 = todos[todos["id_unidade"].isin(so22) & todos["lat"].notna()].groupby("id_unidade")[["lat", "lon", "cd_mun_ibge"]].first()
        for mun, g in c22.groupby("cd_mun_ibge"):
            alvo = cen[(cen["mun"] == mun) & cen.index.isin(todos.loc[todos["ano"] == 2026, "id_unidade"]) &
                       ~cen.index.isin(destino.keys())]
            if len(alvo):
                _, j = cKDTree(xy(alvo["lat"], alvo["lon"])).query(xy(g["lat"], g["lon"]))
                todos["id_unidade"] = todos["id_unidade"].replace(dict(zip(g.index, alvo.index[j])))

    st[["CD_SETOR", "id_unidade"]].to_parquet(os.path.join(out, "setor_unidade.parquet"), index=False)
    todos[["id_local", "ano", "id_unidade", "id_unidade_original"]].to_parquet(os.path.join(out, "local_unidade.parquet"), index=False)

    # ---- tabela seção -> local -> unidade -> município -> RM -> UF
    rm = rm_por_municipio()
    secs = []
    for a in (2022, 2026):
        s = pd.read_parquet(os.path.join(PROC, f"locais_secao_{a}.parquet"), columns=["ano", "uf", "cd_mun_tse", "zona", "secao", "nr_local"])
        s["id_local"] = f"{a}-" + s["uf"] + "-" + s["cd_mun_tse"].astype(str) + "-" + s["zona"].astype(str) + "-" + s["nr_local"].astype(str)
        secs.append(s)
    secs = pd.concat(secs).merge(todos[["id_local", "id_unidade", "cd_mun_ibge", "status_geo"]], on="id_local", how="left")
    secs = secs.merge(rm, on="cd_mun_ibge", how="left")
    secs.to_parquet(os.path.join(out, "secao_unidade.parquet"), index=False)

    # ---- perfil do Censo por unidade (soma dos setores da unidade; sigilo: soma do que existe)
    perfil = cs[["CD_SETOR", "CD_MUN", "NM_MUN", "CD_UF"] + CONTAGENS].merge(st[["CD_SETOR", "id_unidade"]], on="CD_SETOR")
    agg = perfil.groupby("id_unidade").agg(cd_mun_ibge=("CD_MUN", "first"), municipio=("NM_MUN", "first"),
                                           cd_uf=("CD_UF", "first"), setores=("CD_SETOR", "size"),
                                           **{c: (c, "sum") for c in CONTAGENS})
    nomes = st.drop_duplicates("id_unidade").set_index("id_unidade")[["tipo", "nome"]]
    if variante != "U2":
        nomes = nomes.join(u1.drop_duplicates("id_unidade").set_index("id_unidade")[["tipo", "nome"]], rsuffix="_u1", how="outer")
        nomes["tipo"] = nomes["tipo"].fillna(nomes["tipo_u1"]); nomes["nome"] = nomes["nome"].fillna(nomes["nome_u1"])
        nomes = nomes[["tipo", "nome"]]
    un = l26.assign(id_unidade=todos.loc[todos["ano"] == 2026, "id_unidade"].values).groupby("id_unidade").agg(
        eleitores_2026=("eleitores", "sum"), locais_2026=("id_local", "size"), cd_mun_ibge_l=("cd_mun_ibge", "first"))
    un = un.join(agg, how="left").join(nomes, how="left")
    un["cd_mun_ibge"] = un["cd_mun_ibge"].fillna(un["cd_mun_ibge_l"]).astype(int)
    un = un.drop(columns="cd_mun_ibge_l")
    un.loc[un.index.str.startswith("R"), ["tipo", "nome"]] = ["residual", "Locais não localizados"]
    if variante == "U4":
        # área de locais: nome do bairro que o TSE mais declara entre os locais de 2026 da área
        l26n = todos[(todos["ano"] == 2026) & todos["id_unidade"].str.startswith("A", na=False)]
        top = (l26n.groupby(["id_unidade", "bairro_tse"])["eleitores"].sum().reset_index()
               .sort_values("eleitores", ascending=False).drop_duplicates("id_unidade").set_index("id_unidade")["bairro_tse"])
        area = un.index.str.startswith("A")
        un.loc[area, "tipo"] = "area_local"
        un.loc[area, "nome"] = [f"{str(top.get(i, '')).title()} e entorno" if isinstance(top.get(i), str) and top.get(i).strip()
                                else "Área de locais de votação" for i in un.index[area]]
    un["tipo"] = un["tipo"].fillna("municipio")
    un = un.reset_index().merge(rm, on="cd_mun_ibge", how="left")
    un["uf"] = un["cd_mun_ibge"].map(todos.drop_duplicates("cd_mun_ibge").set_index("cd_mun_ibge")["uf"])
    un.to_parquet(os.path.join(out, "unidades.parquet"), index=False)

    # ---- medidas da variante
    sub = ~un["tipo"].isin(["municipio", "residual"])
    e = un["eleitores_2026"]
    m = {
        "variante": variante, "unidades": int(len(un)), "unidades_abaixo_do_municipio": int(sub.sum()),
        "cobertura_pct_eleitores_abaixo_do_municipio": round(100*e[sub].sum()/e.sum(), 2),
        "eleitores_por_unidade_media": round(float(e[sub].mean()), 0), "eleitores_por_unidade_mediana": round(float(e[sub].median()), 0),
        "unidades_fundidas_por_tamanho": len(destino),
        "geocodificacao_2026_pct_eleitores": (l26.groupby("status_geo")["eleitores"].sum()/l26["eleitores"].sum()*100).round(2).to_dict(),
        "concordancia_bairro_tse_ibge_pct_locais_2026": round(100*float(l26["bairro_concorda"].mean()), 1),
        "municipios_com_unidades_abaixo": int(un.loc[sub, "cd_mun_ibge"].nunique()),
        **meta_extra,
    }
    json.dump(m, open(os.path.join(out, "medidas.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in m.items() if k != "malhas_prefeitura"}, ensure_ascii=False))
    return st


def contornos(variante, st):
    """Polígonos das unidades (dissolve dos setores; na U3, polígono da prefeitura). Em paralelo por UF."""
    out = os.path.join(VAR, variante, "unidades.gpkg")
    def uf(c):
        g = gpd.read_file(os.path.join(IBGE, "BR_setores_CD2022.gpkg"), columns=["CD_SETOR"], where=f"CD_UF = '{c}'")
        g = g.merge(st[["CD_SETOR", "id_unidade"]], on="CD_SETOR")
        d = g.dissolve("id_unidade").reset_index()[["id_unidade", "geometry"]]
        d["geometry"] = d.geometry.simplify(0.0005, preserve_topology=True)
        return d
    ufs = sorted(st["CD_SETOR"].str[:2].unique())
    d = pd.concat(Parallel(n_jobs=9)(delayed(uf)(u) for u in ufs))
    gpd.GeoDataFrame(d, crs=4674).to_file(out, driver="GPKG", layer="unidades")
    print(f"{len(d):,} contornos -> {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("variantes", nargs="*", default=["U1", "U2", "U3"])
    ap.add_argument("--sem-contornos", action="store_true")
    a = ap.parse_args()
    for v in a.variantes:
        st = montar(v)
        if not a.sem_contornos:
            contornos(v, st)
