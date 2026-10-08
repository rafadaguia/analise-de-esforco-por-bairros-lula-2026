#!/usr/bin/env python3
"""Chamadas a modelos locais do Ollama (http://localhost:11434), para tarefas simples e repetitivas
da análise: extrair tabelas de texto de PDFs de pesquisas, resumir logs longos, padronizar nomes.

Nada sai da máquina. As respostas de modelo local são sempre conferidas por código (esquema,
somas, faixas de valores) antes de entrar na análise; o que não passa na conferência é descartado
e registrado, nunca corrigido "no olho".

Uso:
    from ollama_local import perguntar, perguntar_json
    perguntar_json("Extraia ... Responda em JSON", modelo="gemma4:31b")
    python bairros/ollama_local.py resumir logs/arquivo.log   # resumo curto de um log
"""
import json, sys, time, urllib.request

URL = "http://localhost:11434/api/generate"
PADRAO = "gemma4:31b"      # bom equilíbrio entre qualidade e velocidade nesta máquina
RAPIDO = "qwen2.5-coder:7b"


def perguntar(prompt, modelo=PADRAO, formato=None, temperatura=0.0, max_tokens=4096, tentativas=3, pensar=False, contexto=32768):
    # pensar=False desliga o modo de raciocínio (qwen3 e afins): rotular não precisa dele e fica muito mais rápido
    corpo = {"model": modelo, "prompt": prompt, "stream": False, "think": pensar,
             "options": {"temperature": temperatura, "num_predict": max_tokens, "seed": 20261005,
                         "num_ctx": contexto}}
    if formato:
        corpo["format"] = formato
    for t in range(tentativas):
        try:
            req = urllib.request.Request(URL, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=1800) as r:
                return json.load(r)["response"]
        except Exception:  # noqa: BLE001
            if t == tentativas - 1:
                raise
            time.sleep(5)


def perguntar_json(prompt, modelo=PADRAO, esquema="json", **kw):
    kw.setdefault("contexto", 32768)
    """Pede JSON (ou um JSON Schema em `esquema`) e devolve o objeto Python; None se não vier JSON válido."""
    txt = perguntar(prompt, modelo=modelo, formato=esquema, **kw)
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        return None


def resumir_log(caminho, modelo=RAPIDO, linhas=400):
    texto = "".join(open(caminho, errors="replace").readlines()[-linhas:])
    return perguntar("Resuma em até 8 linhas, em português, este log de execução. Diga se terminou, "
                     "se houve erro (copie a mensagem exata) e os números finais principais.\n\n" + texto,
                     modelo=modelo, max_tokens=400)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "resumir":
        print(resumir_log(sys.argv[2]))
