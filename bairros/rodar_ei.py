#!/usr/bin/env python3
"""Orquestra os ajustes de b05 por UF em paralelo (4 UFs x 4 cadeias = 16 núcleos), maiores primeiro.

Uso: python bairros/rodar_ei.py U1 [--validacao] [--paralelo 4]
Cada UF grava seu checkpoint; rodar de novo retoma de onde parou.
"""
import argparse, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ordem aproximada pelo nº de municípios/unidades (os maiores primeiro, para não sobrar um gigante no fim)
UFS = ["MG", "SP", "RS", "BA", "PR", "SC", "GO", "PI", "PB", "MA", "PE", "CE", "RN", "PA", "TO", "MT", "RJ",
       "AL", "SE", "ES", "MS", "AM", "RO", "AC", "AP", "RR", "DF"]

def rodar(uni, uf, val, metodo, extra=()):
    os.makedirs(os.path.join(RAIZ, "logs"), exist_ok=True)
    log = os.path.join(RAIZ, "logs", f"ei_{uni}_{metodo}_{uf}{'_val' if val else ''}.log")
    cmd = [sys.executable, os.path.join(RAIZ, "bairros", "b05_ei_bairros.py"), "--unidade", uni, "--metodo", metodo, "--ufs", uf]
    if val:
        cmd.append("--validacao")
    cmd += list(extra)
    env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
    with open(log, "w") as f:
        r = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env=env)
    return uf, r.returncode

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("unidade"); ap.add_argument("--validacao", action="store_true")
    ap.add_argument("--paralelo", type=int, default=4); ap.add_argument("--metodo", default="MC")
    ap.add_argument("--ufs", nargs="*"); ap.add_argument("--extra", nargs="*", default=[])
    a, resto = ap.parse_known_args()      # opções desconhecidas (--longo, --rapido, --ano X) vão para b05
    a.extra = list(a.extra) + resto
    ufs = [u for u in UFS if not a.ufs or u in a.ufs]
    with ThreadPoolExecutor(a.paralelo) as ex:
        for f in as_completed([ex.submit(rodar, a.unidade, u, a.validacao, a.metodo, a.extra) for u in ufs]):
            print(*f.result(), flush=True)
    print("FIM")
