#!/usr/bin/env python3
"""Etapa B21a: propostas de subtemas por tema, feitas por modelo local (gemma4, via Ollama) a partir dos planos.

Para cada tema, junta os resumos dos parágrafos dos dois planos de governo classificados naquele tema (b13) e pede ao
modelo local de 3 a 7 subtemas que (1) apareçam nos planos e (2) façam sentido para a conversa de rua. A lista final é
curada à mão (bairros/insumos/temas/subtemas.json); esta etapa só gera as sugestões, com os parágrafos que as apoiam.

Saída: bairros/insumos/temas/subtemas_propostas.json
"""
import json, os, sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ollama_local import perguntar_json   # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMAS = os.path.join(RAIZ, "bairros", "insumos", "temas")


def main():
    pr = pd.read_csv(os.path.join(TEMAS, "propostas_paragrafos.csv"))
    pr = pr[pr["ok_modelo"].astype(str) == "True"]
    temas = sorted({t for ts in pr["temas"].dropna() for t in str(ts).split(";") if t})
    out = {}
    for t in temas:
        sub = pr[pr["temas"].fillna("").str.split(";").map(lambda x: t in x)]
        linhas = [f"[{r.cand} p.{r.pagina} #{r.id}] {str(r.resumo_modelo)[:220]}" for r in sub.itertuples()]
        if not linhas:
            continue
        prompt = (f"Você organiza propostas de planos de governo do 2º turno de 2026 (Lula e Flávio Bolsonaro). Tema: '{t}'.\n"
                  "Abaixo, resumos de parágrafos dos dois planos sobre este tema, com candidato, página e id.\n"
                  "Proponha de 3 a 7 SUBTEMAS concretos (o assunto específico que um eleitor reconhece, ex.: 'filas e atenção "
                  "básica', 'remédios e Farmácia Popular'), que apareçam nesses parágrafos. Para cada subtema, liste os ids "
                  "dos parágrafos que o tratam. Não invente subtema sem parágrafo.\n"
                  'Responda em JSON: {"subtemas": [{"chave": "snake_case", "nome": "nome curto", "descricao": "1 frase", '
                  '"ids": [int]}]}\n\n' + "\n".join(linhas[:120]))
        try:
            r = perguntar_json(prompt, max_tokens=2000) or {}
            out[t] = {"n_paragrafos": len(sub), "subtemas": r.get("subtemas", [])}
        except Exception as e:  # noqa: BLE001
            out[t] = {"erro": str(e)[:200]}
        print(t, len(sub), [s.get("nome") for s in out[t].get("subtemas", [])], flush=True)
        json.dump(out, open(os.path.join(TEMAS, "subtemas_propostas.json"), "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
