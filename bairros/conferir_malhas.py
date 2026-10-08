#!/usr/bin/env python3
"""Confere as URLs de origem das malhas de bairros das prefeituras usadas na U3/U4.

Para cada malha usada (CAMADAS_U3 em b04_unidades.py), testa as URLs candidatas (registros da coleta de 07/10 e
URLs informadas à mão): baixa de novo e compara com o arquivo usado.
  idêntica        mesmo hash SHA-256
  mesmo conteúdo  hash diferente (servidor gera o arquivo na hora), mas mesmo nº de polígonos e mesmos nomes
  diferente       responde, mas o conteúdo não bate
  sem resposta    erro ou tempo esgotado
Um download por vez (sem paralelismo), com tempo máximo de 120 s e 80 MB por arquivo.

Saída: bairros/insumos/prefeituras/catalogo.csv
"""
import hashlib, io, json, os, re, sys, tempfile, unicodedata, urllib.request, zipfile
import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "bairros"))
from b04_unidades import CAMADAS_U3, ler_camada, PREF  # noqa: E402
CAND = os.environ.get("CANDIDATAS", "")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def baixar(u):
    import ssl, certifi, urllib.parse
    u = urllib.parse.quote(u, safe=":/?&=%#+,;@")          # acentos no caminho (ex.: Teresina)
    ctx = ssl.create_default_context(cafile=certifi.where())  # verificação ligada; só o pacote de certificados é mais novo
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (conferencia de fonte; Estel Tecnologia)"})
    with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
        return r.read(80 * 1024 * 1024)


def nomes(g):
    norm = lambda s: re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", str(s).lower()).encode("ascii", "ignore").decode())
    return len(g), frozenset(norm(x) for x in g["nome"])


def assinatura_arquivo(mun, rel, conteudo=None):
    """(nº de polígonos, nomes) de um arquivo local ou de bytes baixados, com o mesmo leitor de b04."""
    if conteudo is None:
        g, _ = ler_camada(mun, rel)
        return nomes(g)
    # formato do que veio: zip (pode trazer .shp, .geojson ou .kml dentro), kmz, GeoJSON/JSON ou KML
    if conteudo[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(conteudo))
        dentro = [n for n in z.namelist() if n.lower().endswith((".shp", ".geojson", ".json", ".kml"))]
        ext, rel_tmp = (".kmz", "x.kmz") if any(n.endswith("doc.kml") for n in z.namelist()) else (".zip", "x.zip")
    elif conteudo.lstrip()[:1] in (b"{", b"["):
        rel_tmp = "x.geojson"
    else:
        rel_tmp = "x.kml"
    with tempfile.TemporaryDirectory() as tmp:
        pasta = os.path.join(tmp, f"{mun}_x"); os.makedirs(pasta)
        open(os.path.join(pasta, rel_tmp), "wb").write(conteudo)
        import b04_unidades as b4
        antigo = b4.PREF; b4.PREF = tmp
        try:
            g, _ = b4.ler_camada(mun, rel_tmp)
        finally:
            b4.PREF = antigo
        return nomes(g)


def main():
    cand = json.load(open(CAND)) if CAND else {}
    linhas = []
    so = set(os.environ.get("SO", "").split()) if os.environ.get("SO") else None
    for mun, rel in CAMADAS_U3.items():
        if so and str(mun) not in so:
            continue
        pasta = [d for d in os.listdir(PREF) if d.startswith(str(mun))][0]
        local = os.path.join(PREF, pasta, rel)
        b_local = open(local, "rb").read()
        sig_local = assinatura_arquivo(mun, rel)
        res = {"cd_municipio_ibge": mun, "municipio": pasta.split("_", 1)[1].replace("_", " ").title(), "arquivo": rel,
               "sha256_local": sha(b_local)[:16], "poligonos": sig_local[0], "url_arquivo": "", "situacao": "sem URL candidata"}
        for u in cand.get(str(mun), []):
            try:
                b = baixar(u)
            except Exception as e:  # noqa: BLE001
                res.update(url_arquivo=u, situacao=f"sem resposta ({str(e)[:60]})"); continue
            if sha(b) == sha(b_local):
                res.update(url_arquivo=u, situacao="idêntica"); break
            try:
                sig = assinatura_arquivo(mun, rel, b)
            except Exception as e:  # noqa: BLE001
                res.update(url_arquivo=u, situacao=f"responde, ilegível ({str(e)[:50]})"); continue
            if sig == sig_local:
                res.update(url_arquivo=u, situacao="mesmo conteúdo"); break
            res.update(url_arquivo=u, situacao=f"diferente ({sig[0]} polígonos, {len(sig[1] & sig_local[1])} nomes em comum)")
        linhas.append(res)
        print(f"{res['municipio'][:24]:24s} {res['situacao'][:60]:60s} {res['url_arquivo'][:90]}", flush=True)
    os.makedirs(os.path.join(RAIZ, "bairros", "insumos", "prefeituras"), exist_ok=True)
    arq = os.path.join(RAIZ, "bairros", "insumos", "prefeituras", "catalogo.csv")
    novo = pd.DataFrame(linhas)
    if so and os.path.exists(arq):          # segunda rodada: substitui só as cidades conferidas de novo
        velho = pd.read_csv(arq)
        novo = pd.concat([velho[~velho["cd_municipio_ibge"].astype(str).isin(so)], novo]).sort_values("cd_municipio_ibge")
    novo.to_csv(arq, index=False)


if __name__ == "__main__":
    main()
