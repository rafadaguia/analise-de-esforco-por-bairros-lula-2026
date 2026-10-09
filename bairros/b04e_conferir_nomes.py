#!/usr/bin/env python3
"""Etapa B4e: confere e corrige os nomes das áreas formadas por locais de votação (nomes vindos do TSE e do OpenStreetMap).

Verificações (as áreas com bairro oficial do IBGE já trazem o nome do Censo e não são alteradas):
  1. grafia: acentos restaurados palavra a palavra com um dicionário montado de todos os nomes do IBGE (bairros,
     distritos, municípios) e do OpenStreetMap (só quando a forma acentuada é a única usada para aquela palavra);
     abreviações expandidas (Jd -> Jardim, Vl -> Vila, Pq -> Parque, Cj/Conj -> Conjunto, Res -> Residencial,
     Lot -> Loteamento, Sta -> Santa, Sto -> Santo, N. Sra./Nsa -> Nossa Senhora); maiúsculas corrigidas.
  2. lugar: se o nome existe como bairro do IBGE ou lugar do OpenStreetMap no mesmo município, ele precisa estar dentro
     da área ou a até 1,5 km dela. Se estiver longe, o nome é trocado pelo lugar que fica dentro da área (bairro do IBGE
     com mais moradores ou lugar do OpenStreetMap); sem alternativa, fica marcado.
  3. repetidos: "X (2)" vira "X - Y", com Y um lugar (IBGE ou OSM) dentro da área que não seja X; sem alternativa, fica.

Saídas:
  variantes/<U>/nomes_conferencia.csv   uma linha por área conferida: nome antigo, nome novo, motivo, distância
  variantes/<U>/unidades.parquet        nomes corrigidos (com --aplicar; cópia do original em unidades_nomes_antes.parquet)

Uso: python bairros/b04e_conferir_nomes.py U4 [--aplicar]
"""
import argparse, json, os, re, shutil, unicodedata
from collections import Counter, defaultdict
import numpy as np
import pandas as pd
import geopandas as gpd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(RAIZ, "dados_bairros", "proc")
VAR = os.path.join(RAIZ, "variantes")
IBGE = os.path.join(RAIZ, "dados_bairros", "ibge")
OSM = os.path.join(RAIZ, "dados_bairros", "osm", "bairros_osm_br.json")
LIMITE_M = 1500        # acima disso o nome é marcado
TROCA_M = 3000         # acima disso o nome é trocado pelo lugar que fica dentro da área (entre 1,5 e 3 km só marca)
ROMANOS = re.compile(r"^(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|XIII|XIV|XV|XX)$")
ABREV = [(r"\bJd\.?(?=\s)", "Jardim"), (r"\bJrd\.?(?=\s)", "Jardim"), (r"\bVl\.?(?=\s)", "Vila"), (r"\bPq\.?(?=\s)", "Parque"),
         (r"\bPrq\.?(?=\s)", "Parque"), (r"\bConj\.?(?=\s)", "Conjunto"), (r"\bCj\.?(?=\s)", "Conjunto"),
         (r"\bRes\.?(?=\s)", "Residencial"), (r"\bResid\.?(?=\s)", "Residencial"), (r"\bLot\.?(?=\s)", "Loteamento"),
         (r"\bSta\.?(?=\s)", "Santa"), (r"\bSto\.?(?=\s)", "Santo"), (r"\bN\.?\s?Sra\.?(?=\s)", "Nossa Senhora"),
         (r"\bNsa\.?(?=\s)", "Nossa Senhora"), (r"\bNs\.?(?=\s)", "Nossa Senhora"), (r"\bSr\.?(?=\s)", "Senhor"),
         (r"\bDr\.?(?=\s)", "Doutor"), (r"\bPres\.?(?=\s)", "Presidente"), (r"\bGov\.?(?=\s)", "Governador"),
         (r"\bCel\.?(?=\s)", "Coronel"), (r"\bProf\.?(?=\s)", "Professor"), (r"\bAv\.?(?=\s)", "Avenida")]
PARTICULAS = {"de", "da", "do", "dos", "das", "e", "di", "du", "em", "na", "no", "nas", "nos"}
SUFIXOS = (" e entorno", " e arredores")


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s).lower()) if c.isalnum() or c == " ").strip()


def chave(s):
    return re.sub(r"\s+", "", sem_acento(s))


def base(nome):
    n = re.sub(r"\s\(\d+\)$", "", nome)
    for s in SUFIXOS:
        if n.endswith(s):
            return n[: -len(s)], s
    return n, ""


def dicionario(nomes):
    """palavra sem acento -> forma acentuada, só quando ela é a forma usada em 95%+ das ocorrências com acento possível."""
    cont = defaultdict(Counter)
    for n in nomes:
        for p in re.findall(r"[A-Za-zÀ-ÿ]+", str(n)):
            if len(p) >= 3:
                cont[sem_acento(p)][p[0].upper() + p[1:].lower()] += 1
    d = {}
    for k, c in cont.items():
        forma, n = c.most_common(1)[0]
        if sem_acento(forma) != forma.lower() and n / sum(c.values()) >= 0.95 and sum(c.values()) >= 3:
            d[k] = forma
    return d


def limpo(nome):
    """remove caracteres invisíveis (hífen suave, espaço sem largura) e espaços repetidos."""
    n = re.sub(r"[\u00ad\u200b\u200c\u200d\ufeff]", "", str(nome))
    return " ".join(n.split())


def grafia(nome, dic):
    n = limpo(nome)
    if n.isupper() or n.islower():
        n = n.title()
    # palavras inteiras em maiúsculas no meio do nome ("Águas CLARAS"), exceto números romanos e siglas curtas
    n = " ".join(p.title() if p.isupper() and len(p) >= 4 and not ROMANOS.match(p) else p for p in n.split(" "))
    for a, b in ABREV:
        n = re.sub(a, b, n + " ", flags=re.I).strip()
    pal = []
    for i, p in enumerate(n.split(" ")):
        k = sem_acento(p)
        if i and k in PARTICULAS:
            pal.append(k)
        elif p.isalpha() and sem_acento(p) == p.lower() and k in dic:
            pal.append(dic[k])
        else:
            pal.append(p)
    return " ".join(pal)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("unidade", default="U4", nargs="?"); ap.add_argument("--aplicar", action="store_true")
    a = ap.parse_args()
    pasta = os.path.join(VAR, a.unidade)
    un = pd.read_parquet(os.path.join(pasta, "unidades.parquet"))
    geo = gpd.read_file(os.path.join(pasta, "unidades.gpkg"), columns=["id_unidade"]).to_crs(5880)
    # lugares de referência: bairros do IBGE (polígonos) e lugares do OpenStreetMap (pontos), por município
    bai = gpd.read_file(os.path.join(IBGE, "BR_bairros_CD2022.gpkg"), columns=["CD_MUN", "NM_BAIRRO"]).to_crs(5880)
    bai["CD_MUN"] = bai["CD_MUN"].astype(int)
    el = json.load(open(OSM))["elements"]
    o = []
    for e in el:
        t = e.get("tags", {})
        lat, lon = (e.get("lat"), e.get("lon")) if e["type"] == "node" else (e.get("center", {}).get("lat"), e.get("center", {}).get("lon"))
        if "name" in t and lat is not None:
            o.append({"nome": t["name"], "lat": lat, "lon": lon})
    osm = gpd.GeoDataFrame(pd.DataFrame(o), geometry=gpd.points_from_xy([x["lon"] for x in o], [x["lat"] for x in o]), crs=4326).to_crs(5880)
    mun_geo = geo.merge(un[["id_unidade", "cd_mun_ibge"]], on="id_unidade")
    osm = gpd.sjoin(osm, mun_geo[["cd_mun_ibge", "geometry"]], how="inner", predicate="within").drop(columns="index_right")
    distritos = pd.read_parquet(os.path.join(PROC, "censo_setores.parquet"), columns=["NM_DIST", "NM_SUBDIST", "NM_MUN"])
    dic = dicionario(list(bai["NM_BAIRRO"]) + list(osm["nome"]) + list(distritos["NM_DIST"].dropna().unique())
                     + list(distritos["NM_SUBDIST"].dropna().unique()) + list(distritos["NM_MUN"].dropna().unique()))
    ref = pd.concat([bai.rename(columns={"NM_BAIRRO": "nome", "CD_MUN": "cd_mun_ibge"})[["cd_mun_ibge", "nome", "geometry"]].assign(fonte="IBGE"),
                     osm[["cd_mun_ibge", "nome", "geometry"]].assign(fonte="OSM")], ignore_index=True)
    ref["nome"] = ref["nome"].map(limpo).str.replace(r"\s*\([^)]*\)\s*$", "", regex=True)   # "Coqueiro (Ananindeua)" -> "Coqueiro"
    ref["k"] = ref["nome"].map(chave)
    ref_por_mun = {m: g for m, g in ref.groupby("cd_mun_ibge")}
    geo_i = geo.set_index("id_unidade")["geometry"]

    # distrito do IBGE dominante (população) de cada área, para os "Centro" que são centro de distrito
    su = pd.read_parquet(os.path.join(pasta, "setor_unidade.parquet")).drop_duplicates("CD_SETOR")
    cs = pd.read_parquet(os.path.join(PROC, "censo_setores.parquet"), columns=["CD_SETOR", "NM_DIST", "pop"])
    sd = su.merge(cs, on="CD_SETOR").dropna(subset=["NM_DIST"])
    dist_area = sd.groupby(["id_unidade", "NM_DIST"])["pop"].sum().reset_index().sort_values("pop", ascending=False) \
        .drop_duplicates("id_unidade").set_index("id_unidade")["NM_DIST"].to_dict()
    # caracteres invisíveis em qualquer nome (inclusive do IBGE)
    sujos = un["nome"].fillna("").map(limpo) != un["nome"].fillna("")
    alvo = un[un["nome_fonte"].isin(["tse", "osm"])].copy()
    linhas = []
    novos = {}
    for _, r in alvo.iterrows():
        uid, nome, m = r["id_unidade"], r["nome"], int(r["cd_mun_ibge"])
        b, suf = base(nome)
        motivo, dist = [], np.nan
        nb = grafia(b, dic)
        if nb != b:
            motivo.append("grafia")
        g = ref_por_mun.get(m)
        area = geo_i.get(uid)
        dentro = None
        if g is not None and area is not None:
            mesmos = g[g["k"] == chave(nb)]
            if len(mesmos):
                dist = float(mesmos.distance(area).min())
            # lugares que de fato ficam dentro da área (bairro do IBGE com maior interseção; senão OSM)
            cand = g[g.intersects(area)]
            if len(cand):
                cand = cand.assign(nome=cand["nome"].str.replace(r"\s*\((?:[^)]*)\)\s*$", "", regex=True))   # "Coqueiro (Ananindeua)"
                cb = cand[cand["fonte"] == "IBGE"]
                if len(cb):
                    cb = cb.assign(ar=cb.intersection(area).area).sort_values("ar", ascending=False)
                    dentro = cb.iloc[0]["nome"]
                else:
                    dentro = cand.iloc[0]["nome"]
            if not np.isnan(dist) and dist > TROCA_M and dentro and chave(dentro) != chave(nb):
                motivo.append(f"lugar fora da área ({dist / 1000:.1f} km); trocado pelo lugar dentro dela")
                nb = grafia(dentro, dic)
            elif not np.isnan(dist) and dist > TROCA_M and chave(nb) == "centro" and r["id_unidade"] in dist_area \
                    and chave(dist_area[r["id_unidade"]]) != chave(r["municipio"]):
                motivo.append(f"'Centro' fora do centro da cidade ({dist / 1000:.1f} km); é o centro de um distrito")
                nb = f"Centro do distrito de {grafia(dist_area[r['id_unidade']], dic)}"
            elif not np.isnan(dist) and dist > LIMITE_M:
                motivo.append(f"lugar a {dist / 1000:.1f} km da área; nome mantido, conferir")
        novo = nb + suf
        novos[uid] = (novo, dentro)
        if motivo:
            linhas.append({"id_unidade": uid, "uf": r["uf"], "municipio": r["municipio"], "nome_antigo": nome, "nome_novo": novo,
                           "motivo": "; ".join(motivo), "distancia_m": None if np.isnan(dist) else round(dist)})
    # repetidos no mesmo município: segundo lugar da própria área em vez de "(2)"
    un2 = un.copy()
    for idx in un.index[sujos]:
        un2.at[idx, "nome"] = limpo(un.at[idx, "nome"])
        linhas.append({"id_unidade": un.at[idx, "id_unidade"], "uf": un.at[idx, "uf"], "municipio": un.at[idx, "municipio"],
                       "nome_antigo": un.at[idx, "nome"], "nome_novo": un2.at[idx, "nome"], "motivo": "caractere invisível", "distancia_m": None})
    for uid, (nv, _) in novos.items():
        un2.loc[un2["id_unidade"] == uid, "nome"] = nv
    un2["nome"] = un2["nome"].str.replace(r"\s\(\d+\)$", "", regex=True)
    dup = un2.duplicated(["cd_mun_ibge", "nome"], keep=False)
    for (m, n), g in un2[dup].groupby(["cd_mun_ibge", "nome"]):
        usados = {chave(base(n)[0])}
        for k, idx in enumerate(g.sort_values("eleitores_2026", ascending=False).index):
            if k == 0:
                continue
            uid = un2.at[idx, "id_unidade"]
            area, gm = geo_i.get(uid), ref_por_mun.get(int(m))
            alt = None
            if area is not None and gm is not None:
                cand = gm[gm.intersects(area) & ~gm["k"].isin(usados)]
                if len(cand):
                    alt = grafia(cand.iloc[0]["nome"], dic)
                    usados.add(chave(alt))
            novo = f"{base(n)[0]} - {alt}{base(n)[1]}" if alt else f"{n} ({k + 1})"
            antigo = un.at[idx, "nome"]
            un2.at[idx, "nome"] = novo
            if novo != antigo:
                linhas.append({"id_unidade": uid, "uf": un2.at[idx, "uf"], "municipio": un2.at[idx, "municipio"], "nome_antigo": antigo,
                               "nome_novo": novo, "motivo": "repetido no município: " + ("segundo lugar da área" if alt else "mantido o número"),
                               "distancia_m": None})
    rel = pd.DataFrame(linhas).drop_duplicates("id_unidade", keep="last")
    rel = rel.merge(un2[["id_unidade", "nome"]].rename(columns={"nome": "nome_final"}), on="id_unidade")
    rel.to_csv(os.path.join(pasta, "nomes_conferencia.csv"), index=False)
    print(f"áreas conferidas (nomes do TSE e do OSM): {len(alvo):,} | alteradas: {(rel['nome_antigo'] != rel['nome_final']).sum():,}")
    print(rel["motivo"].str.replace(r"\(\d+[.,]\d km\)", "(x km)", regex=True).value_counts().to_string())
    if a.aplicar:
        shutil.copy(os.path.join(pasta, "unidades.parquet"), os.path.join(pasta, "unidades_nomes_antes.parquet"))
        tmp = os.path.join(pasta, "unidades.parquet.tmp")
        un2.to_parquet(tmp, index=False)
        os.replace(tmp, os.path.join(pasta, "unidades.parquet"))
        print("aplicado em", os.path.join(pasta, "unidades.parquet"))


if __name__ == "__main__":
    main()
