#!/usr/bin/env python3
"""Etapa B20: públicos por estado e por município (não por bairro): tamanho de cada grupo, abstenção e como ele vota.

Grupos: gênero (mulheres, homens), idade (16-24, 25-34, 35-44, 45-59, 60+), escolaridade (até fundamental, médio,
superior) e religião (católicos, evangélicos, sem religião). Cor ou raça NÃO é usada.

Fontes (todas públicas e agregadas):
  * tamanho dos grupos de gênero, idade e escolaridade: perfil do eleitorado 2026 (TSE), por município;
  * abstenção de cada grupo: comparecimento e abstenção por perfil, 1º turno de 2022 (TSE), por município;
  * religião: Censo 2022 (IBGE, tabela 10198, pessoas de 15 anos ou mais), por município;
  * voto de cada grupo: Datafolha nacional de 1 a 3/10/2026 (BR-08039/2026), 2º turno Lula x Flávio. A diferença de cada
    grupo para o total nacional (em log-odds) é aplicada ao resultado real do 1º turno de 2026 no estado (Lula entre os
    votos de Lula e Flávio). Aproximação: supõe que o desvio de cada grupo em relação à média é parecido em todo o país.
Classificação (Lula entre os dois candidatos, estimado no estado): 58%+ "base", 42% ou menos "difícil", entre os dois
"disputa". Abstenção do grupo acima da média da cidade é marcada (público para levar às urnas, se for base).

Saídas: variantes/<U>/publicos_municipios.parquet e publicos.json (municípios e estados)
Uso: python bairros/b20_publicos.py U4
"""
import json, os, sys, tempfile, zipfile
import duckdb
import numpy as np
import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TSE = os.path.join(RAIZ, "dados_bairros", "tse")
PROC = os.path.join(RAIZ, "dados_bairros", "proc")
FUND = ("ANALFABETO", "LÊ E ESCREVE", "ENSINO FUNDAMENTAL INCOMPLETO", "ENSINO FUNDAMENTAL COMPLETO")
MEDIO = ("ENSINO MÉDIO INCOMPLETO", "ENSINO MÉDIO COMPLETO")
SUP = ("SUPERIOR INCOMPLETO", "SUPERIOR COMPLETO")
GRUPOS = [("genero", "mulheres", "Mulheres"), ("genero", "homens", "Homens"),
          ("idade", "16-24", "16 a 24 anos"), ("idade", "25-34", "25 a 34 anos"), ("idade", "35-44", "35 a 44 anos"),
          ("idade", "45-59", "45 a 59 anos"), ("idade", "60+", "60 anos ou mais"),
          ("escolaridade", "fundamental", "Até o ensino fundamental"), ("escolaridade", "medio", "Ensino médio"),
          ("escolaridade", "superior", "Ensino superior"),
          ("religiao", "catolicos", "Católicos"), ("religiao", "evangelicos", "Evangélicos"), ("religiao", "sem_religiao", "Sem religião")]
# Datafolha 1 a 3/10/2026 (BR-08039/2026): Lula e Flávio por grupo (lido de bairros/insumos/pesquisas/cruzamentos.csv)
MAPA_DF = {"mulheres": "feminino", "homens": "masculino", "16-24": "16-24", "25-34": "25-34", "35-44": "idade 35 a 44",
           "45-59": "45-59", "60+": "60+", "fundamental": "fundamental", "medio": "medio", "superior": "superior",
           "catolicos": "catolica", "evangelicos": "evangelica"}


def sql_grupos(qt, extra=""):
    f = ", ".join(f"'{x}'" for x in FUND); m = ", ".join(f"'{x}'" for x in MEDIO); s = ", ".join(f"'{x}'" for x in SUP)
    ida = "TRY_CAST(CD_FAIXA_ETARIA AS INTEGER)"
    return f"""
      SUM(CASE WHEN TRIM(DS_GENERO)='FEMININO' THEN {qt} ELSE 0 END) AS mulheres,
      SUM(CASE WHEN TRIM(DS_GENERO)='MASCULINO' THEN {qt} ELSE 0 END) AS homens,
      SUM(CASE WHEN {ida} < 2500 THEN {qt} ELSE 0 END) AS "16-24",
      SUM(CASE WHEN {ida} BETWEEN 2500 AND 3499 THEN {qt} ELSE 0 END) AS "25-34",
      SUM(CASE WHEN {ida} BETWEEN 3500 AND 4499 THEN {qt} ELSE 0 END) AS "35-44",
      SUM(CASE WHEN {ida} BETWEEN 4500 AND 5999 THEN {qt} ELSE 0 END) AS "45-59",
      SUM(CASE WHEN {ida} >= 6000 THEN {qt} ELSE 0 END) AS "60+",
      SUM(CASE WHEN TRIM(DS_GRAU_ESCOLARIDADE) IN ({f}) THEN {qt} ELSE 0 END) AS fundamental,
      SUM(CASE WHEN TRIM(DS_GRAU_ESCOLARIDADE) IN ({m}) THEN {qt} ELSE 0 END) AS medio,
      SUM(CASE WHEN TRIM(DS_GRAU_ESCOLARIDADE) IN ({s}) THEN {qt} ELSE 0 END) AS superior,
      SUM({qt}) AS total {extra}"""


def ler_zip(zipnome, consulta):
    """Roda a consulta em cada CSV do zip (um por UF), descompactando um de cada vez."""
    z = zipfile.ZipFile(os.path.join(TSE, zipnome))
    partes = []
    for nome in [n for n in z.namelist() if n.endswith(".csv") and "BRASIL" not in n.upper()]:
        with tempfile.TemporaryDirectory(dir=TSE) as tmp:
            z.extract(nome, tmp)
            csv = os.path.join(tmp, nome)
            partes.append(duckdb.sql(consulta.format(csv=csv)).df())
    return pd.concat(partes)


def main():
    uni = sys.argv[1] if len(sys.argv) > 1 else "U4"
    pasta = os.path.join(RAIZ, "variantes", uni)
    # código do município do TSE -> IBGE
    m = pd.concat([pd.read_parquet(os.path.join(pasta, f), columns=["cd_mun_tse", "cd_mun_ibge"])
                   for f in ("secao_unidade.parquet", "secao_unidade_hist.parquet")]).dropna().drop_duplicates("cd_mun_tse")
    m["cd_mun_tse"] = m["cd_mun_tse"].astype(int); m["cd_mun_ibge"] = m["cd_mun_ibge"].astype(int).astype(str)
    ler = "FROM read_csv('{csv}', delim=';', header=true, encoding='latin-1', all_varchar=true, quote='\"')"
    # 1) tamanho dos grupos no eleitorado de 2026
    q = f"SELECT CAST(CD_MUNICIPIO AS INTEGER) AS cd_mun_tse, {sql_grupos('CAST(QT_ELEITORES AS BIGINT)')} {ler} GROUP BY 1"
    el = ler_zip("perfil_eleitorado_2026.zip", q).groupby("cd_mun_tse").sum().reset_index().merge(m, on="cd_mun_tse")
    print(f"perfil 2026: {len(el):,} municípios, {el['total'].sum():,.0f} eleitores")
    # 2) abstenção por grupo, 1º turno de 2022
    qa = f"""SELECT CAST(CD_MUNICIPIO AS INTEGER) AS cd_mun_tse, {sql_grupos('CAST(QT_APTOS AS BIGINT)')} {ler}
             WHERE NR_TURNO = '1' GROUP BY 1"""
    qb = f"""SELECT CAST(CD_MUNICIPIO AS INTEGER) AS cd_mun_tse, {sql_grupos('CAST(QT_ABSTENCAO AS BIGINT)')} {ler}
             WHERE NR_TURNO = '1' GROUP BY 1"""
    ap = ler_zip("perfil_comparecimento_abstencao_2022.zip", qa).groupby("cd_mun_tse").sum()
    ab = ler_zip("perfil_comparecimento_abstencao_2022.zip", qb).groupby("cd_mun_tse").sum()
    taxa = (ab / ap.replace(0, np.nan) * 100).add_prefix("abst_").reset_index().merge(m, on="cd_mun_tse")
    print(f"abstenção 2022: {len(taxa):,} municípios | média {100 * ab['total'].sum() / ap['total'].sum():.1f}%")
    # 3) religião (Censo 2022, 15 anos ou mais)
    rel = pd.read_parquet(os.path.join(PROC, "religiao_municipios.parquet"))
    rel = pd.DataFrame({"cd_mun_ibge": rel.index.astype(str), "catolicos": rel["Católica Apostólica Romana"].values,
                        "evangelicos": rel["Evangélicas"].values, "sem_religiao": rel["Sem religião"].values,
                        "pop15_censo": rel["Total"].values})
    # 4) voto por grupo: Datafolha nacional, recentrado no 1º turno real de cada estado
    c = pd.read_csv(os.path.join(RAIZ, "bairros", "insumos", "pesquisas", "cruzamentos.csv"))
    dfo = c[(c["instituto"] == "Datafolha") & (c["registro_tse"] == "BR-08039/2026") & (c["ok"] == True)].drop_duplicates("categoria_padrao").set_index("categoria_padrao")
    lg = lambda p: np.log(p / (1 - p))
    p_tot = dfo.loc["total", "pct_lula"] / (dfo.loc["total", "pct_lula"] + dfo.loc["total", "pct_flavio"])
    desvio = {g: lg(dfo.loc[k, "pct_lula"] / (dfo.loc[k, "pct_lula"] + dfo.loc[k, "pct_flavio"])) - lg(p_tot) for g, k in MAPA_DF.items()}
    s26 = duckdb.sql(f"SELECT uf, SUM(lula) l, SUM(adversario) f FROM '{os.path.join(PROC, 'secoes_2026.parquet')}' WHERE turno = 1 GROUP BY uf").df()
    p_uf = dict(zip(s26["uf"], s26["l"] / (s26["l"] + s26["f"])))
    voto = {uf: {g: float(1 / (1 + np.exp(-(lg(p) + d)))) for g, d in desvio.items()} for uf, p in p_uf.items()}
    # junta por município
    un = pd.read_parquet(os.path.join(pasta, "unidades.parquet"), columns=["cd_mun_ibge", "uf"]).dropna().drop_duplicates("cd_mun_ibge")
    un["cd_mun_ibge"] = un["cd_mun_ibge"].astype(int).astype(str)
    t = un.merge(el.drop(columns="cd_mun_tse"), on="cd_mun_ibge", how="left").merge(taxa.drop(columns="cd_mun_tse"), on="cd_mun_ibge", how="left") \
          .merge(rel, on="cd_mun_ibge", how="left")
    t.to_parquet(os.path.join(pasta, "publicos_municipios.parquet"), index=False)

    def bloco(r, uf, abst_media):
        out = []
        for tipo, g, rot in GRUPOS:
            if tipo == "religiao":
                base = r.get("pop15_censo")
                pct = 100 * r.get(g) / base if base and not pd.isna(r.get(g)) else None
                n = None
            else:
                n = r.get(g); pct = 100 * n / r["total"] if r.get("total") else None
            pl = voto.get(uf, {}).get(g)
            ab = r.get(f"abst_{g}") if tipo != "religiao" else None
            cls = None if pl is None else ("base" if pl >= 0.58 else "difícil" if pl <= 0.42 else "disputa")
            out.append({"grupo": rot, "tipo": tipo, "pct": None if pct is None or pd.isna(pct) else round(float(pct), 1),
                        "eleitores": None if n is None or pd.isna(n) else int(n),
                        "abstencao_2022": None if ab is None or pd.isna(ab) else round(float(ab), 1),
                        "abstencao_acima": bool(ab is not None and not pd.isna(ab) and abst_media and ab > abst_media + 2),
                        "lula_no_estado": None if pl is None else round(100 * pl, 0), "classe": cls})
        return out

    res = {"meta": {"fontes": "TSE (perfil do eleitorado 2026; comparecimento e abstenção por perfil, 1º turno de 2022), "
                              "IBGE (Censo 2022, religião, 15 anos ou mais), Datafolha BR-08039/2026 (1 a 3/10/2026) recentrado "
                              "no 1º turno de 2026 de cada estado",
                    "regra": "base: Lula com 58% ou mais entre os dois no estado; difícil: 42% ou menos; disputa: entre os dois"},
           "estados": {}, "municipios": {}}
    for _, r in t.iterrows():
        res["municipios"][r["cd_mun_ibge"]] = bloco(r, r["uf"], r.get("abst_total"))
    soma = t.groupby("uf")[[g for _, g, _ in GRUPOS] + ["total", "pop15_censo"]].sum()
    ab_uf = ap.join(m.set_index("cd_mun_tse"), how="inner").merge(un, on="cd_mun_ibge").groupby("uf").sum(numeric_only=True)
    ab_uf2 = ab.join(m.set_index("cd_mun_tse"), how="inner").merge(un, on="cd_mun_ibge").groupby("uf").sum(numeric_only=True)
    tx_uf = (ab_uf2 / ab_uf * 100).add_prefix("abst_")
    for uf, r in soma.join(tx_uf).iterrows():
        res["estados"][uf] = bloco(r.to_dict(), uf, r.get("abst_total"))
    json.dump(res, open(os.path.join(pasta, "publicos.json"), "w"), ensure_ascii=False)
    print(f"públicos: {len(res['municipios']):,} municípios e {len(res['estados'])} estados -> {pasta}/publicos.json")


if __name__ == "__main__":
    main()
