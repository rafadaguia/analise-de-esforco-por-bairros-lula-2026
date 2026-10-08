#!/usr/bin/env python3
"""Baixa as fontes brutas da análise por bairro (TSE e IBGE) para dados_bairros/.

Retoma downloads interrompidos (HTTP Range), tenta de novo com espera crescente e
limita a 4 conexões simultâneas por servidor, para não ser bloqueado.
Arquivos já completos (tamanho igual ao Content-Length) são pulados.

Uso:
    python bairros/baixar.py fase1          # o mínimo para a Fase 1
    python bairros/baixar.py historico      # série 1994-2018 (Fase 3)
    python bairros/baixar.py tudo
"""
import os, sys, time, threading, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(RAIZ, "dados_bairros")
TSE = "https://cdn.tse.jus.br/estatistica/sead/odsele"
GEO = ("https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/"
       "malhas_de_setores_censitarios__divisoes_intramunicipais/censo_2022")
CENSO = "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022"
UFS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB",
       "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"]
POR_HOST = 4
_sem = {}
_lock = threading.Lock()


def sem(url):
    h = urlparse(url).netloc
    with _lock:
        return _sem.setdefault(h, threading.Semaphore(POR_HOST))


def fase1():
    l = []
    # 2026: votação por seção (o _BR traz só presidente), detalhe da seção e locais de votação
    for p in ("votacao_secao/votacao_secao_2026_BR.zip", "detalhe_votacao_secao/detalhe_votacao_secao_2026.zip",
              "eleitorado_locais_votacao/eleitorado_local_votacao_2026.zip",
              # 2022: mesma estrutura, para ajustar as transferências entre turnos por bairro
              "votacao_secao/votacao_secao_2022_BR.zip", "detalhe_votacao_secao/detalhe_votacao_secao_2022.zip",
              "eleitorado_locais_votacao/eleitorado_local_votacao_2022.zip",
              "votacao_candidato_munzona/votacao_candidato_munzona_2026.zip",
              "detalhe_votacao_munzona/detalhe_votacao_munzona_2026.zip"):
        l.append((f"{TSE}/{p}", f"tse/{os.path.basename(p)}"))
    for n in ("bairros", "distritos", "subdistritos"):
        l.append((f"{GEO}/{n}/gpkg/BR/BR_{n}_CD2022.gpkg", f"ibge/BR_{n}_CD2022.gpkg"))
    l.append((f"{GEO}/setores/gpkg/BR/BR_setores_CD2022.gpkg", "ibge/BR_setores_CD2022.gpkg"))
    a = f"{CENSO}/Agregados_por_Setores_Censitarios"
    for t in ("alfabetizacao_BR", "basico_BR_20260520", "cor_ou_raca_BR", "demografia_BR",
              "caracteristicas_domicilio1_BR", "caracteristicas_domicilio2_BR_20250417"):
        l.append((f"{a}/Agregados_por_Setor_csv/Agregados_por_setores_{t}.zip", f"ibge/setores_{t}.zip"))
        l.append((f"{a}/Agregados_por_Bairro_csv/Agregados_por_bairros_{t}.zip", f"ibge/bairros_{t}.zip"))
    l.append((f"{a}/dicionario_de_dados_agregados_por_setores_censitarios_20260520.xlsx", "ibge/dicionario_agregados.xlsx"))
    r = f"{CENSO}/Agregados_por_Setores_Censitarios_Rendimento_do_Responsavel"
    for n in ("setores", "bairros"):
        l.append((f"{r}/Agregados_por_{n}_renda_responsavel_BR_20260508_csv.zip", f"ibge/{n}_renda_responsavel.zip"))
    l.append((f"{r}/dicionario_de_dados_renda_responsavel_20260508.xlsx", "ibge/dicionario_renda.xlsx"))
    l.append((f"{GEO}/tabelas_complementares/Populacao_residente_por_bairros_sexo_idade.xlsx",
              "ibge/pop_bairros_sexo_idade.xlsx"))
    return l


def historico():
    l = [(f"{TSE}/votacao_candidato_munzona/votacao_candidato_munzona_1994.zip", "tse/votacao_candidato_munzona_1994.zip")]
    for ano in (1998, 2002, 2006, 2010, 2014, 2018):
        l.append((f"{TSE}/votacao_secao/votacao_secao_{ano}_BR.zip", f"tse/votacao_secao_{ano}_BR.zip"))
        l.append((f"{TSE}/votacao_candidato_munzona/votacao_candidato_munzona_{ano}.zip",
                  f"tse/votacao_candidato_munzona_{ano}.zip"))
        l.append((f"{TSE}/detalhe_votacao_secao/detalhe_votacao_secao_{ano}.zip", f"tse/detalhe_votacao_secao_{ano}.zip"))
    for ano in (2018, 2020, 2024):
        l.append((f"{TSE}/eleitorado_locais_votacao/eleitorado_local_votacao_{ano}.zip",
                  f"tse/eleitorado_local_votacao_{ano}.zip"))
    return l


def tamanho_remoto(url):
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as r:
        if r.status != 200:
            raise IOError(f"HTTP {r.status}")
        return int(r.headers.get("Content-Length", -1))


def baixar(url, rel, tentativas=6):
    destino = os.path.join(DEST, rel)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with sem(url):
        for t in range(tentativas):
            try:
                total = tamanho_remoto(url)
                if os.path.exists(destino) and os.path.getsize(destino) == total:
                    return rel, "já tinha", total
                parcial = destino + ".parcial"
                ja = os.path.getsize(parcial) if os.path.exists(parcial) else 0
                req = urllib.request.Request(url, headers={"Range": f"bytes={ja}-"} if ja else {})
                with urllib.request.urlopen(req, timeout=120) as r, open(parcial, "ab" if ja and r.status == 206 else "wb") as f:
                    while True:
                        b = r.read(1 << 20)
                        if not b:
                            break
                        f.write(b)
                if os.path.getsize(parcial) != total:
                    raise IOError(f"tamanho {os.path.getsize(parcial)} != {total}")
                os.replace(parcial, destino)
                return rel, "ok", total
            except Exception as e:  # noqa: BLE001 — qualquer falha de rede vira nova tentativa
                # 416: o servidor recusa o Range do arquivo parcial; recomeça do zero
                if "416" in str(e) and os.path.exists(destino + ".parcial"):
                    os.remove(destino + ".parcial")
                if t == tentativas - 1:
                    return rel, f"FALHOU: {e}", 0
                time.sleep(5 * 2 ** t)


def main():
    alvo = sys.argv[1] if len(sys.argv) > 1 else "fase1"
    lista = {"fase1": fase1, "historico": historico, "tudo": lambda: fase1() + historico()}[alvo]()
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = [ex.submit(baixar, u, r) for u, r in lista]
        for f in as_completed(futs):
            rel, st, n = f.result()
            print(f"{st:10s} {n/1e6:9.1f} MB  {rel}", flush=True)
    print("FIM", alvo)


if __name__ == "__main__":
    main()
