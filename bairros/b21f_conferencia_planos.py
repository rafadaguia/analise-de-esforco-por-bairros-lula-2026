#!/usr/bin/env python3
"""Etapa B21f: rótulos finais de subtema dos planos, conferidos por dois modelos locais e leitura humana.

  * dois anotadores independentes: gemma4:31b (b21b) e qwen3:32b (b21b2), mesma instrução e mesma taxonomia;
  * rótulo que os dois marcam: vale;
  * divergência nos subtemas usados nas fichas: decisão após leitura do parágrafo (subtemas_conferencia_manual.json);
  * demais divergências: não vale (regra conservadora);
  * "concreto": o do gemma (os dois concordam em 86%).
Saídas: dados_bairros/proc/planos_subtemas_final.jsonl e bairros/insumos/temas/subtemas_planos.csv (via b21b)
"""
import json, os, sys
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(RAIZ, "dados_bairros", "proc")
TEMAS = os.path.join(RAIZ, "bairros", "insumos", "temas")


def main():
    g = {(x["cand"], x["id"]): x for x in map(json.loads, open(os.path.join(PROC, "planos_subtemas.jsonl")))}
    q = {(x["cand"], x["id"]): x for x in map(json.loads, open(os.path.join(PROC, "planos_subtemas_qwen3.jsonl")))}
    man = {(d["cand"], d["id"], d["subtema"]): d["trata"] for d in json.load(open(os.path.join(TEMAS, "subtemas_conferencia_manual.json")))}
    usados = {(c, i, s) for c, i, s in man}
    n = {"ambos": 0, "manual_sim": 0, "manual_nao": 0, "descartado": 0}
    with open(os.path.join(PROC, "planos_subtemas_final.jsonl"), "w") as out:
        for k, x in g.items():
            a, b = set(x["subtemas"]), set(q.get(k, {}).get("subtemas", []))
            final = a & b; n["ambos"] += len(final)
            for s in a ^ b:
                d = man.get((k[0], k[1], s))
                if d is True:
                    final.add(s); n["manual_sim"] += 1
                elif d is False:
                    n["manual_nao"] += 1
                else:
                    n["descartado"] += 1
            out.write(json.dumps({**x, "subtemas": sorted(final)}, ensure_ascii=False) + "\n")
    faltou = [k for k in usados if (k[0], k[1]) not in g]
    print(n, "| decisões sem parágrafo:", faltou)


if __name__ == "__main__":
    main()
