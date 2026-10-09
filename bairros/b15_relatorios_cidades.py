#!/usr/bin/env python3
"""Etapa B15: um relatório por município (os 5.571; `--minimo N` limita a cidades com mais de N habitantes), em linguagem simples.

Uso interno (pasta resultados/, fora do git). Lê os mesmos dados do site (mapa/bairros/dados.json e uf/XX.json),
para que os números batam com o mapa, mais a tabela de áreas (resultado de 2026 e 2022) e o Censo por setor.
Os "achados" são regras fixas sobre os números (nenhum texto é gerado por modelo de linguagem): cada frase
sai de um cálculo, e o relatório mostra o número que a sustenta.

Saídas: resultados/<UF>/<cidade>_<código>.md e resultados/LEIAME.md (índice ordenado por votos a recuperar).
"""
import json, os, re, unicodedata
from datetime import date
import numpy as np
import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(RAIZ, "mapa", "bairros")
OUT = os.path.join(RAIZ, "resultados")
LIMIAR = 0          # habitantes (Censo 2022); 0 = todos os municípios
PORTES = [(0, 20_000, "até 20 mil habitantes"), (20_000, 50_000, "20 mil a 50 mil habitantes"),
          (50_000, 100_000, "50 mil a 100 mil habitantes"), (100_000, 500_000, "100 mil a 500 mil habitantes"),
          (500_000, 10 ** 9, "mais de 500 mil habitantes")]


def porte(p):
    return next(r for a, b, r in PORTES if a <= p < b)

TEMA = {"emprego": "emprego", "jornada_6x1": "fim da escala 6x1", "renda_salario_minimo": "salário mínimo e renda",
        "custo_de_vida_inflacao_alimentos": "custo de vida e preço dos alimentos", "saude_sus": "saúde (SUS)",
        "educacao": "educação", "seguranca_publica": "segurança pública",
        "moradia_mcmv": "moradia (Minha Casa, Minha Vida)", "transporte_mobilidade": "transporte",
        "programas_sociais": "programas sociais (Bolsa Família)", "impostos_isencao_ir": "isenção do Imposto de Renda",
        "previdencia": "Previdência", "agronegocio_meio_ambiente": "agronegócio e meio ambiente",
        "costumes_religiao": "costumes e religião", "corrupcao": "corrupção", "instituicoes_stf_reeleicao": "STF e reeleição",
        "endividamento_apostas": "endividamento e apostas", "saneamento": "saneamento",
        "periferias_favelas": "periferias e favelas", "agricultura_familiar": "agricultura familiar",
        "soberania_nacional": "soberania nacional"}
NOTA = {1: "muito pouco retorno por esforço", 2: "pouco retorno", 3: "retorno abaixo da média", 4: "retorno médio",
        5: "retorno acima da média", 6: "bom retorno", 7: "muito retorno por esforço"}


def mil(v, casas=1):
    """Número em linguagem de jornal: 1.234 / 12,3 mil / 1,2 milhão."""
    v = float(v); a = abs(v); s = "-" if v < 0 else ""
    if a >= 1e6:
        return f"{s}{a / 1e6:.2f} milhões".replace(".", ",")
    if a >= 1e4:
        return f"{s}{a / 1e3:.{casas}f} mil".replace(".", ",")
    return s + f"{a:,.0f}".replace(",", ".")


def pct(v, casas=1):
    return f"{v:.{casas}f}%".replace(".", ",")


def pp(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "sem dado de 2022"      # área nova: locais de votação que não existiam em 2022
    return f"{v:+.1f} ponto{'s' if abs(round(v, 1)) != 1 else ''}".replace(".", ",")


def faixa(t):
    return f"{mil(t[1])} (provável entre {mil(t[0])} e {mil(t[2])})"


def nome_cidade(n):
    return re.sub(r"(?<=\s)(De|Da|Do|Das|Dos|E)(?=\s)", lambda x: x.group(1).lower(), n)


def arquivo(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def carregar():
    D = json.load(open(os.path.join(SITE, "dados.json")))
    areas = {}
    for uf in D["meta"]["ufs"]:
        for k, a in json.load(open(os.path.join(SITE, "uf", f"{uf}.json"))).items():
            areas[k] = a
    A = pd.DataFrame.from_dict(areas, orient="index")
    A.index.name = "id_unidade"
    tab = pd.read_csv(os.path.join(RAIZ, "variantes", D["meta"]["unidade"], D["meta"]["metodo"], "tabelas", "areas.csv"),
                      usecols=["id_unidade", "validos", "lula", "lula_pct_26", "lula_pct_22_2t", "renda_media_responsavel"])
    A = A.join(tab.set_index("id_unidade"))
    infra = pd.read_parquet(os.path.join(RAIZ, "variantes", D["meta"]["unidade"], "infra_areas.parquet")).set_index("id_unidade")
    A = A.join(infra)
    cs = pd.read_parquet(os.path.join(RAIZ, "dados_bairros", "proc", "censo_setores.parquet"), columns=["CD_MUN", "pop"])
    pop = cs.groupby(cs["CD_MUN"].astype("Int64").astype(str))["pop"].sum()
    return D, A, pop


COMPROMISSO = re.compile(r"\b(vamos|iremos|vai|ampliar|ampliaremos|criar|criaremos|garantir|garantiremos|implantar|"
                         r"expandir|fortalecer|reduzir|zerar|isentar|valorizar|construir|construiremos|meta|investir)\b", re.I)


def citacoes_planos():
    """Frase de compromisso por (candidato, tema): parágrafos concretos ou com meta primeiro, frase com verbo de
    compromisso e de tamanho legível. Cópia literal do plano (o texto não é reescrito)."""
    pr = pd.read_csv(os.path.join(RAIZ, "bairros", "insumos", "temas", "propostas_paragrafos.csv"))
    pr = pr[pr["ok_modelo"].astype(str) == "True"]
    out = {}
    for _, r in pr.iterrows():
        for t in str(r["temas"]).split(";"):
            frases = re.split(r"(?<=[.;!?])\s+", str(r["texto"]))
            for f in frases:
                f = f.strip()
                if not (60 <= len(f) <= 260) or not COMPROMISSO.search(f) or f.isupper():
                    continue
                nota = 2 * (str(r["meta_numerica"]) == "True") + (str(r["concreto"]) == "True") + 0.5 * bool(re.search(r"\d", f))
                k = (r["cand"], t)
                if k not in out or nota > out[k][0]:
                    out[k] = (nota, int(r["pagina"]), f)
    return {k: (p, f) for k, (n, p, f) in out.items()}


CITA = {}
CTX = {}
PT = {2010: "Dilma", 2014: "Dilma", 2018: "Haddad", 2022: "Lula"}


def contexto(cids):
    """Por município: série do PT no 2º turno (2010-2022), abstenção, votos de outros candidatos em 2026,
    Bolsa Família/CadÚnico (MDS), emprego formal em 12 meses (Novo CAGED) e domicílios (Censo)."""
    proc = os.path.join(RAIZ, "dados_bairros", "proc")
    mapa = []
    for f in ("secao_unidade.parquet", "secao_unidade_hist.parquet"):
        mapa.append(pd.read_parquet(os.path.join(RAIZ, "variantes", "U4", f), columns=["ano", "cd_mun_tse", "cd_mun_ibge"]))
    tse_ibge = pd.concat(mapa).dropna().drop_duplicates("cd_mun_tse")[["cd_mun_tse", "cd_mun_ibge"]]   # código do TSE é fixo
    tse_ibge["cd_mun_ibge"] = tse_ibge["cd_mun_ibge"].astype("Int64").astype(str)
    out = {k: {"hist": {}} for k in cids}
    for ano in (2010, 2014, 2018, 2022, 2026):
        d = pd.read_parquet(os.path.join(proc, f"secoes_{ano}.parquet"),
                            columns=["turno", "cd_mun_tse", "lula", "adversario", "terceiros", "aptos", "abstencoes"])
        d = d.merge(tse_ibge, on="cd_mun_tse", how="left")
        g = d.groupby(["cd_mun_ibge", "turno"])[["lula", "adversario", "terceiros", "aptos", "abstencoes"]].sum()
        for k in cids:
            for t in (1, 2):
                if (k, t) not in g.index:
                    continue
                r = g.loc[(k, t)]
                reg = {"abst": 100 * r["abstencoes"] / r["aptos"]}
                if t == 2:
                    reg["pt"] = 100 * r["lula"] / (r["lula"] + r["adversario"])
                else:
                    reg["terc"] = float(r["terceiros"]); reg["pt1"] = 100 * r["lula"] / (r["lula"] + r["adversario"] + r["terceiros"])
                out[k]["hist"][(ano, t)] = reg
    ctx = os.path.join(RAIZ, "bairros", "insumos", "contexto")
    bf = pd.read_csv(os.path.join(ctx, "bolsa_familia.csv"), dtype={"cd_municipio_ibge": str})
    bf = bf.sort_values("anomes").groupby("cd_municipio_ibge").last()
    cg = pd.read_csv(os.path.join(ctx, "caged.csv"), dtype={"cd_municipio_ibge": str})
    cg = cg[cg["periodo"].str.startswith("12m")].set_index("cd_municipio_ibge")
    cs = pd.read_parquet(os.path.join(proc, "censo_setores.parquet"), columns=["CD_MUN", "domicilios"])
    dom = cs.groupby(cs["CD_MUN"].astype("Int64").astype(str))["domicilios"].sum()
    for k in cids:
        if k in bf.index:
            out[k]["bf"] = bf.loc[k].to_dict()
        if k in cg.index:
            out[k]["caged"] = cg.loc[k].to_dict()
        out[k]["dom"] = float(dom.get(k, np.nan))
    cg["uf"] = cg["uf"].astype(str)
    out["_caged_uf"] = cg.groupby("uf")["variacao_relativa_pct"].median().to_dict()
    return out


def temas_cidade(sub):
    """Temas das áreas somados pelo eleitorado: o tema que aparece nas áreas com mais eleitores vem primeiro."""
    out = {}
    for c in ("a", "f", "d", "e"):
        peso = {}
        for tm, ap in zip(sub["tm"], sub["ap"]):
            if not isinstance(tm, dict):
                continue
            for i, t in enumerate(tm.get(c, [])):
                peso[t] = peso.get(t, 0) + ap * (1 - 0.15 * i)   # o 1º da lista da área pesa um pouco mais
        tot = sub["ap"].sum()
        out[c] = [(t, w / tot) for t, w in sorted(peso.items(), key=lambda x: -x[1])]
    return out


def relatorio(k, m, D, A, pop, ranks, n_cid):
    G = D["grupos"]["municipio"]
    uf, nome = m["uf"], nome_cidade(m["n"])
    sub = A[A["m"] == k].copy()
    sub["nota"] = sub["v"].map(lambda v: v[1] if isinstance(v, list) else None)   # [P1, P2, P3]; o site usa P2
    sub["pot50"] = sub["pot"].map(lambda t: t[1])
    pot, mob = G["potencial"][k], G["mob"][k]
    mb, md = G["margem_base"][k], G["margem_dir"][k]
    inst = uf in set(D["meta"]["ufs_instaveis"])
    nac = D["meta"]["nac_desloc"]
    v22 = sub["lula_pct_22_2t"].fillna(sub["l22"])
    okv = sub["validos"].fillna(0).gt(0) & sub["lula"].notna() & v22.notna()     # áreas residuais ficam de fora
    val = sub.loc[okv, "validos"]
    l26 = 100 * sub.loc[okv, "lula"].sum() / val.sum() if val.sum() else np.nan
    l22 = np.average(v22[okv], weights=val) if val.sum() else np.nan
    desloc = l26 - l22
    L = []
    w = L.append
    w(f"# {nome} ({uf})")
    w("")
    w(f"*Relatório interno da Estel Tecnologia · gerado em {date.today().strftime('%d/%m/%Y')} a partir do mapa "
      f"\"Onde ganhar votos para Lula exige menos esforço\" (2º turno de 2026). Produção independente, sem relação com a "
      f"campanha oficial.*")
    w("")
    hab = f"{mil(pop[k])} habitantes (Censo 2022)" if pop.get(k, 0) > 0 else "município criado depois do Censo 2022 (sem população recenseada)"
    w(f"{hab} · {mil(m['ap'])} eleitores aptos · "
      f"{m.get('rm') or 'fora de região metropolitana'} · {m['u']} área(s) no mapa")
    w("")
    reproc = uf in set(D["meta"].get("ufs_reprocessando", []))
    if uf in set(D["meta"].get("ufs_conferidas", [])):
        w(f"> **Cálculo difícil em {uf}, mas a nota foi conferida e é estável.** Os cálculos deste estado foram mais difíceis "
          f"que o normal; testamos e a nota de cada lugar quase não muda. Os números absolutos têm um pouco mais de incerteza.")
        w("")
    if inst or reproc:
        txt = []
        if inst:
            txt.append(f"**Atenção: estimativa menos segura em {uf}.** Neste estado, os cálculos variaram mais do que o normal. "
                       f"Use os números como orientação geral e confira com quem conhece o território.")
        if reproc:
            txt.append(f"**Atualização prevista para {D['meta'].get('atualizacao_prevista', 'breve')}:** os números de {uf} "
                       f"estão sendo recalculados com um processamento mais longo, para deixar a estimativa mais segura. A nota, "
                       f"os votos a recuperar e os temas deste relatório podem mudar. Baixe o relatório de novo depois da atualização.")
        w("> " + " ".join(txt))
        w("")

    # ---------------------------------------------------------------- resumo
    w("## Resumo")
    w("")
    pt = porte(pop.get(k, 0))
    w(f"* **Nota da cidade: {m['v']} de 7** ({NOTA[m['v']]}). Entre as {mil(n_cid)} cidades do país, {nome} é a "
      f"**{mil(ranks['pot'][k])}ª** em votos que dá para recuperar e a **{mil(ranks['pot_mil'][k])}ª** em votos a recuperar por "
      f"mil eleitores. Entre as {mil(ranks['n_porte'][pt])} cidades com {pt}, é a **{mil(ranks['pot_porte'][k])}ª**.")
    w(f"* **Votos que dá para recuperar:** {faixa(pot)}.")
    if not np.isnan(desloc):
        comp = "mais" if desloc < nac - 0.5 else ("menos" if desloc > nac + 0.5 else "o mesmo tanto")
        w(f"* **Lula no 1º turno de 2026:** {pct(l26)} dos votos válidos, contra {pct(l22)} no 2º turno de 2022 "
          f"({pp(desloc)}). No país, a variação foi de {pp(nac)}: aqui Lula caiu {comp}"
          f"{'' if comp == 'o mesmo tanto' else ' que a média'}.")
    lado = "Lula" if mb[1] > 0 else "Flávio"
    lo, hi = sorted((abs(mb[0]), abs(mb[2])))
    lado2 = "Lula" if md[1] > 0 else "Flávio"
    w(f"* **Se o comportamento de 2022 entre os turnos se repetir**, {lado} fica na frente na cidade por "
      f"{mil(abs(mb[1]))} votos (provável entre {mil(lo)} e {mil(hi)}). Se os eleitores dos outros candidatos forem "
      f"mais para Flávio, {'a vantagem passa a ser de ' + lado2 + ', com ' if lado2 != lado else 'a diferença fica em '}"
      f"{mil(abs(md[1]))} votos.")
    w("")

    # ---------------------------------------------------------------- o que fazer
    cx = CTX.get(k, {"hist": {}})
    h = cx["hist"]
    t = temas_cidade(sub)
    ok = sub[sub["nota"].notna()].sort_values("pot50", ascending=False)
    terc26 = h.get((2026, 1), {}).get("terc", np.nan)
    v26 = sub["validos"].fillna(0).sum()          # válidos de 2026 (inclui áreas sem dado de 2022)
    terc_pct = 100 * terc26 / v26 if v26 else np.nan
    tb, td = G["terc_base"][k], G["terc_dir"][k]
    w("## O que fazer, em resumo")
    w("")
    prio = "alta" if m["v"] >= 6 else ("média" if m["v"] >= 4 else "baixa")
    w(f"* **Prioridade para receber esforço de fora da cidade: {prio}** (nota {m['v']} de 7). "
      + ("Vale deslocar militância e recursos para cá." if prio == "alta" else
         "Vale manter a campanha local ativa, sem tirar recursos de cidades com nota mais alta." if prio == "média" else
         "A militância local deve trabalhar aqui, mas reforços de fora rendem mais em outras cidades."))
    estr = []
    if mob[0] > 0:
        estr.append("**levar gente às urnas** (o comparecimento favorece Lula)")
    if not np.isnan(desloc) and desloc < nac - 1:
        estr.append("**reconquistar quem votou em Lula em 2022** e se afastou (a queda aqui foi maior que no país)")
    if not np.isnan(terc_pct) and terc_pct >= 8:
        estr.append(f"**disputar os eleitores de outros candidatos** ({pct(terc_pct, 0)} dos votos válidos no 1º turno"
                    + (", que hoje tendem a ir para Flávio)" if tb[1] < 0 else ", que tendem a ajudar Lula)"))
    rr0 = sub[okv & sub["renda_media_responsavel"].notna()]
    if len(rr0) >= 6:
        q0 = rr0["renda_media_responsavel"].rank(pct=True)
        b0, a0 = rr0[q0 <= 1 / 3], rr0[q0 > 2 / 3]
        if np.average(b0["d"].fillna(0), weights=b0["validos"]) < np.average(a0["d"].fillna(0), weights=a0["validos"]) - 1:
            estr.append("**priorizar as áreas de renda mais baixa**, onde Lula perdeu mais desde 2022")
    if not estr:
        estr.append("**segurar a base** e ampliar pela conversa com temas (pouco terreno perdido e mobilização sem ganho claro)")
    w(f"* **Estratégia principal:** {'; '.join(estr)}.")
    if len(ok) >= 3:
        w(f"* **Onde começar:** {', '.join(ok['n'].head(3))}.")
    nomes_t = lambda l, n: ", ".join(TEMA.get(x, x) for x, _ in l[:n]) or "–"
    w(f"* **Com que temas:** {nomes_t(t['a'], 2)}; contraste com Flávio em {nomes_t(t['f'], 1)}. "
      f"Evite puxar {nomes_t(t['e'], 2)}.")
    w("")

    # ---------------------------------------------------------------- achados
    w("## Principais achados")
    w("")
    ach = []
    tot_pot = sub["pot50"].clip(lower=0).sum()
    if pot[1] <= 0 or tot_pot <= 0:
        ach.append("**Pouco terreno a recuperar.** Lula não perdeu aqui mais do que perdeu no país, e levar mais gente às "
                   "urnas não tende a ajudá-lo. O esforço rende mais em outras cidades: a prioridade aqui é manter os votos "
                   "do 1º turno.")
    else:
        n20 = max(1, int(np.ceil(0.2 * len(ok))))
        conc = ok["pot50"].clip(lower=0).head(n20).sum() / tot_pot
        if len(ok) >= 5:
            ach.append(f"**O potencial está {'concentrado' if conc >= 0.6 else 'espalhado'}.** As {n20} áreas com mais votos "
                       f"a recuperar (20% das áreas) somam {pct(100 * conc, 0)} do potencial da cidade"
                       f"{': o esforço pode se concentrar nelas' if conc >= 0.6 else ': vale uma ação que cubra a cidade toda'}.")
    if not np.isnan(desloc) and desloc < nac - 2:
        ach.append(f"**Queda acima da média.** Lula caiu {pp(desloc - nac).lstrip('+-')} a mais que no país entre 2022 e "
                   f"2026: é terreno de quem já votou nele e pode voltar.")
    elif not np.isnan(desloc) and desloc > nac + 2:
        ach.append("**Lula resistiu melhor que no país.** O espaço para recuperar votos é menor; o foco é segurar a base e "
                   "ampliar com temas.")
    pm = sub["pr"].fillna(0)
    ap_ajuda = sub.loc[pm >= 0.7, "ap"].sum() / sub["ap"].sum()
    ap_atrap = sub.loc[pm <= 0.3, "ap"].sum() / sub["ap"].sum()
    if mob[0] > 0:
        ach.append(f"**Levar mais gente às urnas ajuda Lula aqui.** Com mais 2 de cada 100 eleitores votando, Lula "
                   f"ganha {mil(mob[1])} votos de saldo (provável entre {mil(mob[0])} e {mil(mob[2])}). Mobilização para o comparecimento (transporte, lembrete do dia da "
                   f"votação) é prioridade.")
    elif mob[2] < 0:
        ach.append(f"**Mobilização geral não ajuda na cidade como um todo:** com mais 2 de cada 100 eleitores votando, o "
                   f"saldo é de {mil(mob[1])} votos para Lula (provável entre {mil(mob[0])} e {mil(mob[2])}; negativo = "
                   f"vantagem de Flávio). O comparecimento deve ser incentivado só nas áreas onde ele favorece Lula"
                   f"{f' ({pct(100 * ap_ajuda, 0)} dos eleitores)' if ap_ajuda >= 0.005 else ''}; no restante, o foco é "
                   f"conversa e temas." if ap_ajuda >= 0.005 else
                   f"**Mobilização geral não ajuda aqui:** com mais 2 de cada 100 eleitores votando, o saldo é de "
                   f"{mil(mob[1])} votos para Lula (provável entre {mil(mob[0])} e {mil(mob[2])}; negativo = vantagem de "
                   f"Flávio), e nenhuma área da cidade tem efeito favorável. O foco é conversa e temas com quem já vota.")
    else:
        ach.append(f"**Efeito do comparecimento incerto** (saldo de {mil(mob[1])} votos, provável entre {mil(mob[0])} "
                   f"e {mil(mob[2])}). Mobilizar só onde o mapa indica que ajuda: "
                   f"{pct(100 * ap_ajuda, 0)} dos eleitores estão em áreas onde a mobilização tende a favorecer Lula e "
                   f"{pct(100 * ap_atrap, 0)} em áreas onde tende a favorecer Flávio.")
    n7 = int((sub["nota"] >= 6).sum())
    if len(ok) >= 3:
        ach.append(f"**{n7} de {len(ok)} áreas com nota 6 ou 7** ({pct(100 * sub.loc[sub['nota'] >= 6, 'ap'].sum() / sub['ap'].sum(), 0)} "
                   f"dos eleitores).")
    sob = m.get("sob") or {}
    if sob.get("f") in ("alta", "média"):
        motivo = []
        if sob.get("eua"):
            motivo.append(f"US$ {sob['eua']:.0f} exportados aos EUA por eleitor em 2025".replace(".", ","))
        if sob.get("par"):
            motivo.append(f"{sob['par']:.0f}% das exportações da cidade vão para os EUA")
        if sob.get("am"):
            motivo.append("cidade da Amazônia Legal")
        ach.append(f"**Soberania nacional tem força {sob['f']} aqui** ({'; '.join(motivo)}). O tarifaço dos EUA atinge "
                   f"empregos locais: é um tema concreto, não abstrato.")
    if sub["pct_sem_esgoto_adequado"].notna().any():
        esg = np.average(sub["pct_sem_esgoto_adequado"].fillna(0), weights=sub["ap"])
        fav = np.average(sub["pct_pop_favela"].fillna(0), weights=sub["ap"])
        if esg >= 40:
            ach.append(f"**Saneamento é carência real:** {pct(esg, 0)} dos domicílios (média das áreas, pelo eleitorado) "
                       f"sem esgoto adequado no Censo 2022.")
        if fav >= 10:
            ach.append(f"**Periferias e favelas pesam:** cerca de {pct(fav, 0)} da população das áreas vive em favelas ou "
                       f"comunidades urbanas (Censo 2022).")
    for a in ach:
        w(f"* {a}")
    w("")

    # ---------------------------------------------------------------- mais achados
    mais = []
    serie = [(ano, h[(ano, 2)]["pt"]) for ano in (2010, 2014, 2018, 2022) if (ano, 2) in h]
    if len(serie) >= 3:
        txt = " · ".join(f"{ano} ({PT[ano]}): {pct(v)}" for ano, v in serie)
        melhor = max(serie, key=lambda x: x[1]); pior = min(serie, key=lambda x: x[1])
        mais.append(f"**Histórico do PT no 2º turno:** {txt}. Melhor resultado em {melhor[0]}, pior em {pior[0]}."
                    + (f" Em 2022, Lula ficou {pp(serie[-1][1] - melhor[1]).lstrip('+-')} abaixo do melhor resultado do "
                       f"PT na cidade: há eleitorado que já votou no partido." if serie[-1][1] < melhor[1] - 3 else ""))
    if (2022, 1) in h and (2026, 1) in h:
        a22, a26 = h[(2022, 1)]["abst"], h[(2026, 1)]["abst"]
        mais.append(f"**Abstenção no 1º turno:** {pct(a26)} em 2026, contra {pct(a22)} em 2022 ({pp(a26 - a22)}). "
                    + (f"São cerca de {mil(m['ap'] * (a26 - a22) / 100)} eleitores a mais em casa; "
                       + ("como o comparecimento favorece Lula aqui, trazê-los de volta é votos." if mob[0] > 0 else
                          "trazê-los de volta só ajuda nas áreas onde o comparecimento favorece Lula.")
                       if a26 - a22 >= 1 else "A abstenção não subiu de forma relevante."))
        if (2022, 2) in h:
            mais.append(f"**Entre os turnos de 2022** a abstenção foi de {pct(h[(2022, 1)]['abst'])} para "
                        f"{pct(h[(2022, 2)]['abst'])}: {'mais' if h[(2022, 2)]['abst'] > h[(2022, 1)]['abst'] else 'menos'} gente "
                        f"ficou em casa no 2º turno.")
    if not np.isnan(terc26) and terc26 > 0:
        mais.append(f"**Eleitores de outros candidatos:** {mil(terc26)} votos no 1º turno de 2026"
                    + (f" ({pct(terc_pct)} dos válidos). " if not np.isnan(terc_pct) else ". ") +
                    f"Se repetirem 2022, rendem saldo de {mil(tb[1])} votos para Lula no 2º turno; se forem mais para Flávio, "
                    f"{mil(td[1])} (negativo = vantagem de Flávio).")
    rr = sub[okv & sub["renda_media_responsavel"].notna()]
    if len(rr) >= 6:
        q = rr["renda_media_responsavel"].rank(pct=True)
        baixo, alto = rr[q <= 1 / 3], rr[q > 2 / 3]
        lb = 100 * baixo["lula"].sum() / baixo["validos"].sum(); la = 100 * alto["lula"].sum() / alto["validos"].sum()
        db = np.average(baixo["d"].fillna(0), weights=baixo["validos"]); da = np.average(alto["d"].fillna(0), weights=alto["validos"])
        mais.append(f"**Renda:** nas áreas de renda mais baixa (terço inferior da cidade), Lula teve {pct(lb)} em 2026; nas de "
                    f"renda mais alta, {pct(la)}. Desde 2022, a variação foi de {pp(db)} nas de renda baixa e {pp(da)} nas de "
                    f"renda alta" + (": **a perda foi maior na base de renda baixa**, onde o voto em Lula costuma ser mais "
                                     "fácil de recuperar." if db < da - 1 else
                                     ": a perda foi maior nas áreas de renda alta." if da < db - 1 else
                                     ": a perda foi parecida nos dois grupos."))
    bf = cx.get("bf")
    if bf and cx.get("dom", 0) > 0:
        sh = 100 * bf["pbf_familias_beneficiarias"] / cx["dom"]
        ref = CTX.get("_bf_mediana", {}).get(porte(pop.get(k, 0)), np.nan)
        mais.append(f"**Bolsa Família:** {mil(bf['pbf_familias_beneficiarias'])} famílias atendidas, cerca de {pct(sh, 0)} dos "
                    f"domicílios ({'acima' if sh > ref else 'abaixo'} da mediana das cidades com {porte(pop.get(k, 0))}, {pct(ref, 0)}). "
                    f"{mil(bf['cadunico_familias_pobreza'])} famílias em situação de pobreza no CadÚnico."
                    + (" Programas sociais são tema forte aqui." if sh > ref * 1.2 else ""))
    cg = cx.get("caged")
    if cg and not pd.isna(cg.get("variacao_relativa_pct")):
        refu = CTX.get("_caged_uf", {}).get(uf, np.nan)
        mais.append(f"**Emprego formal (Novo CAGED, set/2025 a ago/2026):** saldo de {mil(cg['saldo'])} vagas "
                    f"({f"{cg['variacao_relativa_pct']:+.1f}%".replace(".", ",")}"
                    f" do estoque; mediana das cidades de {uf}: {pct(refu)})."
                    + (" O emprego cresce mais rápido que no estado: dá para mostrar resultado." if cg["variacao_relativa_pct"] > refu + 1 else
                       " O emprego cresce mais devagar que no estado: o tema pede proposta, não balanço." if cg["variacao_relativa_pct"] < refu - 1 else ""))
    if m.get("rm") and m["rm"] in D["rms"]:
        vz = [x for x in D["rms"][m["rm"]]["mun"] if x in D["municipios"] and x != k]
        if vz:
            melhores = sorted(vz, key=lambda x: -G["potencial"][x][1])[:3]
            pos = 1 + sum(G["potencial"][x][1] > pot[1] for x in vz)
            mais.append(f"**Na {m['rm']}:** {nome} é a {pos}ª de {len(vz) + 1} cidades em votos a recuperar. "
                        + ("Outras cidades da RM com mais potencial: " if pos == 1 else "As que têm mais potencial: ") + ", ".join(f"{nome_cidade(D['municipios'][x]['n'])} "
                                                                     f"({mil(G['potencial'][x][1])}, nota {D['municipios'][x]['v']})"
                                                                     for x in melhores) + ".")
    largura = (pot[2] - pot[0]) / max(pot[1], 1)
    if pot[1] > 0:
        mais.append(f"**Firmeza da estimativa:** o intervalo provável dos votos a recuperar tem largura de "
                    f"{pct(100 * largura, 0)} do valor central"
                    + (": número firme." if largura < 0.25 else ": use como ordem de grandeza." if largura < 0.8 else
                       ": muito incerto, confirme com quem conhece a cidade."))
    if mais:
        w("## Mais achados: história, eleitorado e economia")
        w("")
        for a in mais:
            w(f"* {a}")
        w("")

    # ---------------------------------------------------------------- áreas
    if len(ok) >= 2:
        w("## Onde concentrar o esforço")
        w("")
        w("As áreas com mais votos a recuperar (as primeiras 10). A área é um bairro do IBGE ou, onde a cidade não tem "
          "bairros oficiais, o entorno de um grupo de escolas de votação.")
        w("")
        w("| Área | Nota | Votos a recuperar | Eleitores | Lula 2026 | Variação desde 2022 | Levar gente às urnas |")
        w("|---|---|---|---|---|---|---|")
        for _, r in ok.head(10).iterrows():
            efeito = "ajuda Lula" if r["pr"] >= 0.7 else ("ajuda Flávio" if r["pr"] <= 0.3 else "incerto")
            w(f"| {r['n']} | {int(r['nota'])} | {mil(r['pot50'])} | {mil(r['ap'])} | {pct(r['l26'])} | {pp(r['d'])} | {efeito} |")
        w("")
        quedas = sub[(sub["ap"] >= 3000) & sub["d"].notna()].sort_values("d").head(5)
        if len(quedas):
            w("**Onde Lula mais caiu desde 2022** (áreas com 3 mil eleitores ou mais): " +
              "; ".join(f"{r['n']} ({pp(r['d'])})" for _, r in quedas.iterrows()) + ".")
            w("")
        aj = sub[(sub["pr"] >= 0.7) & (sub["ap"] >= 3000)].sort_values("ap", ascending=False).head(5)
        if len(aj):
            w("**Onde vale levar gente às urnas** (a mobilização tende a favorecer Lula): " +
              "; ".join(f"{r['n']}" for _, r in aj.iterrows()) + ".")
            w("")

    # ---------------------------------------------------------------- temas
    C = D.get("citacoes", {})
    w("## Temas para conversar")
    w("")
    w("Sugestão a partir de dados (pesquisas nacionais, perfil das áreas no Censo e força das propostas nos planos de "
      "governo registrados no TSE). Não é pesquisa feita na cidade: teste e ajuste.")
    w("")
    nomes = lambda l, n=3: ", ".join(TEMA.get(x, x) for x, _ in l[:n]) or "–"
    w(f"* **Puxe estes temas (mais força para Lula aqui):** {nomes(t['a'])}.")
    w(f"* **Contraste (o plano de Flávio não trata, ou trata pouco):** {nomes(t['f'], 2)}.")
    w(f"* **Disputados (os dois lados falam; prepare a resposta):** {nomes(t['d'], 2)}.")
    w(f"* **Evite puxar:** {nomes(t['e'], 2)}.")
    w("")
    cit = []
    for x, _ in t["a"][:3]:
        c = CITA.get(("lula", x))
        if c:
            cit.append(f"* {TEMA.get(x, x)}: plano de Lula, p. {c[0]}: “{c[1]}”")
    for x, _ in t["f"][:2]:
        c = C.get(x)
        if c:
            fl = "não trata do tema" if c.get("flavio_omisso") or not c.get("flavio") else f"trata pouco (p. {c['flavio']['p']})"
            lu = f"; plano de Lula, p. {c['lula']['p']}" if c.get("lula") else ""
            cit.append(f"* {TEMA.get(x, x)}: plano de Flávio {fl}{lu}")
    if cit:
        w("Onde está escrito:")
        w("")
        L.extend(cit)
        w("")

    # ---------------------------------------------------------------- cuidados
    w("## Como ler")
    w("")
    w("* O mapa fala de **lugares, não de pessoas**: a média de uma área não descreve quem mora nela. As pessoas votam onde "
      "estão inscritas, que nem sempre é o bairro onde moram.")
    w("* **Não é previsão.** Os números mostram o que acontece se o comportamento de 2022 entre os turnos se repetir.")
    w("* \"Votos que dá para recuperar\" = votos que Lula perdeu aqui além da média do país, mais o ganho de levar mais "
      "gente às urnas onde isso tende a ajudá-lo.")
    w("* Nenhuma sugestão usa cor ou raça, gênero, religião ou orientação sexual.")
    w("")
    return "\n".join(L)


def main():
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--minimo", type=int, default=LIMIAR, help="só cidades com mais de N habitantes")
    a = ap.parse_args()
    D, A, pop = carregar()
    CITA.update(citacoes_planos())
    M = D["municipios"]
    # sem limite, entram todos (inclusive municípios criados depois do Censo 2022, sem população recenseada)
    cid = list(M) if a.minimo <= 0 else [k for k in M if pop.get(k, 0) >= a.minimo]
    G = D["grupos"]["municipio"]
    pot = pd.Series({k: G["potencial"][k][1] for k in cid})
    pmil = pd.Series({k: 1000 * G["potencial"][k][1] / M[k]["ap"] for k in cid})
    pts = pd.Series({k: porte(pop.get(k, 0)) for k in cid})
    ranks = {"pot": pot.rank(ascending=False, method="min").astype(int),
             "pot_mil": pmil.rank(ascending=False, method="min").astype(int),
             "pot_porte": pot.groupby(pts).rank(ascending=False, method="min").astype(int),
             "n_porte": pts.value_counts().to_dict()}
    CTX.update(contexto(cid))
    shs = pd.Series({k: 100 * CTX[k]["bf"]["pbf_familias_beneficiarias"] / CTX[k]["dom"] for k in cid
                     if CTX[k].get("bf") and CTX[k].get("dom")})
    CTX["_bf_mediana"] = shs.groupby(pts.reindex(shs.index)).median().to_dict()     # mediana por porte de cidade
    os.makedirs(OUT, exist_ok=True)
    idx = []
    for k in cid:
        m = M[k]
        texto = relatorio(k, m, D, A, pop, ranks, len(cid))
        rel = os.path.join(m["uf"], f"{arquivo(nome_cidade(m['n']))}_{k}.md")
        os.makedirs(os.path.join(OUT, m["uf"]), exist_ok=True)
        open(os.path.join(OUT, rel), "w").write(texto)
        idx.append((ranks["pot"][k], m["n"], m["uf"], m["v"], pot[k], pmil[k], rel))
    idx.sort()
    L = ["# Relatórios por cidade: 2º turno de 2026", "",
         "*Uso interno da Estel Tecnologia. Não publicar.* Um relatório para cada uma das "
         f"{mil(len(cid))} cidades do país, com os mesmos números do mapa. "
         f"Gerado em {date.today().strftime('%d/%m/%Y')} por `bairros/b15_relatorios_cidades.py`; "
         f"estados com estimativa menos segura: {', '.join(D['meta']['ufs_instaveis']) or 'nenhum'}.", "",
         "Ordem: votos que dá para recuperar (mediana).", "",
         "| # | Cidade | UF | Nota | Votos a recuperar | Por mil eleitores |", "|---|---|---|---|---|---|"]
    for r, n, uf, v, p, pm, rel in idx:
        L.append(f"| {r} | [{nome_cidade(n)}]({rel}) | {uf} | {v} | {mil(p)} | {pm:.1f} |".replace(f"{pm:.1f}", f"{pm:.1f}".replace(".", ",")))
    open(os.path.join(OUT, "LEIAME.md"), "w").write("\n".join(L) + "\n")
    print(f"{len(cid)} relatórios em {OUT}")


if __name__ == "__main__":
    main()
