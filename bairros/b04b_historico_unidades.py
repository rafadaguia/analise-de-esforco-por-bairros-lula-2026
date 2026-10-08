#!/usr/bin/env python3
"""Etapa B4b: leva as seções de 2010, 2014 e 2018 às mesmas unidades de 2022/2026.

Cada local de votação histórico, já geocodificado (b03, com as coordenadas de 2022 como reserva),
vai para a unidade do setor censitário onde cai (setor_unidade.parquet, gerado por b04).
Sem setor, mas com bairro IBGE pelo nome: a unidade desse bairro (seguindo as fusões de b04).
Sem nada: unidade residual do município.

As unidades são as de 2026: a série compara sempre o mesmo território.

Saída: variantes/<U>/secao_unidade_hist.parquet (mesmas colunas de secao_unidade.parquet)
"""
import argparse, os, sys
import numpy as np
import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "bairros"))
PROC = os.path.join(RAIZ, "dados_bairros", "proc")
VAR = os.path.join(RAIZ, "variantes")
from b04_unidades import rm_por_municipio  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unidade", default="U1"); ap.add_argument("--anos", nargs="*", type=int, default=[2018, 2014, 2010])
    a = ap.parse_args()
    pasta = os.path.join(VAR, a.unidade)
    su = pd.read_parquet(os.path.join(pasta, "setor_unidade.parquet"))
    lu = pd.read_parquet(os.path.join(pasta, "local_unidade.parquet"))
    fusao = dict(zip(lu["id_unidade_original"], lu["id_unidade"]))
    validas = set(lu.loc[lu["ano"] == 2026, "id_unidade"])
    rm = rm_por_municipio()
    partes, medidas = [], []
    for ano in a.anos:
        loc = pd.read_parquet(os.path.join(PROC, f"locais_geo_{ano}.parquet"))
        loc["id_local"] = f"{ano}-" + loc["uf"] + "-" + loc["cd_mun_tse"].astype(str) + "-" + loc["zona"].astype(str) + "-" + loc["nr_local"].astype(str)
        loc = loc.merge(su, on="CD_SETOR", how="left")
        sem = loc["id_unidade"].isna() & loc["CD_BAIRRO"].notna() & (loc["CD_BAIRRO"] != ".")
        loc.loc[sem, "id_unidade"] = ("B" + loc.loc[sem, "CD_BAIRRO"].astype(str)).map(lambda x: fusao.get(x, x))
        fora = loc["id_unidade"].isna() | ~loc["id_unidade"].isin(validas)
        mun1 = "M" + loc["cd_mun_ibge"].astype("Int64").astype(str)
        loc.loc[fora, "id_unidade"] = np.where(mun1[fora].isin(validas), mun1[fora], "R" + loc.loc[fora, "cd_mun_ibge"].astype("Int64").astype(str))
        s = pd.read_parquet(os.path.join(PROC, f"locais_secao_{ano}.parquet"), columns=["ano", "uf", "cd_mun_tse", "zona", "secao", "nr_local"])
        s["id_local"] = f"{ano}-" + s["uf"] + "-" + s["cd_mun_tse"].astype(str) + "-" + s["zona"].astype(str) + "-" + s["nr_local"].astype(str)
        s = s.merge(loc[["id_local", "id_unidade", "cd_mun_ibge", "status_geo"]], on="id_local", how="left").merge(rm, on="cd_mun_ibge", how="left")
        partes.append(s)
        e = loc.groupby("status_geo")["eleitores"].sum() / loc["eleitores"].sum() * 100
        medidas.append({"ano": ano, **{f"pct_{k}": round(v, 2) for k, v in e.items()},
                        "pct_em_unidade_sub": round(100 * loc.loc[loc["id_unidade"].str[0].isin(["B", "S", "D", "A", "P"]), "eleitores"].sum() / loc["eleitores"].sum(), 2)})
    pd.concat(partes).to_parquet(os.path.join(pasta, "secao_unidade_hist.parquet"), index=False)
    m = pd.DataFrame(medidas)
    m.to_csv(os.path.join(pasta, "historico_cobertura.csv"), index=False)
    print(m.to_string(index=False))


if __name__ == "__main__":
    main()
