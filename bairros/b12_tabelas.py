#!/usr/bin/env python3
"""Entrega 3: tabelas por nível geográfico (CSV e Parquet) da variante escolhida.

  areas      uma linha por área: perfil, voto, potencial e intervalos, níveis P1-P3, MRP, temas
  municipio, rm, uf, frente, pais: somas do Monte Carlo por sorteio (mediana e intervalo de 90%)
Uso: python bairros/b12_tabelas.py --unidade U1 --metodo MC
"""
import argparse, os
import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--unidade", default="U1"); ap.add_argument("--metodo", default="MC")
    a = ap.parse_args()
    V = os.path.join(RAIZ, "variantes", a.unidade); P = os.path.join(V, a.metodo); out = os.path.join(P, "tabelas")
    os.makedirs(out, exist_ok=True)
    mc = pd.read_parquet(os.path.join(P, "unidades_mc.parquet"))
    es = pd.read_parquet(os.path.join(P, "esforco.parquet"))
    un = pd.read_parquet(os.path.join(V, "unidades.parquet"))
    perfil = un[["id_unidade", "pop", "pop_15m", "branca", "preta", "parda", "alfabetizados_15m", "renda_resp_soma", "resp_com_renda"]].copy()
    perfil["renda_media_responsavel"] = perfil["renda_resp_soma"] / perfil["resp_com_renda"]
    perfil["pct_alfabetizados_15m"] = 100 * perfil["alfabetizados_15m"] / perfil["pop_15m"]
    for c in ("branca", "preta", "parda"):
        perfil[f"pct_{c}"] = 100 * perfil[c] / perfil[["branca", "preta", "parda"]].sum(axis=1)
    perfil = perfil[["id_unidade", "pop", "pop_15m", "renda_media_responsavel", "pct_alfabetizados_15m", "pct_branca", "pct_preta", "pct_parda"]]
    t = mc.merge(es[["id_unidade", "pot_mil", "incerteza_rel", "indice_P1", "nivel_P1", "indice_P2", "nivel_P2", "indice_P3", "nivel_P3"]], on="id_unidade") \
          .merge(perfil, on="id_unidade", how="left")
    mrp = os.path.join(V, "mrp.parquet")
    if os.path.exists(mrp):
        t = t.merge(pd.read_parquet(mrp)[["id_unidade"] + [f"R{i}_{q}" for i in (1, 2, 3) for q in ("p05", "p50", "p95")]], on="id_unidade", how="left")
    tm = os.path.join(V, "temas_unidades.parquet")
    if os.path.exists(tm):
        t = t.merge(pd.read_parquet(tm)[["id_unidade", "temas_aderentes_lula", "temas_flavio_mais_fraco", "temas_disputados", "temas_evitar", "rotulo"]], on="id_unidade", how="left")
    t["aviso"] = "dados agregados por local de votação; não descreve pessoas (falácia ecológica)"
    t.to_csv(os.path.join(out, "areas.csv"), index=False); t.to_parquet(os.path.join(out, "areas.parquet"), index=False)
    g = pd.read_parquet(os.path.join(P, "grupos_mc.parquet"))
    for nv in g["nivel"].unique():
        w = g[g["nivel"] == nv].pivot_table(index="grupo", columns="medida", values=["p05", "mediana", "p95"])
        w.columns = [f"{m}_{q}" for q, m in w.columns]
        w.reset_index().to_csv(os.path.join(out, f"{nv}.csv"), index=False)
    print(f"{len(t):,} áreas e {g['nivel'].nunique()} níveis agregados -> {out}")
