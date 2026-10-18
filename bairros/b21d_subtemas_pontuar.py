#!/usr/bin/env python3
"""Etapa B21d: subtemas por área e por município, com o motivo local de cada um.

Para cada área e cada tema que aparece nas sugestões dela (puxar, contraste, disputados; b09), escolhe os subtemas:
  necessidade local  média dos postos percentuais (0 a 1) dos indicadores do subtema (b21c), no sentido da necessidade:
                     indicador de área comparado entre as áreas do país; de município, entre os municípios. Sem indicador: 0,5.
  força nos planos   compromissos de cada candidato no subtema (b21b): vantagem = (Lula - Flávio) / (Lula + Flávio + 1)
  puxar:      (0,5 + necessidade) x (1 + vantagem) x raiz(propostas de Lula)
  disputados: (0,5 + necessidade) x raiz(propostas de Lula) x (1 + vantagem/2)
  contraste:  (0,5 + necessidade) x (Lula / (Lula + Flávio)) x raiz(propostas de Lula), só onde Flávio tem menos que Lula
O motivo é o indicador mais acima da média no lugar, em texto simples (ex.: "UBS mais próxima a 3,2 km").
Município: necessidade média das áreas (pelo eleitorado) e indicadores do próprio município.

Saídas: variantes/<U>/subtemas_areas.json (id_unidade -> {tema: [[subtema, motivo], ...]}),
        variantes/<U>/subtemas_municipios.json e bairros/insumos/temas/subtemas_resumo.csv
"""
import json, os, sys
import numpy as np
import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from b15_relatorios_cidades import TEMA   # noqa: E402
norm = lambda x: "".join(c for c in x.lower() if c.isalnum())
TEMAS = os.path.join(RAIZ, "bairros", "insumos", "temas")
NUM = lambda v, c=0: f"{v:,.{c}f}".replace(",", "§").replace(".", ",").replace("§", ".")
MOTIVO = {
    "ubs_dist_km": lambda v: f"posto de saúde mais próximo a {NUM(v, 1)} km",
    "ubs_por_10mil": lambda v: "nenhum posto de saúde a até 2 km" if v < 0.05 else
        f"{NUM(v, 1)} {'posto' if v < 1.95 else 'postos'} de saúde por 10 mil moradores num raio de 2 km",
    "urgencia_dist_km": lambda v: f"pronto-atendimento mais próximo a {NUM(v, 0)} km",
    "especialidade_por_100mil": lambda v: "nenhum centro de especialidade na cidade" if v < 0.5 else
        f"{NUM(v, 0)} {'centro' if v < 1.5 else 'centros'} de especialidade por 100 mil habitantes na cidade",
    "caps_por_100mil": lambda v: "nenhum CAPS na cidade" if v == 0 else f"{NUM(v, 1)} CAPS por 100 mil habitantes na cidade",
    "pct_0a4": lambda v: f"{NUM(v, 1)}% dos moradores têm até 4 anos",
    "pct_15a24": lambda v: f"{NUM(v, 0)}% dos moradores têm de 15 a 24 anos",
    "pct_60m": lambda v: f"{NUM(v, 0)}% dos moradores têm 60 anos ou mais",
    "pct_70m": lambda v: f"{NUM(v, 0)}% dos moradores têm 70 anos ou mais",
    "analfab_15m": lambda v: f"{NUM(v, 0)}% dos adultos não sabem ler e escrever",
    "renda_resp": lambda v: f"renda média do responsável pela casa de R$ {NUM(v, 0)}",
    "sem_esgoto": lambda v: f"{NUM(v, 0)}% das casas sem esgoto adequado",
    "sem_agua": lambda v: f"{NUM(v, 0)}% das casas sem água da rede",
    "sem_lixo": lambda v: f"{NUM(v, 0)}% das casas sem coleta de lixo",
    "favela": lambda v: f"{NUM(v, 0)}% dos moradores em favela ou comunidade urbana",
    "rural": lambda v: f"{NUM(v, 0)}% dos moradores em área rural",
    "creche_cobertura": lambda v: f"vagas em creche para {NUM(min(v, 100), 0)}% das crianças pequenas da cidade",
    "integral_pct": lambda v: "nenhum aluno da cidade em tempo integral" if v < 0.5 else f"só {NUM(v, 0)}% dos alunos da cidade em tempo integral",
    "escolas_sem_internet_pct": lambda v: f"{NUM(v, 0)}% das escolas públicas da cidade sem internet para os alunos",
    "bf_pct": lambda v: f"Bolsa Família em {NUM(v, 0)}% das casas da cidade",
    "pobreza_cadunico": lambda v: f"{NUM(v, 0)}% das casas da cidade em pobreza no CadÚnico",
    "caged_var": lambda v: f"emprego formal na cidade {'caiu' if v < 0 else 'cresceu só'} {NUM(abs(v), 1)}% em 12 meses",
    "agro_familiar_pct": lambda v: f"{NUM(v, 0)}% das propriedades rurais da cidade são da agricultura familiar",
    "agro_sem_ater_pct": lambda v: f"{NUM(v, 0)}% dos agricultores familiares da cidade sem assistência técnica",
    "agro_sem_energia_pct": lambda v: f"{NUM(v, 0)}% dos agricultores familiares da cidade sem energia elétrica",
    "eua_agro_por_eleitor": lambda v: f"US$ {NUM(v, 0)} por eleitor da cidade em produtos do campo vendidos aos EUA",
    "eua_ind_por_eleitor": lambda v: f"US$ {NUM(v, 0)} por eleitor da cidade em produtos industriais vendidos aos EUA",
    "eua_petroleo_por_eleitor": lambda v: f"US$ {NUM(v, 0)} por eleitor da cidade em petróleo vendido aos EUA",
    "amazonia": lambda v: "cidade da Amazônia Legal",
}


def main():
    uni = sys.argv[1] if len(sys.argv) > 1 else "U4"
    pasta = os.path.join(RAIZ, "variantes", uni)
    tax = {t: v for t, v in json.load(open(os.path.join(TEMAS, "subtemas.json"))).items() if not t.startswith("_")}
    pl = pd.read_csv(os.path.join(TEMAS, "subtemas_planos.csv"))
    forca = {(r.cand, r.subtema): r.forca for r in pl.itertuples()}
    a = pd.read_parquet(os.path.join(pasta, "subtemas_ind_area.parquet")).set_index("id_unidade")
    m = pd.read_parquet(os.path.join(pasta, "subtemas_ind_municipio.parquet")).set_index("cd_mun_ibge")
    un = pd.read_parquet(os.path.join(pasta, "unidades.parquet"), columns=["id_unidade", "cd_mun_ibge", "eleitores_2026"]).set_index("id_unidade")
    un["cd_mun_ibge"] = un["cd_mun_ibge"].astype("Int64").astype(str)
    a = a.reindex(un.index)
    a["cd_mun_ibge"] = un["cd_mun_ibge"]
    # postos percentuais (necessidade) por indicador
    rk = {}
    for c in a.columns:
        if c in MOTIVO:
            rk[("area", c)] = a[c].rank(pct=True)
    for c in m.columns:
        if c in MOTIVO:
            rk[("municipio", c)] = m[c].rank(pct=True)
    tm = pd.read_parquet(os.path.join(pasta, "temas_unidades.parquet")).set_index("id_unidade")
    pop_mun = pd.read_parquet(os.path.join(pasta, "unidades.parquet"), columns=["cd_mun_ibge", "pop"]) \
        .assign(cd_mun_ibge=lambda d: d["cd_mun_ibge"].astype("Int64").astype(str)).groupby("cd_mun_ibge")["pop"].sum().to_dict()
    tem = {c: c for c in tm.columns}
    print("colunas de temas:", list(tm.columns)[:12])
    res_area, resumo = {}, []
    sub_info = {s["chave"]: (t, s) for t, lst in tax.items() for s in lst}

    def necessidade(uid, s):
        vals, mot = [], []
        for ind, sinal, nivel in s["ind"]:
            # área residual (sem setor): necessidade com os valores da cidade, mas sem motivo "da área"
            mostrar = not (nivel == "area" and uid in a.index and bool(a.at[uid, "ind_da_cidade"]))
            if nivel == "area":
                r = rk.get(("area", ind)); v = a.at[uid, ind] if uid in a.index else np.nan; rr = r.get(uid) if r is not None else np.nan
            else:
                mun = a.at[uid, "cd_mun_ibge"] if uid in a.index else None
                r = rk.get(("municipio", ind)); v = m.at[mun, ind] if mun in m.index else np.nan; rr = r.get(mun) if r is not None and mun in m.index else np.nan
            if pd.isna(rr):
                continue
            n = rr if sinal > 0 else 1 - rr
            vals.append(n)
            if n >= 0.6 and not pd.isna(v) and mostrar and not (sinal > 0 and v < 0.5):
                mot.append((n, MOTIVO[ind](float(v))))
        nec = float(np.mean(vals)) if vals else 0.5
        motivo = max(mot)[1] if mot else ""
        return nec, motivo

    def escolher(uid, tema, modo):
        cand = []
        for s in tax.get(tema, []):
            L, F = forca.get(("lula", s["chave"]), 0), forca.get(("flavio", s["chave"]), 0)
            req = s.get("requer", {})   # subtema que só vale em área urbana ou na Amazônia Legal
            if req.get("urbano") and uid in a.index and (a.at[uid, "rural"] > 50 or pop_mun.get(a.at[uid, "cd_mun_ibge"], 0) < 50000):
                continue
            if req.get("amazonia") and m.at[a.at[uid, "cd_mun_ibge"], "amazonia"] < 1 if a.at[uid, "cd_mun_ibge"] in m.index else False:
                continue
            if L < 4:   # menos de 4 de força (ex.: 1 parágrafo concreto) é base fraca para recomendar
                continue
            # tema de puxar: só subtema em que o plano de Lula tem mais propostas; tema disputado: ao menos empate
            if (modo == "a" and L <= F) or (modo == "d" and L < F):
                continue
            # subtema com o mesmo nome do tema não acrescenta nada à conversa
            if norm(s["nome"]) == norm(TEMA.get(tema, "")):
                continue
            nec, mot = necessidade(uid, s)
            # o volume de propostas de Lula no subtema também conta (raiz): evita que um subtema com 1 ou 2 parágrafos
            # ganhe só pela proporção, quando não há dado local para diferenciar os lugares
            if modo == "f":
                if F >= L:
                    continue
                sc = (0.5 + nec) * (L / (L + F)) * np.sqrt(L)
            elif modo == "d":
                sc = (0.5 + nec) * np.sqrt(L) * (1 + 0.5 * (L - F) / (L + F + 1))
            else:
                sc = (0.5 + nec) * (1 + (L - F) / (L + F + 1)) * np.sqrt(L)
            cand.append((sc, s["chave"], mot))
        cand.sort(reverse=True)
        return [[c, mo] for _, c, mo in cand[:2]]

    for uid in un.index:
        if uid not in tm.index:
            continue
        r = tm.loc[uid]
        saida = {}
        for modo, col in (("a", "temas_aderentes_lula"), ("f", "temas_flavio_mais_fraco"), ("d", "temas_disputados")):
            if col not in tm.columns:
                continue
            temas = [t for t in str(r[col]).split(";") if t and t != "nan"]
            for t in temas:
                ch = escolher(uid, t, modo)
                if ch:
                    saida.setdefault(t, {})[modo] = ch
        res_area[uid] = saida
    json.dump(res_area, open(os.path.join(pasta, "subtemas_areas.json"), "w"), ensure_ascii=False)
    # município: subtemas mais frequentes nas áreas, pesados pelo eleitorado, com o motivo mais citado
    nomes_area = pd.read_parquet(os.path.join(pasta, "unidades.parquet"), columns=["id_unidade", "nome"]).set_index("id_unidade")["nome"].to_dict()
    res_mun = {}
    for mun, g in un.groupby("cd_mun_ibge"):
        cont = {}
        for uid, ap in g["eleitores_2026"].items():
            for t, mod in res_area.get(uid, {}).items():
                for modo, lst in mod.items():
                    for i, (s, mo) in enumerate(lst):
                        k = (t, modo, s)
                        c = cont.setdefault(k, [0, {}]); c[0] += ap * (1 - 0.3 * i)
                        if mo:   # motivo com o nome do bairro de onde vem o dado (no nível da cidade, "na área" fica ambíguo)
                            nome = nomes_area.get(uid, "")
                            mo_c = f"em {nome}: {mo}" if nome and not mo.endswith("na cidade") and "cidade" not in mo else mo
                            c[1][mo_c] = c[1].get(mo_c, 0) + ap
        por = {}
        for (t, modo, s), (w, mos) in sorted(cont.items(), key=lambda x: -x[1][0]):
            lst = por.setdefault(t, {}).setdefault(modo, [])
            if len(lst) < 2:
                lst.append([s, max(mos, key=mos.get) if mos else ""])
        res_mun[mun] = por
    json.dump(res_mun, open(os.path.join(pasta, "subtemas_municipios.json"), "w"), ensure_ascii=False)
    # resumo nacional: quantas áreas recebem cada subtema
    from collections import Counter
    c = Counter((t, s) for v in res_area.values() for t, mod in v.items() for lst in mod.values() for s, _ in lst[:1])
    pd.DataFrame([{"tema": t, "subtema": s, "nome": sub_info[s][1]["nome"], "areas": n} for (t, s), n in c.most_common()]) \
        .to_csv(os.path.join(TEMAS, "subtemas_resumo.csv"), index=False)
    print(f"áreas com subtemas: {sum(1 for v in res_area.values() if v):,} de {len(res_area):,}; municípios: {len(res_mun):,}")
    print(pd.read_csv(os.path.join(TEMAS, "subtemas_resumo.csv")).head(15).to_string(index=False))


if __name__ == "__main__":
    main()
