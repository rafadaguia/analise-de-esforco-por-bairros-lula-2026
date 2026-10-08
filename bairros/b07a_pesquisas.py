#!/usr/bin/env python3
"""Etapa B7a: cruzamentos das pesquisas de 2º turno (Lula x Flávio), extraídos dos relatórios dos institutos.

Extração determinística por coordenadas, sem modelo de linguagem:
  * PDFs com texto (Datafolha): palavras e posições pelo PyMuPDF;
  * PDFs com tabelas em imagem (AtlasIntel): OCR local do macOS (Apple Vision, via ocrmac),
    que também devolve as posições.
As colunas são achadas pela posição dos números na linha de Lula; cada cabeçalho vai para a
coluna mais próxima. Conferência: em cada coluna, Lula + Flávio + branco/nulo + indecisos tem de
somar 100 ± 3 (arredondamento). Coluna que não passa é descartada e registrada, nunca corrigida.

Saídas: bairros/insumos/pesquisas/cruzamentos.csv, pesquisas.csv, extracao_log.csv
"""
import glob, io, os, re, sys
import numpy as np
import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDFS = os.path.join(RAIZ, "dados_bairros", "outros", "pesquisas")
OUT = os.path.join(RAIZ, "bairros", "insumos", "pesquisas")
NUM = re.compile(r"^(\d{1,5}([.,]\d{1,2})?%?|–|-|\*)$")

# vocabulário para harmonizar categorias (variavel, categoria_padrao)
def padronizar(grupo, cat):
    g, c = (grupo or "").lower(), cat.lower().replace("\n", " ").strip()
    c2 = re.sub(r"\s+", " ", c)
    if c2 in ("total",):
        return "total", "total"
    if "masc" in c2 or c2 == "homem" or c2 == "homens":
        return "sexo", "masculino"
    if "femin" in c2 or c2.startswith("mulher"):
        return "sexo", "feminino"
    if re.search(r"^r\$|acima de r\$", c2):           # renda em reais (AtlasIntel)
        n = [x.replace(",", "").replace(".", "") for x in re.findall(r"\d[\d.,]*", c2)]
        return "renda_reais", ("acima_" + n[0]) if "acima" in c2 else "_".join(n[:2])
    if "fundamental e m" in c2:
        return "escolaridade", "fundamental_medio"
    if re.search(r"60\s*-\s*100", c2):
        return "idade", "60+"
    if re.search(r"^\d+\s*(a|-)\s*\d+\s*(anos)?$", c2):
        a, b = re.findall(r"\d+", c2)[:2]
        return "idade", f"{a}-{b}"
    if re.search(r"60\s*(ou|\+|anos ou)", c2) or c2 in ("60+", "60 anos ou mais"):
        return "idade", "60+"
    if "fundam" in c2:
        return "escolaridade", "fundamental"
    if "médio" in c2 or "medio" in c2:
        return "escolaridade", "medio"
    if "superior" in c2 or "supe- rior" in c2 or c2 == "supe-rior":
        return "escolaridade", "superior"
    if "s.m" in c2 or "salário" in c2 or "salario" in c2 or "renda" in g:
        n = re.findall(r"\d+", c2)
        if "até" in c2 or "ate " in c2:
            return "renda", f"ate_{n[0]}sm" if n else c2
        if len(n) >= 2:
            return "renda", f"{n[0]}_{n[1]}sm"
        if n:
            return "renda", f"mais_{n[0]}sm"
    if c2 in ("branca", "branco", "brancos"):
        return "cor_raca", "branca"
    if c2 in ("preta", "preto", "pretos"):
        return "cor_raca", "preta"
    if c2 in ("parda", "pardo", "pardos"):
        return "cor_raca", "parda"
    if "catól" in c2 or "catol" in c2:
        return "religiao", "catolica"
    if "evang" in c2:
        return "religiao", "evangelica"
    if "sem religi" in c2 or "ateu" in c2 or "nenhuma" == c2:
        return "religiao", "sem_religiao"
    if "oeste/" in c2 or "oeste / norte" in c2:
        return "regiao", "CO_N"
    for k, v in (("sudeste", "SE"), ("nordeste", "NE"), ("sul", "S"), ("centro-oeste", "CO_N"), ("norte", "N")):
        if c2.startswith(k):
            return "regiao", v
    if "metropol" in c2:
        return "porte", "regiao_metropolitana"
    if "interior" in c2:
        return "porte", "interior"
    if c2 in ("pea", "não pea", "nao pea"):
        return "ocupacao", c2.replace("ã", "a")
    if "partido" in g or c2 in ("pt", "pl", "outro partido", "nenhum/ não tem", "nenhum/não tem"):
        return "partido", c2
    return "outro", c2


ROTULOS = {"lula": r"^Lula", "flavio": r"^Fl[aá]vio", "bn": r"^(Em branco|Branco|Nulo|Branco/nulo)", "nsnr": r"^(Indecis|Não sabe|NS/NR|Não sabe/)",
           "base": r"^Base"}


def palavras_pdf(pagina):
    return [(w[0], w[1], w[2], w[3], w[4]) for w in pagina.get_text("words")]


def palavras_ocr(pagina, zoom=3):
    """OCR de uma página (Apple Vision). Coordenadas convertidas para o mesmo sistema do PDF."""
    from ocrmac import ocrmac
    import pymupdf
    from PIL import Image
    pix = pagina.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    W, H = pagina.rect.width, pagina.rect.height
    out = []
    for txt, conf, (x, y, w, h) in ocrmac.OCR(img, language_preference=["pt-BR"], recognition_level="accurate").recognize():
        # bbox normalizada com origem embaixo à esquerda; cada pedaço pode ter várias palavras
        x0, y1 = x*W, (1 - y)*H
        x1, y0 = (x + w)*W, (1 - y - h)*H
        partes = txt.split()
        if len(partes) > 1 and all(NUM.match(p) for p in partes):   # "48 44 51" num só bloco: divide
            step = (x1 - x0)/len(partes)
            out += [(x0 + i*step, y0, x0 + (i + 1)*step, y1, p) for i, p in enumerate(partes)]
        else:
            out.append((x0, y0, x1, y1, txt))
    return out


def linhas(ws, tol=3.0):
    """Agrupa palavras em linhas pela altura (centro vertical)."""
    out = []
    for w in sorted(ws, key=lambda w: ((w[1] + w[3])/2, w[0])):
        yc = (w[1] + w[3])/2
        if out and abs(out[-1][0] - yc) < tol:
            out[-1][1].append(w)
        else:
            out.append([yc, [w]])
    return [(yc, sorted(l, key=lambda w: w[0])) for yc, l in out]


def linha_de(ws, padrao, ymin, ymax):
    """Rótulo de linha que casa com `padrao` (primeira ocorrência entre ymin e ymax).
    Devolve uma pseudo-palavra com a caixa do rótulo (só a parte de texto, sem os números)."""
    for yc, l in linhas([w for w in ws if ymin <= w[1] < ymax]):
        rot = []
        for w in l:
            if NUM.match(w[4]) and rot:
                break
            rot.append(w)
        texto = " ".join(w[4] for w in rot)
        if rot and re.match(padrao, texto):
            return (rot[0][0], min(w[1] for w in rot), rot[-1][2], max(w[3] for w in rot), texto)
    return None


def valor(t):
    return 0.0 if t in ("–", "-", "*") else float(t.rstrip("%").replace(",", "."))


def valores_da_linha(ws, rot, tol=14):
    """Números da linha do rótulo: a linha (por altura) mais próxima do rótulo com ao menos 2 números
    à direita dele. No Datafolha é a mesma linha; na AtlasIntel os valores ficam alguns pontos abaixo."""
    if rot is None:
        return []
    y = (rot[1] + rot[3])/2
    melhor = []
    for yc, l in linhas([w for w in ws if abs((w[1] + w[3])/2 - y) <= tol]):
        nums = [w for w in l if NUM.match(w[4]) and w[0] > rot[0] + 20]
        if len(nums) >= 2 and (not melhor or abs(yc - y) < melhor[0]):
            melhor = [abs(yc - y), nums]
    return sorted(melhor[1], key=lambda w: w[0]) if melhor else []


def extrair_bloco(ws, ymin, ymax):
    rot = {k: linha_de(ws, pad, ymin, ymax) for k, pad in ROTULOS.items()}
    if rot["lula"] is None or rot["flavio"] is None:
        return None
    vl = valores_da_linha(ws, rot["lula"])
    if len(vl) < 2:
        return None
    cx = np.array([(w[0] + w[2])/2 for w in vl])
    y_dados = min(r[1] for k, r in rot.items() if r is not None and k != "base")
    # cabeçalho: até 75 pt acima da primeira linha de dados; a linha mais alta traz os grupos
    ls = [l for yc, l in linhas([w for w in ws if max(ymin, y_dados - 75) <= w[1] < y_dados - 1])
          if not l[0][4].startswith(("Bloco", "Base:", "Se o", "Valores", "Em um", "candidatos"))]
    grp = ls[0] if len(ls) > 1 else []
    cab = [w for l in (ls[1:] if len(ls) > 1 else ls) for w in l if w[4] != "%"]
    nomes = [[] for _ in cx]
    for w in sorted(cab, key=lambda w: (round(w[1]), w[0])):
        j = int(np.argmin(np.abs(cx - (w[0] + w[2])/2)))
        nomes[j].append(w[4])
    cats = [" ".join(n).replace("- ", "") for n in nomes]
    cats = [c if c else ("Total" if j == 0 else "") for j, c in enumerate(cats)]
    gl = sorted(grp, key=lambda w: w[0])
    grupos = [([w for w in gl if w[0] <= c + 5] or [("", "", "", "", "")])[-1][4] for c in cx]
    tab = {}
    for k in ROTULOS:
        arr = np.full(len(cx), np.nan)
        for w in valores_da_linha(ws, rot[k]):
            j = int(np.argmin(np.abs(cx - (w[0] + w[2])/2)))
            if np.isnan(arr[j]) and abs(cx[j] - (w[0] + w[2])/2) < 25:
                arr[j] = valor(w[4])
        tab[k] = arr
    df = pd.DataFrame({"grupo": grupos, "categoria": cats, "pct_lula": tab["lula"], "pct_flavio": tab["flavio"],
                       "pct_branco_nulo": tab["bn"], "pct_nsnr": tab["nsnr"], "base_ponderada": tab["base"]})
    fim = max(r[3] for r in rot.values() if r is not None) + 12
    return df, fim


def extrair_pagina(ws):
    """Blocos em sequência: cada um vai da linha seguinte ao fim do anterior até a última linha de dados."""
    H = max((w[3] for w in ws), default=0) + 1
    out, ymin = [], 0
    while ymin < H:
        r = extrair_bloco(ws, ymin, H)
        if r is None:
            break
        df, fim = r
        out.append(df)
        ymin = fim
    return out


def processar(arq, meta):
    import pymupdf
    d = pymupdf.open(arq)
    blocos, log = [], []
    for i, pg in enumerate(d):
        txt = pg.get_text()
        usa_ocr = len(re.findall(r"\b\d{1,3}([.,]\d)?\b", txt)) < 15
        if not (re.search(r"(segundo|2º|2o)\s*turno", txt, re.I) and re.search(r"Fl[aá]vio", txt)) and not usa_ocr:
            continue
        if usa_ocr and not (re.search(r"(segundo|2º|2o)\s*turno", txt, re.I) or len(txt) < 50):
            continue  # página da AtlasIntel com título que não é de 2º turno: nem faz OCR
        ws = palavras_ocr(pg) if usa_ocr else palavras_pdf(pg)
        texto = " ".join(w[4] for w in ws)
        if not (re.search(r"(segundo|2º|2o)\s*turno", texto, re.I) and re.search(r"Fl[aá]vio", texto)
                and re.search(r"Lula", texto)) or re.search(r"S[ée]rie Temporal", texto):
            continue
        # cenário de 2º turno com outro adversário (ex.: Lula x Tarcísio) fica de fora
        for b in extrair_pagina(ws):
            if b["pct_flavio"].isna().all():
                continue
            soma = b[["pct_lula", "pct_flavio", "pct_branco_nulo", "pct_nsnr"]].sum(axis=1, min_count=2)
            b["soma"] = soma
            b["ok"] = (soma - 100).abs() <= 3
            b["pagina"] = i + 1
            b["ocr"] = usa_ocr
            blocos.append(b)
            log.append({"arquivo": os.path.basename(arq), "pagina": i + 1, "ocr": usa_ocr, "colunas": len(b),
                        "colunas_ok": int(b["ok"].sum())})
    if not blocos:
        return None, log
    t = pd.concat(blocos, ignore_index=True)
    for k, v in meta.items():
        t[k] = v
    return t, log


def meta_de(arq):
    """Metadados da pesquisa, lidos da capa/rodapé do relatório (registro TSE, campo, amostra, margem)."""
    import pymupdf
    d = pymupdf.open(arq)
    capa = " ".join(p.get_text() for p in list(d)[:3])
    if len(capa) < 300:  # relatório em imagem: OCR da capa e da página de metodologia
        capa = " ".join(" ".join(w[4] for w in palavras_ocr(p)) for p in list(d)[:3])
    nome = os.path.basename(arq)
    inst = "AtlasIntel" if "atlas" in nome else "Datafolha"
    uf = None
    m = re.search(r"eleicoes_([a-z_]+?)_(2026_)?_?261003", nome)
    if m:
        uf = m.group(1).replace("_", " ").strip()
    reg = re.search(r"(BR|[A-Z]{2})-\d{5}/2026", capa)
    amostra = re.search(r"(\d[\d\.]{2,6})\s*(entrevistas|eleitores|respondentes|questionários)", capa)
    margem = re.search(r"(margem de erro|erro)[^\d]{0,40}(\d+(?:[,\.]\d)?)\s*(p\.?p|ponto)", capa, re.I)
    campo = re.search(r"(\d{1,2}(?:º)?\s*(?:a|e)\s*\d{1,2}(?:º)?\s*de\s*[a-zç]+\s*(?:de\s*)?2026)", capa, re.I)
    return {"instituto": inst, "abrangencia_uf": uf, "registro_tse": reg.group(0) if reg else None,
            "amostra": amostra.group(1).replace(".", "") if amostra else None,
            "margem_erro_pp": margem.group(2).replace(",", ".") if margem else None,
            "campo": campo.group(1) if campo else None, "arquivo": nome}


def main():
    os.makedirs(OUT, exist_ok=True)
    tabs, logs, metas = [], [], []
    links = {}
    for lf in glob.glob(os.path.join(PDFS, "*_links.txt")):
        for u in open(lf).read().split():
            links[os.path.basename(u)] = u
    acesso = open(os.path.join(PDFS, "data_acesso.txt")).read().strip() if os.path.exists(os.path.join(PDFS, "data_acesso.txt")) else ""
    for arq in sorted(glob.glob(os.path.join(PDFS, "*.pdf"))):
        meta = meta_de(arq)
        meta["url"] = links.get(os.path.basename(arq))
        meta["data_acesso"] = acesso
        t, lg = processar(arq, meta)
        logs += lg
        metas.append(meta)
        if t is not None:
            tabs.append(t)
        print(f"{meta['instituto']:10s} {str(meta['abrangencia_uf'] or 'BR'):22s} reg {meta['registro_tse']} | "
              f"blocos {len(lg)} | colunas ok {sum(l['colunas_ok'] for l in lg)}/{sum(l['colunas'] for l in lg)}", flush=True)
    c = pd.concat(tabs, ignore_index=True)
    pad = [padronizar(g, k) for g, k in zip(c["grupo"], c["categoria"])]
    c["variavel"], c["categoria_padrao"] = [p[0] for p in pad], [p[1] for p in pad]
    c.to_csv(os.path.join(OUT, "cruzamentos_brutos.csv"), index=False)
    c[c["ok"]].to_csv(os.path.join(OUT, "cruzamentos.csv"), index=False)
    pd.DataFrame(metas).to_csv(os.path.join(OUT, "pesquisas.csv"), index=False)
    pd.DataFrame(logs).to_csv(os.path.join(OUT, "extracao_log.csv"), index=False)
    print(f"{len(c)} colunas extraídas, {int(c['ok'].sum())} passaram na conferência de soma")


if __name__ == "__main__":
    main()
