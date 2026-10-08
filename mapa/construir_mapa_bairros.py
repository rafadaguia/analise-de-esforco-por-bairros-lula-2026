#!/usr/bin/env python3
"""Gera o mapa nacional por bairro (mapa/bairros/): tiles vetoriais PMTiles e dados das fichas.

Navegação UF -> região metropolitana -> município -> bairro, com ficha de análise em cada nível.
Compatível com o GitHub Pages: página estática + arquivos .pmtiles lidos por HTTP Range
(MapLibre GL + protocolo pmtiles). Não publica nada: só gera a pasta local.
O mapa e o embed atuais (mapa/mapa_prioridades.html, mapa/embed.html, docs/) não são alterados.

Uso: .venv-bairros/bin/python mapa/construir_mapa_bairros.py --unidade U1 --metodo MC --pesos P1
"""
import argparse, json, os, shutil, subprocess, sys, tempfile
import numpy as np
import pandas as pd
import geopandas as gpd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAR = os.path.join(RAIZ, "variantes")
OUT = os.path.join(RAIZ, "mapa", "bairros")


def limpo(o):
    """NaN não é JSON válido no navegador: vira null."""
    if isinstance(o, dict):
        return {k: limpo(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [limpo(v) for v in o]
    if isinstance(o, float) and np.isnan(o):
        return None
    return o


def r(v, k=0):
    return None if pd.isna(v) else (int(round(v)) if k == 0 else round(float(v), k))


def tiles(gdf, camada, destino, zmin, zmax, extra=()):
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, f"{camada}.geojsonseq")
        gdf.to_crs(4326).to_file(src, driver="GeoJSONSeq")
        cmd = ["tippecanoe", "-o", destino, "-l", camada, "-Z", str(zmin), "-z", str(zmax), "--force",
               "--coalesce-densest-as-needed", "--drop-densest-as-needed",
               "--simplification=4", "--detect-shared-borders", "-q", *extra, src]
        subprocess.run(cmd, check=True)
    print(f"  {camada}: {len(gdf):,} feições -> {os.path.basename(destino)} ({os.path.getsize(destino)/1e6:.1f} MB)")


UF_NOME = {11: "Rondônia", 12: "Acre", 13: "Amazonas", 14: "Roraima", 15: "Pará", 16: "Amapá", 17: "Tocantins", 21: "Maranhão",
           22: "Piauí", 23: "Ceará", 24: "Rio Grande do Norte", 25: "Paraíba", 26: "Pernambuco", 27: "Alagoas", 28: "Sergipe",
           29: "Bahia", 31: "Minas Gerais", 32: "Espírito Santo", 33: "Rio de Janeiro", 35: "São Paulo", 41: "Paraná",
           42: "Santa Catarina", 43: "Rio Grande do Sul", 50: "Mato Grosso do Sul", 51: "Mato Grosso", 52: "Goiás", 53: "Distrito Federal"}


def rotulos(gu, mun, rmg, u):
    """Pontos de rótulo (estados, RMs, municípios, bairros) com o zoom mínimo de cada um, num só PMTiles.
    k: 1 estado, 2 município, 3 área (bairro), 4 região metropolitana; r: posto de importância (eleitores)."""
    ufs = gpd.read_file(os.path.join(RAIZ, "dados", "geo", "ibge_ufs_qualidade_minima.json"))
    feats = []
    def add(geom, k, n, z, r):
        if geom is None or geom.is_empty or not isinstance(n, str) or not n.strip():
            return
        pt = geom.representative_point() if geom.geom_type != "Point" else geom
        feats.append({"type": "Feature", "tippecanoe": {"minzoom": int(z)},
                      "geometry": {"type": "Point", "coordinates": [round(pt.x, 5), round(pt.y, 5)]},
                      "properties": {"k": k, "n": n, "r": int(r)}})
    for _, x in ufs.to_crs(4326).iterrows():
        add(x.geometry, 1, UF_NOME.get(int(x["codarea"]), str(x["codarea"])), 2, 10**9)
    ap_mun = u.groupby("cd_mun_ibge")["aptos"].sum()
    nm_mun = u.groupby("cd_mun_ibge")["municipio"].first()
    for _, x in mun.to_crs(4326).iterrows():
        k_ = int(x["m"]); a_ = float(ap_mun.get(k_, 0) or 0)
        z = 5 if a_ >= 500e3 else 6 if a_ >= 150e3 else 7 if a_ >= 40e3 else 8 if a_ >= 10e3 else 9
        add(x.geometry, 2, nm_mun.get(k_), z, a_)
    for _, x in rmg.to_crs(4326).iterrows():
        add(x.geometry, 4, x["r"], 3, 0)
    ap_un = u.set_index("id_unidade")["aptos"]
    tipo = u.set_index("id_unidade")["tipo"]
    for _, x in gu.to_crs(4326).iterrows():
        if tipo.get(x["id"]) in ("municipio", "residual"):
            continue                       # área = município inteiro: o rótulo do município basta
        a_ = float(ap_un.get(x["id"], 0) or 0)
        add(x.geometry, 3, x["n"], 10 if a_ >= 5000 else 11, a_)
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "rotulos.geojsonseq")
        with open(src, "w") as f:
            for ft in feats:
                f.write(json.dumps(ft, ensure_ascii=False) + "\n")
        destino = os.path.join(OUT, "rotulos.pmtiles")
        subprocess.run(["tippecanoe", "-o", destino, "-l", "rotulos", "-Z", "2", "-z", "13", "--force", "-r1",
                        "--no-feature-limit", "--no-tile-size-limit", "-q", src], check=True)
    print(f"  rótulos: {len(feats):,} -> rotulos.pmtiles ({os.path.getsize(destino)/1e6:.1f} MB)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unidade", default="U1"); ap.add_argument("--metodo", default="MC"); ap.add_argument("--pesos", default="P2")
    a = ap.parse_args()
    pasta = os.path.join(VAR, a.unidade, a.metodo)
    os.makedirs(OUT, exist_ok=True)

    mc = pd.read_parquet(os.path.join(pasta, "unidades_mc.parquet"))
    es = pd.read_parquet(os.path.join(pasta, "esforco.parquet"))[["id_unidade", "pot_mil", "nivel_P1", "nivel_P2", "nivel_P3"]]
    u = mc.merge(es, on="id_unidade", how="left")
    mrp_arq = os.path.join(VAR, a.unidade, "mrp.parquet")
    if os.path.exists(mrp_arq):
        u = u.merge(pd.read_parquet(mrp_arq)[["id_unidade", "R3_p05", "R3_p50", "R3_p95"]], on="id_unidade", how="left")
    else:
        u["R3_p50"] = np.nan; u["R3_p05"] = np.nan; u["R3_p95"] = np.nan
    tm_arq = os.path.join(VAR, a.unidade, "temas_unidades.parquet")
    temas = pd.read_parquet(tm_arq).set_index("id_unidade") if os.path.exists(tm_arq) else None
    gr = pd.read_parquet(os.path.join(pasta, "grupos_mc.parquet"))
    meta = json.load(open(os.path.join(pasta, "mc_meta.json")))

    # ------------------------------------------------ geometria das unidades e dos municípios
    g = gpd.read_file(os.path.join(VAR, a.unidade, "unidades.gpkg"))
    g = g.merge(u, on="id_unidade", how="left")
    nivel = f"nivel_{a.pesos}"
    cs = pd.read_parquet(os.path.join(RAIZ, "dados_bairros", "proc", "censo_setores.parquet"), columns=["CD_BAIRRO", "NM_BAIRRO"])
    nb = cs[cs["CD_BAIRRO"] != "."].drop_duplicates("CD_BAIRRO").set_index("CD_BAIRRO")["NM_BAIRRO"]
    nome_ibge = g["id_unidade"].where(g["id_unidade"].str.startswith("B")).str[1:].map(nb)
    props = pd.DataFrame({
        "id": g["id_unidade"], "n": g["nome"].fillna(nome_ibge).fillna("Área sem local de votação"), "m": g["cd_mun_ibge"].astype("Int64"),
        "v": g[nivel].astype("Int64"), "v1": g["nivel_P1"].astype("Int64"), "v2": g["nivel_P2"].astype("Int64"),
        "v3": g["nivel_P3"].astype("Int64"),
    })
    gu = gpd.GeoDataFrame(props, geometry=g.geometry, crs=g.crs)
    # polígono sem eleitor (bairro sem local de votação): fica, em cinza
    gu["m"] = gu["m"].fillna(pd.to_numeric(gu["id"].str.extract(r"^[BSDMP](\d{7})")[0], errors="coerce").astype("Int64"))
    mun = gu.dropna(subset=["m"]).dissolve("m").reset_index()[["m", "geometry"]]
    mun["geometry"] = mun.geometry.simplify(0.002, preserve_topology=True)

    # nível de esforço do município e da RM: mesmos 4 componentes das áreas, pesos P2, setis
    import sys as _s; _s.path.insert(0, os.path.join(RAIZ, "bairros"))
    from b08_esforco import PESOS
    w = PESOS[a.pesos]
    def niveis_grupo(nv, chave):
        pot = gr[(gr["nivel"] == nv) & (gr["medida"] == "potencial")].set_index("grupo")
        uu = u.assign(_g=u[chave].astype(str) if chave != "cd_mun_ibge" else u[chave].astype(int).astype(str))
        ap_ = uu.groupby("_g")["aptos"].sum()
        seg = uu.groupby("_g").apply(lambda g: np.average(g["prob_mob_rende"].fillna(0), weights=g["aptos"].fillna(0) + 1), include_groups=False)
        d = pd.DataFrame({"pot": pot["mediana"], "lar": (pot["p95"] - pot["p05"]) / pot["mediana"].clip(lower=1)}).join(ap_.rename("ap")).join(seg.rename("seg")).dropna()
        idx = (w[0] * (d["pot"] / d["ap"]).rank(pct=True) + w[1] * d["seg"].rank(pct=True)
               + w[2] * (-d["lar"]).rank(pct=True) + w[3] * np.log(d["ap"]).rank(pct=True))
        d["v"] = pd.qcut(idx.rank(method="first"), 7, labels=range(1, 8)).astype(int)
        return d
    nv_mun = niveis_grupo("municipio", "cd_mun_ibge")
    nv_rm = niveis_grupo("rm", "nome_rm")
    nv_rm = nv_rm[nv_rm.index != "(fora de RM)"]
    mun["v"] = mun["m"].astype(int).astype(str).map(nv_mun["v"]).astype("Int64")
    rm_de = u.dropna(subset=["nome_rm"]).groupby("cd_mun_ibge")["nome_rm"].first()
    # contorno da RM a partir das áreas (sem simplificação prévia) e com as frestas entre municípios fechadas;
    # simplificar antes de juntar deixava riscos internos no polígono
    gr_ = gu.dropna(subset=["m"]).assign(r=lambda x: x["m"].astype(int).map(rm_de)).dropna(subset=["r"])
    rmg = gr_.dissolve("r").reset_index()[["r", "geometry"]]
    rmg["geometry"] = rmg.geometry.buffer(0.002).buffer(-0.002).simplify(0.003, preserve_topology=True)
    rmg["v"] = rmg["r"].map(nv_rm["v"]).astype("Int64")

    # zoom máximo 12: acima disso o MapLibre sobreamplia; mantém o arquivo abaixo do limite do GitHub
    tiles(gu, "unidades", os.path.join(OUT, "unidades.pmtiles"), 2, 12)
    tiles(mun, "municipios", os.path.join(OUT, "municipios.pmtiles"), 2, 10)
    tiles(rmg, "rm", os.path.join(OUT, "rm.pmtiles"), 2, 10)
    rotulos(gu, mun, rmg, u)

    # ------------------------------------------------ fichas (JSON)
    def faixa(df, med):
        l = df[df["medida"] == med]
        return {k: [r(x) for x in v] for k, v in zip(l["grupo"], l[["p05", "mediana", "p95"]].to_numpy())}
    niveis = {}
    for nv in ("uf", "rm", "municipio", "frente", "pais"):
        d = gr[gr["nivel"] == nv]
        niveis[nv] = {m: faixa(d, m) for m in ("potencial", "margem_base", "margem_dir", "mob", "terc_base", "terc_dir")}
    # contagem de unidades por nível de esforço em cada município/RM/UF (para a ficha)
    ok = u[nivel].notna()
    dist = {}
    for col, chave in (("uf", "uf"), ("nome_rm", "rm"), ("cd_mun_ibge", "municipio")):
        t = u[ok].groupby([u.loc[ok, col].astype(str), nivel]).size().unstack(fill_value=0)
        dist[chave] = {k: [int(t.loc[k].get(i, 0)) for i in range(1, 8)] for k in t.index}
    u["municipio"] = u["municipio"].fillna(u["municipio_tse"].str.title())
    mun_info = u.groupby("cd_mun_ibge").agg(nome=("municipio", "first"), uf=("uf", "first"), rm=("nome_rm", "first"),
                                            aptos=("aptos", "sum"), unidades=("id_unidade", "size")).reset_index()
    cent = mun.set_index("m").to_crs(5880).geometry.centroid.to_crs(4326)
    bbox_mun = mun.set_index("m").to_crs(4326).bounds.round(4)
    municipios = {str(int(k)): {"n": r_["nome"], "uf": r_["uf"], "rm": r_["rm"] if isinstance(r_["rm"], str) else None,
                                "ap": int(r_["aptos"]), "u": int(r_["unidades"]),
                                "v": int(nv_mun["v"].get(str(int(k)))) if str(int(k)) in nv_mun.index else None,
                                "b": bbox_mun.loc[k].tolist() if k in bbox_mun.index else None}
                  for k, r_ in mun_info.set_index("cd_mun_ibge").iterrows()}
    rms = {}
    for k, s in mun_info.dropna(subset=["rm"]).groupby("rm"):
        b = bbox_mun.loc[bbox_mun.index.intersection(s["cd_mun_ibge"])]
        rms[k] = {"uf": s["uf"].mode().iat[0], "mun": [str(int(x)) for x in s["cd_mun_ibge"]], "ap": int(s["aptos"].sum()),
                  "v": int(nv_rm["v"].get(k)) if k in nv_rm.index else None,
                  "b": [b.minx.min(), b.miny.min(), b.maxx.max(), b.maxy.max()] if len(b) else None}
    unidades = {}
    for _, x in u.iterrows():
        unidades[x["id_unidade"]] = {
            "n": x["nome"] if isinstance(x["nome"], str) else "Área sem nome", "t": x["tipo"], "m": str(int(x["cd_mun_ibge"])), "ap": r(x["aptos"]),
            "l26": r(x["lula_pct_26"], 1), "l22": r(x["lula_pct_22_2t"], 1), "d": r(x["desloc"], 1),
            "te": r(x["terreno"]), "pot": [r(x["pot_p05"]), r(x["pot_p50"]), r(x["pot_p95"])], "pm": r(x["pot_mil"], 1),
            "mob": [r(x["mob_p05"]), r(x["mob_p50"]), r(x["mob_p95"])], "pr": r(x["prob_mob_rende"], 2),
            "ei": [r(x["lula2_base_p05"], 3), r(x["lula2_base_p50"], 3), r(x["lula2_base_p95"], 3)] if "lula2_base_p50" in x else None,
            "v": [r(x["nivel_P1"]), r(x["nivel_P2"]), r(x["nivel_P3"])],
            "tm": ({k: [t for t in str(temas.at[x["id_unidade"], c]).split(";") if t and t != "nan"]
                    for k, c in (("a", "temas_aderentes_lula"), ("f", "temas_flavio_mais_fraco"),
                                 ("d", "temas_disputados"), ("e", "temas_evitar"))}
                   if temas is not None and x["id_unidade"] in temas.index else None),
        }
    import glob as _g
    inst = []
    for f in _g.glob(os.path.join(pasta, "diag_??.json")):
        dg = json.load(open(f))
        rh = dg.get("rhat_max")
        if rh is None or (isinstance(rh, float) and np.isnan(rh)) or rh > 1.05 or len(dg.get("descartadas", [])) >= 3:
            inst.append(dg["uf"])
    # citações dos planos oficiais por tema (b09/b13) e força do tema soberania por município (b14)
    cit_arq = os.path.join(VAR, a.unidade, "temas_citacoes.json")
    citacoes = json.load(open(cit_arq)) if os.path.exists(cit_arq) else {}
    sob_arq = os.path.join(RAIZ, "bairros", "insumos", "contexto", "soberania_municipios.csv")
    if os.path.exists(sob_arq):
        sob = pd.read_csv(sob_arq).set_index("cd_municipio_ibge")
        for k, v in municipios.items():
            if int(k) in sob.index:
                r_ = sob.loc[int(k)]
                v["sob"] = {"f": r_["forca_soberania"], "eua": round(float(r_["exp_eua_usd"]) / 1e6, 1),
                            "par": round(100 * float(r_["parcela_eua"]), 0), "am": bool(r_["amazonia_legal"]), "sede": bool(r_["sede_exportadora"])}
    dados = {"meta": {**meta, "unidade": a.unidade, "metodo": a.metodo, "pesos": a.pesos, "ufs_instaveis": sorted(inst)},
             "citacoes": citacoes,
             "grupos": niveis, "dist": dist, "municipios": municipios, "rms": rms}
    json.dump(limpo(dados), open(os.path.join(OUT, "dados.json"), "w"), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    # unidades em arquivos por UF (carregados sob demanda, ao entrar na UF)
    os.makedirs(os.path.join(OUT, "uf"), exist_ok=True)
    por_uf = {}
    for k, v in unidades.items():
        por_uf.setdefault(municipios[v["m"]]["uf"], {})[k] = v
    for uf, d in por_uf.items():
        json.dump(limpo(d), open(os.path.join(OUT, "uf", f"{uf}.json"), "w"), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    # contorno estadual a partir dos municípios (o arquivo de "qualidade mínima" do IBGE corta baías com retas,
    # visíveis de perto, como na Baía de Guanabara)
    ufg = mun.assign(uf=(mun["m"].astype(int) // 100000)).dissolve("uf").reset_index()[["uf", "geometry"]]
    ufg["geometry"] = ufg.geometry.buffer(0.001).buffer(-0.001).simplify(0.004, preserve_topology=True)
    ufg.to_crs(4326).to_file(os.path.join(OUT, "ufs.json"), driver="GeoJSON", COORDINATE_PRECISION=4)
    modelo = open(os.path.join(RAIZ, "mapa", "modelo_bairros.html"), encoding="utf-8").read()
    for arq, modo, tit in (("index.html", "municipio", "Esforço por Município"), ("bairros.html", "area", "Esforço por Bairro"),
                           ("rm.html", "rm", "Esforço por Região Metropolitana")):
        pag = modelo.replace('/*__MODO__*/"municipio"', f'"{modo}"').replace("/*__TITULO__*/Esforço por Município", tit)
        open(os.path.join(OUT, arq), "w", encoding="utf-8").write(pag)
    shutil.copy(os.path.join(RAIZ, "mapa", "guia_modelo.html"), os.path.join(OUT, "guia.html"))   # página "Como usar"
    print(f"  níveis: {len(nv_mun)} municípios, {len(nv_rm)} RMs | UFs instáveis: {sorted(inst)}")
    # bibliotecas e fontes locais (MapLibre, PMTiles, Archivo, Instrument Sans): nada é carregado de fora
    shutil.copytree(os.path.join(RAIZ, "mapa", "lib"), os.path.join(OUT, "lib"), dirs_exist_ok=True)
    tams = [os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(OUT) for f in fs]
    print(f"mapa -> {OUT} ({sum(tams)/1e6:.1f} MB no total; maior arquivo {max(tams)/1e6:.1f} MB)")
    assert max(tams) < 100e6, "arquivo acima de 100 MB: o GitHub recusa"


if __name__ == "__main__":
    main()
