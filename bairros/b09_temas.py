#!/usr/bin/env python3
"""Etapa B9 (versão 2, 08/10): temas por área, como HIPÓTESE DE COMUNICAÇÃO derivada de dados agregados.

Nada aqui descreve pessoas nem prevê reação a mensagens. Regra explícita e auditável, com fontes:

  escore(tema, área) = importância do tema        pesquisas publicadas (Quaest; piso 0,05 sem número publicado)
                     × relevância para a área     perfil do Censo (renda, idade, alfabetização, zona rural), infraestrutura
                                                  (esgoto, favela), emprego formal e Bolsa Família (município), exposição
                                                  ao tarifaço dos EUA (soberania; b14)
                     × (1 + vantagem no papel)    força das propostas nos planos OFICIAIS (b13): compromissos concretos
                                                  + 2 × metas numéricas, Lula contra Flávio
                     × (1 + 0,25 se o público-alvo das propostas de Lula no tema casa com um sinal forte da área)

  aderentes a Lula   os 3 maiores escores entre temas com proposta de Lula e vantagem > −0,2
  Flávio mais fraco  temas que o plano oficial de Flávio não menciona, ou em que a força dele é menos de 1/3 da de Lula
  disputados         temas muito citados nas pesquisas em que Flávio tem força igual ou maior no plano (vantagem ≤ 0,2)
  a evitar           costumes/religião e STF/reeleição (polarizam, pouco citados como problema)

Proteções: nenhum gatilho usa cor ou raça, gênero, religião ou orientação sexual da área (os públicos "mulheres" e
"população negra" das propostas são registrados, mas não casam com nenhum sinal). Cada tema traz a citação literal
do plano, com página (b13).

Entradas: unidades, setor_unidade, infra_areas (b04d), soberania_municipios (b14), propostas_por_tema (b13), matriz e
importância dos temas, CAGED e Bolsa Família.
Saídas: variantes/<U>/temas_unidades.parquet e temas_citacoes.json
"""
import argparse, json, os
import numpy as np
import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAR = os.path.join(RAIZ, "variantes")
INS = os.path.join(RAIZ, "bairros", "insumos")
PROC = os.path.join(RAIZ, "dados_bairros", "proc")

EVITAR = ["costumes_religiao", "instituicoes_stf_reeleicao"]
BASE_EXTRA = {"saneamento": 0.05, "periferias_favelas": 0.05, "agricultura_familiar": 0.05,
              # soberania: mesma base dos temas sem número de "principal problema"; quem decide ONDE ele entra é a
              # exposição local ao tarifaço e a Amazônia Legal (b14). Com 0,08 ele aparecia em metade do país (08/10)
              "soberania_nacional": 0.05}
# sinal da área -> temas que ele torna mais relevantes
GATILHOS = {
    "renda_baixa": ["custo_de_vida_inflacao_alimentos", "programas_sociais", "renda_salario_minimo", "moradia_mcmv", "endividamento_apostas"],
    "renda_media": ["impostos_isencao_ir", "endividamento_apostas"],
    "jovens": ["educacao", "emprego", "jornada_6x1"],
    "idosos": ["saude_sus", "previdencia"],
    "baixa_alfabetizacao": ["educacao", "programas_sociais"],
    "emprego_fraco": ["emprego", "jornada_6x1"],
    "bolsa_familia": ["programas_sociais"],
    "sem_esgoto": ["saneamento", "saude_sus"],
    "favela": ["periferias_favelas", "moradia_mcmv", "seguranca_publica", "saneamento"],
    "rural": ["agricultura_familiar", "agronegocio_meio_ambiente"],
    "soberania": ["soberania_nacional", "emprego"],
}
# público das propostas -> sinal da área que ele atinge
PUBLICO_SINAL = {"jovens": "jovens", "estudantes": "jovens", "idosos_aposentados": "idosos", "baixa_renda": "renda_baixa",
                 "classe_media": "renda_media", "periferia_urbana": "favela", "rural_agricultores": "rural",
                 "trabalhadores_formais": "emprego_fraco", "criancas_familias": "renda_baixa"}


def importancia():
    i = pd.read_csv(os.path.join(INS, "temas", "importancia_temas.csv"))
    i = i[(i["recorte"] == "total") & i["instituto"].str.startswith("Quaest")]
    mapa = {"violencia/seguranca": "seguranca_publica", "economia": "custo_de_vida_inflacao_alimentos", "corrupcao": "corrupcao",
            "saude": "saude_sus", "educacao": "educacao", "desemprego": "emprego", "emprego": "emprego",
            "fome/pobreza": "programas_sociais", "questoes_sociais": "programas_sociais", "inflacao": "custo_de_vida_inflacao_alimentos",
            "custo de vida": "custo_de_vida_inflacao_alimentos"}
    i["tema_m"] = i["tema"].str.lower().map(lambda t: next((v for k, v in mapa.items() if k in t), None))
    return (i.dropna(subset=["tema_m"]).groupby("tema_m")["pct"].mean() / 100).to_dict()


def sinais(variante, un):
    """Sinais de cada área como posto percentual (0-1) em relação a todas as áreas."""
    p = pd.DataFrame(index=un.index)
    renda = un["renda_resp_soma"] / un["resp_com_renda"]
    p["renda_baixa"] = (-renda).rank(pct=True)
    p["renda_media"] = 1 - (renda.rank(pct=True) - 0.55).abs() * 2
    p["jovens"] = ((un["m_15_19"] + un["f_15_19"] + un["m_20_24"] + un["f_20_24"]) / un["pop_15m"]).rank(pct=True)
    p["idosos"] = ((un["m_60_69"] + un["f_60_69"] + un["m_70m"] + un["f_70m"]) / un["pop_15m"]).rank(pct=True)
    p["baixa_alfabetizacao"] = (-(un["alfabetizados_15m"] / un["pop_15m"])).rank(pct=True)
    cg = pd.read_csv(os.path.join(INS, "contexto", "caged.csv"))
    cg = cg[cg["periodo"].str.startswith("12m")].set_index("cd_municipio_ibge")["variacao_relativa_pct"]
    p["emprego_fraco"] = (-un["cd_mun_ibge"].map(cg)).rank(pct=True)
    bf = pd.read_csv(os.path.join(INS, "contexto", "bolsa_familia.csv")).set_index("cd_municipio_ibge")
    dom_mun = un.groupby("cd_mun_ibge")["domicilios"].sum()
    p["bolsa_familia"] = un["cd_mun_ibge"].map((bf["pbf_familias_beneficiarias"] / dom_mun.reindex(bf.index)).clip(0, 1.5)).rank(pct=True)
    inf = pd.read_parquet(os.path.join(VAR, variante, "infra_areas.parquet")).set_index("id_unidade")
    p["sem_esgoto"] = un["id_unidade"].map(inf["pct_sem_esgoto_adequado"]).rank(pct=True)
    fav = un["id_unidade"].map(inf["pct_pop_favela"]).fillna(0)
    p["favela"] = np.where(fav > 0, 0.5 + 0.5 * fav.rank(pct=True), 0.2)       # áreas sem favela: sinal baixo, não zero
    su = pd.read_parquet(os.path.join(VAR, variante, "setor_unidade.parquet")).drop_duplicates("CD_SETOR")
    cs = pd.read_parquet(os.path.join(PROC, "censo_setores.parquet"), columns=["CD_SETOR", "SITUACAO", "pop"])
    x = su.merge(cs, on="CD_SETOR")
    rur = x[x["SITUACAO"] == "Rural"].groupby("id_unidade")["pop"].sum() / x.groupby("id_unidade")["pop"].sum()
    p["rural"] = un["id_unidade"].map(rur).fillna(0).rank(pct=True)
    sob = pd.read_csv(os.path.join(INS, "contexto", "soberania_municipios.csv")).set_index("cd_municipio_ibge")["forca_soberania"]
    p["soberania"] = un["cd_mun_ibge"].map(sob).map({"alta": 1.0, "média": 0.65, "baixa": 0.3}).fillna(0.3)
    p = p.fillna(0.5)
    # medidas brutas para os "portões" dos temas territoriais (não são postos)
    p.attrs["bruto"] = pd.DataFrame({"rural": un["id_unidade"].map(rur).fillna(0).to_numpy(),
                                     "favela": fav.to_numpy(),
                                     "sem_esgoto": un["id_unidade"].map(inf["pct_sem_esgoto_adequado"]).fillna(0).to_numpy(),
                                     "soberania": un["cd_mun_ibge"].map(sob).fillna("baixa").to_numpy()}, index=un.index)
    return p


def forca_planos():
    t = pd.read_csv(os.path.join(INS, "temas", "propostas_por_tema.csv"))
    f = t.pivot_table(index="tema", columns="candidato", values="forca", fill_value=0)
    for c in ("lula", "flavio"):
        if c not in f:
            f[c] = 0
    f["vantagem"] = (f["lula"] - f["flavio"]) / (f["lula"] + f["flavio"] + 1)
    pub = t[t["candidato"] == "lula"].set_index("tema")["publicos_principais"].fillna("").str.split(";")
    cit = {}
    for _, r in t.iterrows():
        cit.setdefault(r["tema"], {})[r["candidato"]] = {"p": int(r["citacao_pagina"]), "t": str(r["citacao"]), "n": int(r["compromissos"]), "m": int(r["metas"])}
    return f, pub, cit


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--unidade", default="U4")
    a = ap.parse_args()
    un = pd.read_parquet(os.path.join(VAR, a.unidade, "unidades.parquet")).reset_index(drop=True)
    mtz = pd.read_csv(os.path.join(INS, "temas", "matriz_temas.csv"))
    fpl = mtz[(mtz["candidato"].str.contains("Fl")) & (mtz["fonte_tipo"] == "plano_governo")]
    omisso = set(fpl.loc[fpl["posicao_resumo"].str.contains(r"n[aã]o (menciona|cita)", case=False, regex=True), "tema"])
    forca, pub, cit = forca_planos()
    imp = importancia()
    temas = sorted(set(forca.index) | set(mtz["tema"]))
    base = pd.Series({t: imp.get(t, BASE_EXTRA.get(t, 0.05)) for t in temas})
    fl = forca["lula"].reindex(temas).fillna(0); ff = forca["flavio"].reindex(temas).fillna(0)
    vant = forca["vantagem"].reindex(temas).fillna(0)
    # sem proposta concreta de Flávio no plano oficial: omissão na matriz ou força zero com Lula forte
    flavio_fraco = [t for t in temas if t not in EVITAR and fl[t] > 0 and (t in omisso or ff[t] == 0 or ff[t] < fl[t] / 3)]
    disputados = [t for t in temas if t not in EVITAR and base[t] >= 0.14 and vant[t] <= 0.2]
    aderiveis = [t for t in temas if t not in EVITAR and t not in disputados and fl[t] > 0 and vant[t] > -0.2]

    p = sinais(a.unidade, un)
    rel = pd.DataFrame(1.0, index=un.index, columns=temas)
    for s, ts in GATILHOS.items():
        for t in ts:
            if t in rel:
                rel[t] += p[s] - 0.5
    bonus = pd.DataFrame(0.0, index=un.index, columns=temas)
    for t in temas:
        alvos = [PUBLICO_SINAL[x] for x in pub.get(t, []) if x in PUBLICO_SINAL]
        if alvos:
            bonus[t] = 0.25 * (p[alvos].max(axis=1) >= 0.8)
    escore = rel.mul(base, axis=1).mul(1 + vant, axis=1) * (1 + bonus)
    # portões: tema territorial só entra onde o sinal local existe de fato (decisão de 08/10, 7h40: "agricultura
    # familiar" aparecia em bairros urbanos de Sorocaba porque a vantagem de Lula no plano o empurrava para cima)
    b = p.attrs["bruto"]
    portoes = {"agricultura_familiar": b["rural"] >= 0.20, "agronegocio_meio_ambiente": b["rural"] >= 0.20,
               "periferias_favelas": b["favela"] > 0, "saneamento": b["sem_esgoto"] >= 50,
               "soberania_nacional": b["soberania"].isin(["alta", "média"])}
    for t, ok in portoes.items():
        if t in escore:
            escore.loc[~ok.to_numpy(), t] = np.nan

    def top(i, pool, k, ref):
        r = ref.loc[i, pool].dropna().sort_values(ascending=False)
        return ";".join(r.index[:k])
    out = un[["id_unidade", "uf", "cd_mun_ibge", "nome"]].copy()
    out["temas_aderentes_lula"] = [top(i, aderiveis, 3, escore) for i in un.index]
    rel_f = rel.mul(base, axis=1)
    for t, ok in portoes.items():
        if t in rel_f:
            rel_f.loc[~ok.to_numpy(), t] = np.nan
    out["temas_flavio_mais_fraco"] = [top(i, flavio_fraco, 2, rel_f) for i in un.index]
    out["temas_disputados"] = [top(i, disputados, 2, rel.mul(base, axis=1)) for i in un.index]
    out["temas_evitar"] = ";".join(EVITAR)
    out["sinais_fortes"] = [";".join(s for s in p.columns if p.at[i, s] >= 0.8) for i in un.index]
    out["forca_soberania"] = un["cd_mun_ibge"].map(pd.read_csv(os.path.join(INS, "contexto", "soberania_municipios.csv"))
                                                   .set_index("cd_municipio_ibge")["forca_soberania"])
    out["rotulo"] = "hipótese de comunicação derivada de dados agregados; não descreve moradores"
    out.to_parquet(os.path.join(VAR, a.unidade, "temas_unidades.parquet"), index=False)
    # citações por tema (o mapa e o notebook usam)
    cits = {t: {"lula": cit.get(t, {}).get("lula"), "flavio": cit.get(t, {}).get("flavio"),
                "flavio_omisso": bool(t in omisso or ff[t] == 0), "forca_lula": int(fl[t]), "forca_flavio": int(ff[t]),
                "vantagem": round(float(vant[t]), 2)} for t in temas}
    json.dump(cits, open(os.path.join(VAR, a.unidade, "temas_citacoes.json"), "w"), ensure_ascii=False, indent=1)
    print("força no plano (lula/flávio) e vantagem:")
    print(pd.DataFrame({"lula": fl, "flavio": ff, "vantagem": vant.round(2), "base": base.round(2)}).sort_values("vantagem").to_string())
    print("Flávio mais fraco:", flavio_fraco); print("disputados:", disputados)
    print(out["temas_aderentes_lula"].str.split(";").explode().value_counts().head(12).to_string())


if __name__ == "__main__":
    main()
