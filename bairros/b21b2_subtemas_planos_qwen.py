#!/usr/bin/env python3
"""Etapa B21b (segundo anotador, qwen3:32b, para conferência): classifica cada parágrafo dos planos de governo nos subtemas (taxonomia curada em subtemas.json).

Para cada parágrafo já classificado em temas (b13), o modelo local (gemma4, Ollama) escolhe entre os subtemas desses temas
quais o parágrafo trata, e se é um compromisso concreto. A resposta passa por conferência: só valem chaves da taxonomia e
dos temas do parágrafo. Retomável (cache por parágrafo).

Saídas: dados_bairros/proc/planos_subtemas_qwen3.jsonl (cache) e bairros/insumos/temas/subtemas_planos.csv
        (cand, subtema, n_paragrafos, n_concretos, forca, pagina e trecho literal de compromisso)
"""
import json, os, re, sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ollama_local import perguntar_json   # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMAS = os.path.join(RAIZ, "bairros", "insumos", "temas")
CACHE = os.path.join(RAIZ, "dados_bairros", "proc", "planos_subtemas_qwen3.jsonl")
COMPROMISSO = re.compile(r"\b(vamos|iremos|vai|ampliar|ampliaremos|criar|criaremos|garantir|garantiremos|implantar|expandir|"
                         r"fortalecer|reduzir|zerar|isentar|valorizar|construir|construiremos|meta|investir|universalizar)\b", re.I)


def main():
    tax = {t: v for t, v in json.load(open(os.path.join(TEMAS, "subtemas.json"))).items() if not t.startswith("_")}
    pr = pd.read_csv(os.path.join(TEMAS, "propostas_paragrafos.csv"))
    pr = pr[pr["ok_modelo"].astype(str) == "True"]
    feitos = {}
    if os.path.exists(CACHE):
        for l in open(CACHE):
            d = json.loads(l); feitos[(d["cand"], d["id"])] = d
    out = open(CACHE, "a")
    for r in pr.itertuples():
        if (r.cand, r.id) in feitos:
            continue
        temas = [t for t in str(r.temas).split(";") if t in tax]
        if not temas:
            continue
        opcoes = {s["chave"]: f"{t}: {s['nome']} ({s['descr']})" for t in temas for s in tax[t]}
        prompt = ("Classifique o parágrafo de um plano de governo (eleição presidencial de 2026) nos SUBTEMAS abaixo. Escolha "
                  "só os subtemas que o parágrafo trata de fato (pode ser nenhum). Marque 'concreto' se o parágrafo traz "
                  "compromisso, programa ou meta específica (não só diagnóstico ou valores).\n\nSUBTEMAS:\n"
                  + "\n".join(f"- {k}: {v}" for k, v in opcoes.items())
                  + f"\n\nPARÁGRAFO (página {r.pagina}):\n{str(r.texto)[:1800]}\n\n"
                  'Responda em JSON: {"subtemas": ["chave", ...], "concreto": true|false}')
        res = perguntar_json(prompt, modelo="qwen3:32b", max_tokens=200, contexto=4096) or {}
        subs = [s for s in res.get("subtemas", []) if s in opcoes] if isinstance(res.get("subtemas"), list) else []
        d = {"cand": r.cand, "id": int(r.id), "pagina": int(r.pagina), "subtemas": subs, "concreto": bool(res.get("concreto")),
             "temas": temas}
        out.write(json.dumps(d, ensure_ascii=False) + "\n"); out.flush()
        feitos[(r.cand, r.id)] = d
    out.close()
    # agregação por candidato e subtema, com trecho literal de compromisso
    linhas = []
    txt = {(r.cand, int(r.id)): str(r.texto) for r in pr.itertuples()}
    for (cand, pid), d in feitos.items():
        for s in d["subtemas"]:
            linhas.append({"cand": cand, "subtema": s, "id": pid, "pagina": d["pagina"], "concreto": d["concreto"]})
    df = pd.DataFrame(linhas)
    res = []
    for (cand, s), g in df.groupby(["cand", "subtema"]):
        trecho, pag, melhor = "", None, -1
        for x in g.itertuples():
            for f in re.split(r"(?<=[.;!?])\s+", txt[(cand, x.id)]):
                f = f.strip()
                if 60 <= len(f) <= 260 and COMPROMISSO.search(f) and not f.isupper():
                    nota = 2 * x.concreto + bool(re.search(r"\d", f))
                    if nota > melhor:
                        melhor, trecho, pag = nota, f, x.pagina
        res.append({"cand": cand, "subtema": s, "n_paragrafos": len(g), "n_concretos": int(g["concreto"].sum()),
                    "forca": len(g) + 2 * int(g["concreto"].sum()), "pagina": pag, "trecho": trecho})
    pd.DataFrame(res).to_csv(os.path.join(TEMAS, "subtemas_planos_qwen3.csv"), index=False)
    print(f"{len(feitos)} parágrafos | {len(res)} pares candidato-subtema -> subtemas_planos.csv")


if __name__ == "__main__":
    main()
