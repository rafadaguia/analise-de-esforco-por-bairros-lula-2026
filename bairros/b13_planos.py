#!/usr/bin/env python3
"""Etapa B13: propostas dos planos de governo oficiais (TSE), por tema e público, com página e trecho literal.

1. Segmenta os PDFs oficiais ("Plano de governo/proposta-pt.pdf" e "proposta-pl.pdf") em parágrafos, com a página
   e o título de seção mais recente.
2. Classifica cada parágrafo com um modelo LOCAL (Ollama, qwen3:32b; nada sai da máquina): temas, públicos,
   se é compromisso concreto ("vamos", "criaremos"...) e um resumo curto. Conferências por código:
     - temas e públicos fora da lista fixa são descartados;
     - "meta numérica" não vem do modelo: é detectada por expressão regular no texto do parágrafo;
     - o trecho citado é sempre o texto literal do PDF (primeira frase do parágrafo), nunca o resumo do modelo.
   Checkpoint em dados_bairros/proc/planos_classificados.jsonl (retoma de onde parou).
3. Agrega por candidato e tema: nº de parágrafos, de compromissos concretos, de metas numéricas, páginas e a melhor
   citação (compromisso com meta, ou o mais longo).

Saídas: bairros/insumos/temas/propostas_paragrafos.csv, propostas_por_tema.csv
"""
import json, os, re, sys, unicodedata
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "bairros"))
from ollama_local import perguntar_json  # noqa: E402

PLANOS = {"lula": os.path.join(RAIZ, "Plano de governo", "proposta-pt.pdf"),
          "flavio": os.path.join(RAIZ, "Plano de governo", "proposta-pl.pdf")}
CACHE = os.path.join(RAIZ, "dados_bairros", "proc", "planos_classificados.jsonl")
OUT = os.path.join(RAIZ, "bairros", "insumos", "temas")
MODELO = "gemma4:31b"   # qwen3:32b devolvia a lista de temas vazia com o prompt completo (teste de 08/10)
TEMAS = ["emprego", "jornada_6x1", "renda_salario_minimo", "custo_de_vida_inflacao_alimentos", "saude_sus", "educacao",
         "seguranca_publica", "moradia_mcmv", "transporte_mobilidade", "programas_sociais", "impostos_isencao_ir",
         "previdencia", "agronegocio_meio_ambiente", "costumes_religiao", "corrupcao", "instituicoes_stf_reeleicao",
         "endividamento_apostas", "saneamento", "periferias_favelas", "agricultura_familiar", "soberania_nacional"]
DESCR_TEMAS = ("emprego (empregos, trabalho, qualificação profissional), jornada_6x1 (escala e jornada de trabalho), "
    "renda_salario_minimo, custo_de_vida_inflacao_alimentos (preços, energia, alimentos), saude_sus, educacao, seguranca_publica, "
    "moradia_mcmv, transporte_mobilidade (inclui infraestrutura de transporte), programas_sociais (Bolsa Família, assistência), "
    "impostos_isencao_ir (impostos e tributos), previdencia (INSS, aposentados), agronegocio_meio_ambiente, costumes_religiao "
    "(família, valores, religião), corrupcao, instituicoes_stf_reeleicao (STF, Judiciário, democracia, eleições), "
    "endividamento_apostas, saneamento, periferias_favelas, agricultura_familiar, soberania_nacional (soberania do país, "
    "tarifas e pressões de outros países, Petrobras e pré-sal, regulação de big techs, Pix)")
# evidência textual exigida para aceitar um tema ou público proposto pelo modelo (sem acento, minúsculas)
EVID_TEMA = {
    "emprego": r"empreg|trabalho|carteira|vaga", "jornada_6x1": r"6x1|6 x 1|jornada|escala de trabalho|horas semanais",
    "renda_salario_minimo": r"salario minimo|renda|salario", "custo_de_vida_inflacao_alimentos": r"custo de vida|inflac|preco|alimento|cesta|carestia|conta de luz|energia",
    "saude_sus": r"saude|\bsus\b|hospita|medic|consulta|remedio", "educacao": r"educac|escola|ensino|alfabetiz|creche|universidade|professor",
    "seguranca_publica": r"seguranca|crime|criminal|violencia|policia|faccao|presidio|homicid|bandid|arma|trafico",
    "moradia_mcmv": r"moradia|habitac|casa|minha casa|casa verde|aluguel|regulariz", "transporte_mobilidade": r"transporte|mobilidade|onibus|metro|trem|tarifa|rodovia|ferrovia",
    "programas_sociais": r"programas? socia|bolsa familia|transferencia de renda|cadastro unico|cadunico|beneficio",
    "impostos_isencao_ir": r"imposto|tribut|isenc|\birpf\b|iva|carga tributaria", "previdencia": r"previdenc|aposentad|\binss\b|pensao",
    "agronegocio_meio_ambiente": r"agro|rural|ambient|amazon|desmat|clima|floresta|bioma", "costumes_religiao": r"famili|religi|aborto|valores|igreja|fe\b|ideolog|doutrin",
    "corrupcao": r"corrup|desvio|transparen|integridade|estatais|fraude", "instituicoes_stf_reeleicao": r"\bstf\b|supremo|reeleic|monocrat|foro|judicia|democrac|eleic|censura",
    "endividamento_apostas": r"endivid|divida|apostas|bets|credito|juros", "saneamento": r"saneamento|esgoto|agua potavel|abastecimento de agua",
    "periferias_favelas": r"periferi|favela|comunidade|quebrada", "agricultura_familiar": r"agricultura familiar|pequeno produtor|assentament|pronaf",
    "soberania_nacional": r"soberan|tarifa|tarifaco|estados unidos|\beua\b|ingerencia|interferencia estrangeira|pre-sal|petrobras|defesa nacional|big tech|plataformas digitais|\bpix\b|autonomia nacional|independencia"}
EVID_PUB = {
    "jovens": r"jove|juventude", "idosos_aposentados": r"idos|aposentad|terceira idade", "trabalhadores_formais": r"trabalhador|carteira|clt|empregad",
    "trabalhadores_informais_aplicativo": r"aplicativo|plataforma|informal|entregador|motorista", "baixa_renda": r"baixa renda|pobre|vulnera|cadunico|bolsa",
    "classe_media": r"classe media|renda media|ate r\$ ?5|5 mil", "rural_agricultores": r"rural|campo|agricult|produtor", "periferia_urbana": r"periferi|favela|comunidade",
    "empreendedores": r"empreend|pequen[ao]s? empresa|mei\b|microempre", "estudantes": r"estudant|aluno|escola|universit", "mulheres": r"mulher|feminin|maes?\b",
    "populacao_negra": r"negr|racial|racismo|afro|quilombol", "pessoas_com_deficiencia": r"deficienc|\bpcd\b|acessib", "criancas_familias": r"crianc|famili|infancia|creche"}
PUBLICOS = ["jovens", "idosos_aposentados", "trabalhadores_formais", "trabalhadores_informais_aplicativo", "baixa_renda",
            "classe_media", "rural_agricultores", "periferia_urbana", "empreendedores", "estudantes", "mulheres",
            "populacao_negra", "pessoas_com_deficiencia", "criancas_familias"]
META = re.compile(r"\b\d[\d\.,]*\s*(mil\b|milh(ão|ões|oes|ao)|bilh(ão|ões|oes|ao)|%|por cento|reais|R\$)|R\$\s*\d|\b\d{2,}\s*(novas|novos|mil)\b", re.I)
ESQUEMA = {"type": "object", "properties": {
    "temas": {"type": "array", "items": {"type": "string", "enum": TEMAS}},
    "publicos": {"type": "array", "items": {"type": "string", "enum": PUBLICOS}},
    "compromisso_concreto": {"type": "boolean"},
    "resumo": {"type": "string"}}, "required": ["temas", "publicos", "compromisso_concreto", "resumo"]}


def sem_acento(s):
    return unicodedata.normalize("NFKD", str(s).lower()).encode("ascii", "ignore").decode()


def paragrafos(arq):
    import pymupdf
    d = pymupdf.open(arq)
    out, secao = [], ""
    for i, p in enumerate(d):
        if i < 3:   # capa e sumário
            continue
        linhas = [(b[2] - b[0], " ".join(b[4].split())) for b in p.get_text("blocks")]
        linhas = [(w, t) for w, t in linhas if t and not re.fullmatch(r"\d{1,3}", t) and "....." not in t]
        if not linhas:
            continue
        larg = max(w for w, _ in linhas)
        atual = []
        for w, t in linhas:
            curta = w < 0.80 * larg
            if curta and not re.search(r"[.;:!?]$", t) and not atual:
                secao = t           # título ou subtítulo
                continue
            atual.append(t)
            if curta and re.search(r"[.;:!?]$", t):
                txt = " ".join(atual)
                if len(txt) >= 140:
                    out.append({"pagina": i + 1, "secao": secao, "texto": txt})
                atual = []
        if atual and len(" ".join(atual)) >= 140:
            out.append({"pagina": i + 1, "secao": secao, "texto": " ".join(atual)})
    return out


def classificar(cand, k, par):
    prompt = (f"Trecho do plano de governo de {'Lula (PT)' if cand == 'lula' else 'Flávio Bolsonaro (PL)'} (eleição presidencial de 2026).\n"
              f"Seção: {par['secao']}\nTrecho: {par['texto']}\n\n"
              "Liste os TEMAS que o trecho trata (1 a 3), escolhendo nesta lista: " + DESCR_TEMAS + ".\n"
              "Liste os PÚBLICOS a quem a proposta se dirige explicitamente (0 a 3): " + ", ".join(PUBLICOS) + ".\n"
              "compromisso_concreto: true se o trecho promete uma ação concreta do governo (ex.: 'vamos criar', 'ampliaremos', "
              "'isentar'); false se é diagnóstico ou valor genérico. resumo: até 15 palavras.")
    r = perguntar_json(prompt, modelo=MODELO, esquema=ESQUEMA, max_tokens=300, contexto=4096) or {}
    alvo = sem_acento(par["secao"] + " " + par["texto"])
    temas = list(dict.fromkeys(t for t in r.get("temas", []) if t in TEMAS and re.search(EVID_TEMA[t], alvo)))[:3]
    pubs = list(dict.fromkeys(p for p in r.get("publicos", []) if p in PUBLICOS and re.search(EVID_PUB[p], alvo)))[:3]
    return {"cand": cand, "id": k, **par, "temas": temas, "publicos": pubs,
            "concreto": bool(r.get("compromisso_concreto")), "meta_numerica": bool(META.search(par["texto"])),
            "resumo_modelo": str(r.get("resumo", ""))[:200], "ok_modelo": bool(r)}


def main():
    feitos = {}
    if os.path.exists(CACHE):
        for l in open(CACHE):
            j = json.loads(l); feitos[(j["cand"], j["id"])] = j
    tarefas = []
    for cand, arq in PLANOS.items():
        for k, par in enumerate(paragrafos(arq)):
            if (cand, k) not in feitos:
                tarefas.append((cand, k, par))
    print(f"{len(feitos)} já classificados, {len(tarefas)} a classificar", flush=True)
    with open(CACHE, "a") as fc, ThreadPoolExecutor(4) as ex:
        for n, r in enumerate(ex.map(lambda t: classificar(*t), tarefas), 1):
            fc.write(json.dumps(r, ensure_ascii=False) + "\n"); fc.flush()
            feitos[(r["cand"], r["id"])] = r
            if n % 50 == 0:
                print(f"  {n}/{len(tarefas)}", flush=True)
    d = pd.DataFrame(feitos.values())
    os.makedirs(OUT, exist_ok=True)
    d.assign(temas=d["temas"].map(";".join), publicos=d["publicos"].map(";".join)).to_csv(
        os.path.join(OUT, "propostas_paragrafos.csv"), index=False)
    # agregação por candidato x tema
    e = d.explode("temas").dropna(subset=["temas"])
    linhas = []
    for (cand, tema), g in e.groupby(["cand", "temas"]):
        conc = g[g["concreto"]]
        best = (conc[conc["meta_numerica"]] if conc["meta_numerica"].any() else conc if len(conc) else g)
        best = best.loc[best["texto"].str.len().idxmax()]
        frase = re.split(r"(?<=[.!?])\s", best["texto"])[0][:320]
        pubs = pd.Series([p for l in g["publicos"] for p in l]).value_counts()
        linhas.append({"candidato": cand, "tema": tema, "paragrafos": len(g), "compromissos": len(conc),
                       "metas": int(conc["meta_numerica"].sum()), "paginas": ";".join(map(str, sorted(set(g["pagina"])))),
                       "publicos_principais": ";".join(pubs.index[:4]), "citacao_pagina": int(best["pagina"]),
                       "citacao": frase, "citacao_secao": best["secao"]})
    t = pd.DataFrame(linhas)
    t["forca"] = t["compromissos"] + 2 * t["metas"]
    t.to_csv(os.path.join(OUT, "propostas_por_tema.csv"), index=False)
    w = t.pivot_table(index="tema", columns="candidato", values=["compromissos", "metas"], fill_value=0)
    print(w.to_string())
    print(f"falhas do modelo: {(~d['ok_modelo']).sum()} de {len(d)}")


if __name__ == "__main__":
    main()
