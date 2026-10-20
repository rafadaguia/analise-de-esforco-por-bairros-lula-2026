#!/usr/bin/env python3
"""Etapa B09c: citações conferidas do "Onde está escrito" (uma por tema e candidato).

Cada citação foi escolhida por leitura humana entre os trechos dos parágrafos classificados no tema (b21f) e é localizada
aqui pelo início da frase; o script copia a frase literal do parágrafo e confere a página no PDF oficial do plano (TSE).
Se a frase não for achada ou a página não bater, para com erro. Tema sem citação (None): o plano não traz compromisso
sobre o tema, ou o tema é de "evitar".

Saídas: bairros/insumos/temas/citacoes_conferidas.json; atualiza "lula"/"flavio" em variantes/<U>/temas_citacoes.json
"""
import json, os, re, sys
import pandas as pd
import pymupdf

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMAS = os.path.join(RAIZ, "bairros", "insumos", "temas")
PDF = {"lula": os.path.join(RAIZ, "Plano de governo", "proposta-pt.pdf"),
       "flavio": os.path.join(RAIZ, "Plano de governo", "proposta-pl.pdf")}
ESCOLHA = {   # tema: (início da frase no plano de Lula, início no plano de Flávio)
    "saude_sus": ("Retomamos o Farmácia Popular", "Vamos ampliar o acesso a exames preventivos"),
    "educacao": ("Seguiremos com as ações e políticas já pactuadas", "Vamos ampliar a oferta de creches"),
    "emprego": (None, "Para quem tem mais idade, vamos criar um contrato"),
    "jornada_6x1": ("Manteremos nossa ação junto ao Senado Federal", "Vamos também dar mais liberdade a quem trabalha"),
    "renda_salario_minimo": ("Reinstituímos a política de valorização do salário-mínimo", None),
    "custo_de_vida_inflacao_alimentos": ("Manteremos a inflação sob controle", "Vamos reduzir impostos sobre energia elétrica"),
    "seguranca_publica": ("Manteremos a estratégia de asfixia financeira", "Em parceria com os governos estaduais, vamos criar meio milhão"),
    "moradia_mcmv": ("O programa alcançou sua meta de contratar 2 milhões", "Vamos retomar o Casa Verde e Amarela"),
    "transporte_mobilidade": ("A atual carteira, entre retomada de obras", "Vamos investir R$ 900 bilhões"),
    "programas_sociais": ("Recriamos e expandimos o Bolsa Família", "Por isso, o compromisso é claro e vem em primeiro lugar"),
    "impostos_isencao_ir": ("Aprovamos a reforma tributária do consumo e isentamos", "Vamos promover a revisão e o redimensionamento"),
    "previdencia": ("Queremos construir mecanismos contributivos mais flexíveis", "Vamos investir em tecnologia e digitalizar os processos do INSS"),
    "agronegocio_meio_ambiente": ("No próximo mandato, continuaremos trabalhando para alcançar o desmatamento", "Vamos instituir a rastreabilidade completa"),
    "agricultura_familiar": ("Vamos continuar expandindo o Plano Safra da Agricultura Familiar", "E o pequeno produtor que não tem o título"),
    "costumes_religiao": (None, None),
    "corrupcao": ("Vamos dar sequência às medidas de controle e integridade", "Nas empresas públicas, essa proteção tem nome"),
    "instituicoes_stf_reeleicao": (None, "E propomos o fim da reeleição"),
    "endividamento_apostas": ("Em 2026, o Novo Desenrola Brasil", "Vamos proibir o uso dos recursos dos programas sociais"),
    "saneamento": ("Continuaremos, no próximo mandato, a perseguir o objetivo", "O governo do PT tentou desarticulá-lo por decreto"),
    "periferias_favelas": ("Com o Periferia Viva, voltamos a investir", "Vamos promover a urbanização de áreas degradadas"),
    "soberania_nacional": ("Garantiremos a soberania digital", "Vamos ampliar a capacidade de armazenamento das safras, para garantir"),
}
EMPREGO_LULA = r"(Nova Indústria Brasil|neoindustrializa|empregos? de qualidade)"
norm = lambda s: re.sub(r"\W+", "", s.lower())


def main():
    uni = sys.argv[1] if len(sys.argv) > 1 else "U4"
    pr = pd.read_csv(os.path.join(TEMAS, "propostas_paragrafos.csv"))
    pags = {c: [norm(p.get_text()) for p in pymupdf.open(f)] for c, f in PDF.items()}
    frases = {c: [] for c in PDF}
    for r in pr.itertuples():
        txt = " ".join(str(r.texto).split())
        for f in re.split(r"(?<=[.;!?])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕ])", txt):
            frases[r.cand].append((f, int(r.pagina)))
    out, erros = {}, []
    for t, (il, iff) in ESCOLHA.items():
        out[t] = {}
        for c, ini in (("lula", il), ("flavio", iff)):
            if c == "lula" and t == "emprego":
                achou = [(f, p) for f, p in frases[c] if re.search(EMPREGO_LULA, f) and re.search(r"\b(vamos|seguiremos|continuaremos|ampliaremos|manteremos)\b", f, re.I)]
            elif ini is None:
                out[t][c] = None; continue
            else:
                achou = [(f, p) for f, p in frases[c] if f.startswith(ini)]
            if not achou:
                erros.append((t, c, ini)); continue
            f, p0 = achou[0]
            alvo = norm(f)[:90]
            pg = [i + 1 for i, s in enumerate(pags[c]) if alvo in s]
            if not pg:   # frase que atravessa páginas: confere o começo
                pg = [i + 1 for i, s in enumerate(pags[c]) if norm(f)[:40] in s]
            if not pg:
                erros.append((t, c, "página não conferida: " + f[:60])); continue
            out[t][c] = {"p": pg[0], "t": f}
    if erros:
        print("ERROS:", erros); sys.exit(1)
    json.dump(out, open(os.path.join(TEMAS, "citacoes_conferidas.json"), "w"), ensure_ascii=False, indent=1)
    arq = os.path.join(RAIZ, "variantes", uni, "temas_citacoes.json")
    tc = json.load(open(arq))
    for t, v in out.items():
        if t in tc:
            tc[t]["lula"], tc[t]["flavio"] = v["lula"], v["flavio"]
    json.dump(tc, open(arq, "w"), ensure_ascii=False, indent=1)
    for t, v in out.items():
        for c in ("lula", "flavio"):
            x = v[c]; print(f"{t:34s} {c:6s} " + (f"p{x['p']}: {x['t'][:110]}" if x else "—"))


if __name__ == "__main__":
    main()
