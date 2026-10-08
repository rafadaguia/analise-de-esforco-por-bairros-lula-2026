#!/usr/bin/env python3
"""Etapa B8: índice de esforço por unidade e os 7 níveis (7 = menor esforço por voto, 1 = maior).

Componentes (cada um vira um posto percentual de 0 a 1 entre as unidades classificáveis; 1 = melhor):
  potencial   potencial (terreno perdido + saldo de +2 pp onde a mobilização rende) por mil eleitores,
              mediana do Monte Carlo. Mais votos a ganhar por eleitor abordado = menos esforço por voto.
  seguranca   probabilidade de a mobilização render votos líquidos a Lula (P(saldo > 0)).
              Onde mobilizar pode dar votos ao adversário, cada contato é mais arriscado.
  certeza     inverso da incerteza relativa do potencial: (p95 - p05) / mediana. Intervalo estreito = aposta mais segura.
  escala      eleitorado da unidade (log). Unidades maiores diluem o custo fixo de uma ação (ato, equipe, carro de som).

Esquemas de pesos:
  P1  iguais                      0,25 / 0,25 / 0,25 / 0,25
  P2  foco em potencial           0,55 / 0,15 / 0,15 / 0,15
  P3  foco em segurança           0,20 / 0,40 / 0,30 / 0,10

Níveis: setis do índice (cada nível com ~1/7 das unidades classificáveis). Unidades residuais
("não localizado") e com menos de 1.000 aptos não são classificadas.

Saídas em variantes/<U>/<M>/:
  esforco.parquet          componentes, índice e nível por esquema de pesos
  esforco_mudancas.csv     quantas unidades mudam de nível entre esquemas (matrizes de transição)
"""
import argparse, os, sys
import numpy as np
import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAR = os.path.join(RAIZ, "variantes")
PESOS = {"P1": (0.25, 0.25, 0.25, 0.25), "P2": (0.55, 0.15, 0.15, 0.15), "P3": (0.20, 0.40, 0.30, 0.10)}
COMP = ["potencial", "seguranca", "certeza", "escala"]


def posto(s):
    return s.rank(pct=True, method="average")


def classificar(u, pesos=PESOS):
    ok = (u["tipo"] != "residual") & (u["aptos"] >= 1000)
    c = pd.DataFrame(index=u.index)
    c["pot_mil"] = 1000 * u["pot_p50"] / u["aptos"]
    c["incerteza_rel"] = (u["pot_p95"] - u["pot_p05"]) / u["pot_p50"].clip(lower=1)
    r = pd.DataFrame(index=u.index)
    r["potencial"] = posto(c.loc[ok, "pot_mil"])
    r["seguranca"] = posto(u.loc[ok, "prob_mob_rende"])
    r["certeza"] = posto(-c.loc[ok, "incerteza_rel"])
    r["escala"] = posto(np.log(u.loc[ok, "aptos"]))
    out = pd.concat([c, r.add_prefix("r_")], axis=1)
    for nome, w in pesos.items():
        idx = sum(wi * r[k] for wi, k in zip(w, COMP))
        out[f"indice_{nome}"] = idx
        # setis: 7 = maior índice = menor esforço por voto
        out[f"nivel_{nome}"] = pd.qcut(idx.rank(method="first"), 7, labels=range(1, 8)).astype("Int64")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unidade", default="U1"); ap.add_argument("--metodo", default="MC")
    a = ap.parse_args()
    pasta = os.path.join(VAR, a.unidade, a.metodo)
    u = pd.read_parquet(os.path.join(pasta, "unidades_mc.parquet"))
    e = classificar(u)
    out = pd.concat([u[["id_unidade", "uf", "cd_mun_ibge", "municipio", "nome_rm", "frente", "tipo", "nome", "aptos",
                        "pot_p05", "pot_p50", "pot_p95", "prob_mob_rende"]], e], axis=1)
    out.to_parquet(os.path.join(pasta, "esforco.parquet"), index=False)
    linhas = []
    for a1, a2 in (("P1", "P2"), ("P1", "P3"), ("P2", "P3")):
        x, y = out[f"nivel_{a1}"], out[f"nivel_{a2}"]
        m = x.notna() & y.notna()
        linhas.append({"de": a1, "para": a2, "unidades": int(m.sum()), "mudam_de_nivel": int((x[m] != y[m]).sum()),
                       "mudam_2_ou_mais": int(((x[m] - y[m]).abs() >= 2).sum()),
                       "nivel7_em_comum": int(((x[m] == 7) & (y[m] == 7)).sum()), "nivel7_de": int((x[m] == 7).sum())})
    mud = pd.DataFrame(linhas)
    mud.to_csv(os.path.join(pasta, "esforco_mudancas.csv"), index=False)
    print(mud.to_string(index=False))
    for p in PESOS:
        t = out.groupby(f"nivel_{p}").agg(unidades=("id_unidade", "size"), aptos=("aptos", "sum"),
                                          potencial=("pot_p50", "sum"), pot_mil=("pot_mil", "median"))
        print(f"\n{p}:\n" + t.round(1).to_string())


if __name__ == "__main__":
    main()
