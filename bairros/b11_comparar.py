#!/usr/bin/env python3
"""Etapa B11: compara variantes (método MC x M2; unidades U1 x U2 x U3; pesos P1-P3; MRP x modelo ecológico).

Saídas em variantes/comparacoes/: uma tabela por comparação, lidas pelo notebook e pelo relatório.
Uso: python bairros/b11_comparar.py
"""
import os, sys
import numpy as np
import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAR = os.path.join(RAIZ, "variantes")
OUT = os.path.join(VAR, "comparacoes")
FOCOS = os.path.join(RAIZ, "painel", "focos_ei.csv")


def ler(u, m):
    p = os.path.join(VAR, u, m)
    if not os.path.exists(os.path.join(p, "esforco.parquet")):
        return None
    mc = pd.read_parquet(os.path.join(p, "unidades_mc.parquet"))
    es = pd.read_parquet(os.path.join(p, "esforco.parquet"))[["id_unidade", "pot_mil", "nivel_P1", "nivel_P2", "nivel_P3"]]
    return mc.merge(es, on="id_unidade")


def metodo(u="U1"):
    a, b = ler(u, "MC"), ler(u, "M2")
    if a is None or b is None:
        return None
    j = a.merge(b, on="id_unidade", suffixes=("_mc", "_m2"))
    linhas = []
    for med in ("pot_p50", "margem_base_p50", "mob_p50", "lula2_base_p50", "prob_mob_rende"):
        x, y = j[f"{med}_mc"], j[f"{med}_m2"]
        linhas.append({"medida": med, "correlacao": round(x.corr(y), 3), "dif_mediana_abs": round((x - y).abs().median(), 3),
                       "soma_mc": round(x.sum(), 0) if "p50" in med and "lula2" not in med else None,
                       "soma_m2": round(y.sum(), 0) if "p50" in med and "lula2" not in med else None})
    for p in ("P1", "P2", "P3"):
        x, y = j[f"nivel_{p}_mc"], j[f"nivel_{p}_m2"]
        m = x.notna() & y.notna()
        linhas.append({"medida": f"nivel_{p}", "correlacao": round(x[m].astype(float).corr(y[m].astype(float)), 3),
                       "mudam_de_nivel": int((x[m] != y[m]).sum()), "unidades": int(m.sum())})
    # largura relativa dos intervalos (o ADVI costuma subestimar a incerteza)
    lw = lambda df, s: ((df[f"pot_p95{s}"] - df[f"pot_p05{s}"]) / df[f"pot_p50{s}"].clip(lower=1)).median()
    linhas.append({"medida": "largura_relativa_ic90_potencial", "mc": round(lw(j, "_mc"), 3), "m2": round(lw(j, "_m2"), 3)})
    return pd.DataFrame(linhas)


def frentes(u, m):
    """Potencial das áreas dentro dos 200 municípios-foco da v2.0, por frente (comparável aos 459 mil)."""
    d = ler(u, m)
    if d is None:
        return None
    f = pd.read_csv(FOCOS)
    foco = d[d["cd_mun_ibge"].isin(f["cd_municipio_ibge"])]
    g = foco.groupby("frente").agg(areas=("id_unidade", "size"), pot_p50=("pot_p50", "sum"),
                                   areas_nivel7_P1=("nivel_P1", lambda s: int((s == 7).sum())))
    g.loc["TODOS OS FOCOS"] = [len(foco), foco["pot_p50"].sum(), int((foco["nivel_P1"] == 7).sum())]
    v2 = pd.read_csv(os.path.join(RAIZ, "painel", "cenarios_frentes.csv"))
    v2 = v2[v2["medida"] == "potencial (terreno + 2 pp)"].set_index("frente")["mediana"]
    g["pot_v2_municipal"] = v2.reindex(g.index)
    g["variante"] = f"{u}/{m}"
    return g.reset_index()


def unidades():
    linhas = []
    for u in ("U1", "U2", "U3", "U4"):
        p = os.path.join(VAR, u, "medidas.json")
        if os.path.exists(p):
            import json
            m = json.load(open(p))
            linhas.append({"variante": u, **{k: v for k, v in m.items() if not isinstance(v, dict)}})
        d = ler(u, "MC")
        if d is not None:
            linhas[-1].update({"potencial_total": round(d["pot_p50"].sum()), "margem_base_total": round(d["margem_base_p50"].sum())})
    return pd.DataFrame(linhas)


def mrp_vs_ei(u="U1", m="MC"):
    d = ler(u, m)
    p = os.path.join(VAR, u, "mrp.parquet")
    if d is None or not os.path.exists(p):
        return None, None
    r = pd.read_parquet(p)
    j = d.merge(r, on=["id_unidade"], suffixes=("", "_mrp"))
    linhas = []
    for v in ("R1", "R2", "R3"):
        ok = j[f"{v}_p50"].notna()
        dif = j.loc[ok, f"{v}_p50"] - j.loc[ok, "lula2_base_p50"]
        linhas.append({"variante_mrp": v, "unidades": int(ok.sum()), "correlacao_com_ei": round(j.loc[ok, f"{v}_p50"].corr(j.loc[ok, "lula2_base_p50"]), 3),
                       "dif_media_pp": round(100*dif.mean(), 2), "dif_abs_mediana_pp": round(100*dif.abs().median(), 2),
                       "pct_divergencia_maior_10pp": round(100*(dif.abs() > 0.10).mean(), 1)})
    j["div_R3_pp"] = 100*(j["R3_p50"] - j["lula2_base_p50"])
    por_uf = j.groupby("uf").agg(div_media_pp=("div_R3_pp", "mean"), div_abs_mediana_pp=("div_R3_pp", lambda s: s.abs().median())).round(2)
    return pd.DataFrame(linhas), por_uf.reset_index()


def main():
    os.makedirs(OUT, exist_ok=True)
    r = metodo()
    if r is not None:
        r.to_csv(os.path.join(OUT, "metodo_MC_x_M2.csv"), index=False); print(r.to_string(index=False))
    fs = [f for f in (frentes(u, m) for u in ("U1", "U2", "U3", "U4") for m in ("MC", "M2")) if f is not None]
    if fs:
        f = pd.concat(fs); f.to_csv(os.path.join(OUT, "frentes.csv"), index=False); print(f.round(0).to_string(index=False))
    un = unidades(); un.to_csv(os.path.join(OUT, "unidades.csv"), index=False); print(un.to_string(index=False))
    a, b = mrp_vs_ei()
    if a is not None:
        a.to_csv(os.path.join(OUT, "mrp_x_ei.csv"), index=False); b.to_csv(os.path.join(OUT, "mrp_x_ei_uf.csv"), index=False)
        print(a.to_string(index=False)); print(b.sort_values("div_media_pp").to_string(index=False))


if __name__ == "__main__" and len(sys.argv) == 1:
    main()


def unidades_por_populacao(pesos="P2"):
    """Comparação entre geografias diferentes (U1 x U2 x U3): cada setor censitário recebe o nível da área em que está;
    mede-se a fração da população 15+ cujo nível muda ao trocar de unidade, e o potencial por município."""
    cs = pd.read_parquet(os.path.join(RAIZ, "dados_bairros", "proc", "censo_setores.parquet"), columns=["CD_SETOR", "CD_MUN", "pop_15m"])
    niv, pot = {}, {}
    for u in ("U1", "U2", "U3", "U4"):
        su = pd.read_parquet(os.path.join(VAR, u, "setor_unidade.parquet"))
        es = pd.read_parquet(os.path.join(VAR, u, "MC", "esforco.parquet"))[["id_unidade", f"nivel_{pesos}"]]
        su = su.drop_duplicates("CD_SETOR")   # a U2 repete alguns setores na junção de nomes
        niv[u] = su.merge(es, on="id_unidade", how="left").set_index("CD_SETOR")[f"nivel_{pesos}"]
        mc = pd.read_parquet(os.path.join(VAR, u, "MC", "unidades_mc.parquet"))
        pot[u] = mc.groupby("cd_mun_ibge")["pot_p50"].sum()
    s = cs.set_index("CD_SETOR")
    linhas = []
    for a, b in (("U1", "U2"), ("U1", "U3"), ("U2", "U3"), ("U1", "U4"), ("U2", "U4")):
        x, y = niv[a].reindex(s.index), niv[b].reindex(s.index)
        m = x.notna() & y.notna()
        w = s.loc[m, "pop_15m"].fillna(0)
        linhas.append({"de": a, "para": b, "pesos": pesos, "pop_15m_comparada_mi": round(w.sum()/1e6, 1),
                       "pct_pop_muda_nivel": round(100*w[x[m] != y[m]].sum()/w.sum(), 1),
                       "pct_pop_muda_2_ou_mais": round(100*w[(x[m] - y[m]).abs() >= 2].sum()/w.sum(), 1),
                       "corr_potencial_por_municipio": round(pd.concat([pot[a], pot[b]], axis=1).dropna().corr().iloc[0, 1], 3),
                       "potencial_total_a": round(pot[a].sum()), "potencial_total_b": round(pot[b].sum())})
    return pd.DataFrame(linhas)


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "populacao":
    t = pd.concat([unidades_por_populacao(p) for p in ("P1", "P2", "P3")])
    t.to_csv(os.path.join(OUT, "unidades_por_populacao.csv"), index=False)
    print(t.to_string(index=False))
