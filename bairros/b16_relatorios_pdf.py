#!/usr/bin/env python3
"""Etapa B16: converte os relatórios por cidade (resultados/*.md) em PDF com a identidade visual da Estel Tecnologia.

Duas versões, com a mesma organização por UF:
  padrão      Resultados_Doc/ (fora do git), rotulada como uso interno
  --publico   mapa/bairros/relatorios/ (vai para o site com o mapa), sem o rótulo de uso interno, com links relativos
              e indice.json (código IBGE -> arquivo) para o botão de download do mapa
Markdown -> HTML (python-markdown, com tabelas) -> PDF pelo Chrome sem interface (puppeteer-core, script em Node),
com fontes e logo locais, sem nenhum recurso externo.

Identidade: logo da Estel (mapa/lib/marca), azul #1863DC e azul-marinho #00378E do site estel.tec.br, texto #212121,
títulos em Archivo e texto em Instrument Sans (as mesmas fontes do mapa). Nota de 1 a 7 na escala do mapa (rosa a vermelho).
"""
import argparse, base64, glob, json, os, re, subprocess, sys
import markdown

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(RAIZ, "resultados")
OUT = os.path.join(RAIZ, "Resultados_Doc")
LIB = os.path.join(RAIZ, "mapa", "lib")
NOTAS = ["#fde7ea", "#fbc8cf", "#f6a2ae", "#ee7787", "#e24d5f", "#cc2a3c", "#a3101f"]
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PUPPETEER = os.environ.get("PUPPETEER_DIR", "")   # pasta com node_modules/puppeteer-core


def b64(p):
    return base64.b64encode(open(p, "rb").read()).decode()


def css():
    fontes = open(os.path.join(LIB, "fontes", "fontes.css")).read()
    fontes = re.sub(r"url\(([^)]+\.woff2)\)", lambda m: f"url(data:font/woff2;base64,{b64(os.path.join(LIB, 'fontes', m.group(1)))})", fontes)
    return fontes + """
@page { size: A4; margin: 22mm 16mm 20mm 16mm; }
:root { --azul: #1863DC; --marinho: #00378E; --tinta: #212121; --cinza: #5f6368; --linha: #dfe3ea; --fundo: #f4f6fa; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: "Instrument Sans", "Helvetica Neue", Arial, sans-serif; color: var(--tinta); font-size: 10pt; line-height: 1.45; margin: 0; }
.capa { display: flex; justify-content: space-between; align-items: center; border-bottom: 3px solid var(--azul); padding-bottom: 8px; margin-bottom: 14px; }
.capa img { height: 34px; }
.capa .rot { font-family: "Archivo", sans-serif; font-size: 8pt; letter-spacing: .08em; text-transform: uppercase; color: var(--marinho); text-align: right; }
h1 { font-family: "Archivo", sans-serif; font-weight: 800; font-stretch: 90%; font-size: 26pt; line-height: 1.05; margin: 0 0 6px; color: var(--marinho); }
h2 { font-family: "Archivo", sans-serif; font-weight: 700; font-size: 13pt; color: var(--marinho); margin: 18px 0 6px; padding-bottom: 3px; border-bottom: 1px solid var(--linha); break-after: avoid; }
p { margin: 4px 0 8px; }
ul { margin: 4px 0 8px; padding-left: 16px; }
li { margin: 3px 0; break-inside: avoid; }
li::marker { color: var(--azul); }
strong { color: #000; }
a { color: var(--azul); text-decoration: none; }
em { color: var(--cinza); }
blockquote { margin: 8px 0; padding: 8px 12px; background: #fff6e5; border-left: 4px solid #c27c00; color: #5a3d00; }
blockquote p { margin: 0; }
table { width: 100%; border-collapse: collapse; font-size: 8.4pt; margin: 6px 0 10px; break-inside: auto; }
thead th { background: var(--marinho); color: #fff; font-family: "Archivo", sans-serif; font-weight: 600; text-align: left; padding: 5px 6px; }
td { padding: 4px 6px; border-bottom: 1px solid var(--linha); vertical-align: top; }
tr { break-inside: avoid; }
tbody tr:nth-child(even) td { background: var(--fundo); }
.ficha { display: flex; gap: 10px; align-items: center; margin: 4px 0 10px; color: var(--cinza); font-size: 9pt; }
.nota { display: inline-flex; align-items: center; gap: 8px; font-family: "Archivo", sans-serif; font-weight: 700; color: var(--tinta); }
.nota .n { width: 30px; height: 30px; border-radius: 4px; display: inline-flex; align-items: center; justify-content: center; font-size: 15pt; }
.escala { display: inline-flex; gap: 2px; }
.escala i { display: inline-block; width: 14px; height: 6px; }
.indep { background: var(--tinta); color: #fff; font-size: 8pt; padding: 6px 10px; margin: 0 0 12px; }
.indep b { color: #fff; }
td.nt { text-align: center; font-weight: 700; }
"""


def nota_html(v):
    cor = NOTAS[v - 1]
    txt = "#fff" if v >= 5 else "#212121"
    esc = "".join(f'<i style="background:{c}"></i>' for c in NOTAS)
    return (f'<div class="nota"><span class="n" style="background:{cor};color:{txt}">{v}</span>'
            f'<span>Nota {v} de 7<br><span class="escala">{esc}</span></span></div>')


PUBLICO = False
SITE_PUBLICO = "https://rafadaguia.github.io/analise-de-esforco-por-bairros-lula-2026/"


def pagina(md_texto, logo):
    m = re.search(r"\*\*Nota da cidade: (\d) de 7\*\*", md_texto)
    corpo = markdown.markdown(md_texto, extensions=["tables", "sane_lists"])
    # a linha de rodapé interna vira faixa de independência; a nota ganha o selo de cor
    corpo = re.sub(r"<p><em>Relatório interno da Estel Tecnologia[^<]*</em></p>", "", corpo, count=1)
    if PUBLICO:
        corpo = re.sub(r"<p><em>Uso interno da Estel Tecnologia\. Não publicar\.</em>\s*", "<p>", corpo)
    if m:
        corpo = corpo.replace("</h1>", f"</h1>\n{nota_html(int(m.group(1)))}", 1)
    # coluna "Nota" das tabelas de áreas: célula colorida
    def cor_td_v(v):
        v = int(v); return f'<td class="nt" style="background:{NOTAS[v - 1]};color:{"#fff" if v >= 5 else "#212121"}">{v}</td>'
    corpo = re.sub(r"(?<=<tr>\n<td>)([^\n]*</td>\n)<td>([1-7])</td>", lambda mm: mm.group(1) + cor_td_v(mm.group(2)), corpo)   # áreas: 2ª coluna
    corpo = re.sub(r"(<td>[A-Z]{2}</td>\n)<td>([1-7])</td>", lambda mm: mm.group(1) + cor_td_v(mm.group(2)), corpo)          # índice: depois da UF
    titulo = re.search(r"<h1>(.*?)</h1>", corpo)
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>{titulo.group(1) if titulo else 'Relatório'}</title>
<style>{CSS}</style></head><body>
<div class="capa"><img src="data:image/png;base64,{logo}" alt="Estel Tecnologia"><div class="rot">Relatório por cidade<br>2º turno de 2026{'' if PUBLICO else ' · uso interno'}</div></div>
<div class="indep"><b>Produção independente e exclusiva da Estel Tecnologia.</b> Sem relação com a campanha oficial de Lula, com o PT ou com qualquer partido, federação, coligação ou candidatura.</div>
{corpo}
</body></html>"""


def rodape():
    marca = "Estel Tecnologia · estel.tec.br · " + ("produção independente, sem relação com a campanha oficial" if PUBLICO
                                                    else "uso interno, não publicar")
    return ('<div style="font-family:Arial,sans-serif;font-size:7pt;color:#5f6368;width:100%;padding:0 16mm;display:flex;'
            f'justify-content:space-between"><span>{marca}</span>'
            '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>')

NODE = r"""
const puppeteer = require('puppeteer-core');
const fs = require('fs');
(async () => {
  const lista = JSON.parse(fs.readFileSync(process.argv[2]));
  const br = await puppeteer.launch({ executablePath: process.argv[3], headless: 'new' });
  const p = await br.newPage();
  for (const [html, pdf] of lista) {
    await p.goto('file://' + html, { waitUntil: 'load' });
    await p.evaluate(() => document.fonts.ready);
    await p.pdf({ path: pdf, format: 'A4', printBackground: true, displayHeaderFooter: true,
      headerTemplate: '<span></span>', footerTemplate: process.argv[4],
      margin: { top: '16mm', bottom: '18mm', left: '16mm', right: '16mm' } });
  }
  await br.close();
  console.log('PDFs: ' + lista.length);
})();
"""


def main():
    global CSS, OUT, PUBLICO
    ap = argparse.ArgumentParser(); ap.add_argument("--publico", action="store_true"); a = ap.parse_args()
    PUBLICO = a.publico
    if PUBLICO:
        OUT = os.path.join(RAIZ, "mapa", "bairros", "relatorios")
    CSS = css()
    logo = b64(os.path.join(LIB, "marca", "estel-preto.png"))
    tmp = os.path.join(OUT, ".html")
    os.makedirs(tmp, exist_ok=True)
    lista = []
    arquivos = sorted(glob.glob(os.path.join(SRC, "*", "*.md"))) + [os.path.join(SRC, "LEIAME.md")]
    for md in arquivos:
        rel = os.path.relpath(md, SRC)
        texto = open(md).read()
        if rel == "LEIAME.md":
            # o índice aponta para os PDFs (caminho absoluto: o HTML intermediário fica em outra pasta)
            if PUBLICO:
                # endereço do site: um link relativo viraria caminho local da máquina dentro do PDF
                texto = re.sub(r"\]\(([A-Z]{2}/[^)]+)\.md\)", rf"]({SITE_PUBLICO}relatorios/\1.pdf)", texto)
            else:
                texto = re.sub(r"\]\(([A-Z]{2}/[^)]+)\.md\)", lambda mm: f"](file://{OUT}/{mm.group(1)}.pdf)".replace(" ", "%20"), texto)
            rel = "00_INDICE.md"
        html = os.path.join(tmp, rel.replace(os.sep, "__").replace(".md", ".html"))
        open(html, "w").write(pagina(texto, logo))
        pdf = os.path.join(OUT, rel.replace(".md", ".pdf"))
        os.makedirs(os.path.dirname(pdf), exist_ok=True)
        lista.append([html, pdf])
    js = os.path.join(tmp, "imprimir.js")
    open(js, "w").write(NODE)
    json.dump(lista, open(os.path.join(tmp, "lista.json"), "w"))
    env = dict(os.environ, NODE_PATH=os.path.join(PUPPETEER, "node_modules"))
    subprocess.run(["node", js, os.path.join(tmp, "lista.json"), CHROME, rodape()], check=True, env=env)
    if PUBLICO:
        idx = {re.search(r"_(\d{7})\.pdf$", p).group(1): os.path.relpath(p, OUT) for _, p in lista if re.search(r"_\d{7}\.pdf$", p)}
        json.dump(idx, open(os.path.join(OUT, "indice.json"), "w"), separators=(",", ":"))
    for f in glob.glob(os.path.join(tmp, "*")):
        os.remove(f)
    os.rmdir(tmp)


if __name__ == "__main__":
    if not PUPPETEER:
        sys.exit("defina PUPPETEER_DIR (pasta com node_modules/puppeteer-core)")
    main()
