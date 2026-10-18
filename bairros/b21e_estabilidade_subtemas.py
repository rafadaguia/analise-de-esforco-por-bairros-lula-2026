#!/usr/bin/env python3
"""Etapa B21e: estabilidade dos subtemas por Monte Carlo (não é MCMC: a escolha do subtema é uma pontuação direta).

Repete a escolha de b21d N vezes, cada vez com:
  * bootstrap dos parágrafos de cada plano (sorteio com reposição dos parágrafos classificados);
  * perda aleatória de 20% dos rótulos de subtema (erro de classificação do modelo local, ~80% de acerto na amostra);
  * pesos da regra sorteados: expoente do volume de propostas de Lula entre 0,3 e 0,7 (b21d: 0,5) e constante somada à
    necessidade local entre 0,25 e 1 (b21d: 0,5).
Para cada área, tema e grupo (puxar, contraste, disputado), mede a fração dos sorteios em que o 1º subtema é o mesmo de
b21d. Selo: estável (>= 80%), moderado (50 a 80%), sensível (< 50%).

Saídas: variantes/<U>/subtemas_estabilidade.parquet (id_unidade, tema, modo, subtema, estab)
        bairros/insumos/temas/subtemas_estabilidade_resumo.csv
"""
import json, os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from b15_relatorios_cidades import TEMA   # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMAS = os.path.join(RAIZ, "bairros", "insumos", "temas")
N = int(os.environ.get("N_SORTEIOS", 300))
FONTE = os.environ.get("FONTE", "tudo")   # tudo | rotulos | planos (bootstrap e perda de rótulos) | pesos (só os pesos da regra)
norm = lambda x: "".join(c for c in x.lower() if c.isalnum())


def forca(pars, rng=None, perda=0.0):
    f = {}
    for x in pars:
        subs = x["subtemas"]
        if rng is not None and perda:
            subs = [s for s in subs if rng.random() >= perda]
        for s in subs:
            f[(x["cand"], s)] = f.get((x["cand"], s), 0) + 1 + 2 * x["concreto"]
    return f


def main():
    uni = sys.argv[1] if len(sys.argv) > 1 else "U4"
    pasta = os.path.join(RAIZ, "variantes", uni)
    tax = {t: v for t, v in json.load(open(os.path.join(TEMAS, "subtemas.json"))).items() if not t.startswith("_")}
    un = pd.read_parquet(os.path.join(pasta, "unidades.parquet"), columns=["id_unidade", "cd_mun_ibge", "pop"]).set_index("id_unidade")
    un["cd_mun_ibge"] = un["cd_mun_ibge"].astype("Int64").astype(str)
    a = pd.read_parquet(os.path.join(pasta, "subtemas_ind_area.parquet")).set_index("id_unidade").reindex(un.index)
    m = pd.read_parquet(os.path.join(pasta, "subtemas_ind_municipio.parquet")).set_index("cd_mun_ibge")
    pop_mun = un.groupby("cd_mun_ibge")["pop"].sum()
    mun = un["cd_mun_ibge"]
    # necessidade (0 a 1) por área e subtema, como em b21d
    rk_a = {c: a[c].rank(pct=True) for c in a.columns if a[c].dtype.kind in "fi" and c != "cd_mun_ibge"}
    rk_m = {c: m[c].rank(pct=True) for c in m.columns}
    nec, guarda = {}, {}
    for t, lst in tax.items():
        for s in lst:
            cols = []
            for ind, sinal, nivel in s["ind"]:
                r = rk_a[ind] if nivel == "area" else mun.map(rk_m[ind]).set_axis(un.index)
                cols.append(r if sinal > 0 else 1 - r)
            nec[s["chave"]] = pd.concat(cols, axis=1).mean(axis=1).fillna(0.5).to_numpy() if cols else np.full(len(un), 0.5)
            ok = np.ones(len(un), bool)
            req = s.get("requer", {})
            if req.get("urbano"):
                ok &= ~((a["rural"] > 50) | (mun.map(pop_mun).fillna(0) < 50000)).to_numpy()
            if req.get("amazonia"):
                ok &= (mun.map(m["amazonia"]).fillna(0) >= 1).to_numpy()
            if norm(s["nome"]) == norm(TEMA.get(t, "")):
                ok[:] = False
            guarda[s["chave"]] = ok
    tm = pd.read_parquet(os.path.join(pasta, "temas_unidades.parquet")).set_index("id_unidade").reindex(un.index)
    pres = {}   # (tema, modo) -> máscara de áreas
    for modo, col in (("a", "temas_aderentes_lula"), ("f", "temas_flavio_mais_fraco"), ("d", "temas_disputados")):
        lst = tm[col].fillna("").str.split(";")
        for t in tax:
            pres[(t, modo)] = lst.map(lambda x: t in x).to_numpy()
    pars = [json.loads(l) for l in open(os.path.join(RAIZ, "dados_bairros", "proc", "planos_subtemas_final.jsonl"))]
    por_cand = {c: [x for x in pars if x["cand"] == c] for c in ("lula", "flavio")}

    def escolher(f, expo, const):
        out = {}
        for (t, modo), msk in pres.items():
            if not msk.any():
                continue
            subs = tax[t]
            sc = np.full((len(un), len(subs)), -np.inf)
            for j, s in enumerate(subs):
                L, F = f.get(("lula", s["chave"]), 0), f.get(("flavio", s["chave"]), 0)
                if L < 4 or (modo == "a" and L <= F) or (modo == "d" and L < F) or (modo == "f" and F >= L):
                    continue
                if modo == "f":
                    w = (L / (L + F)) * L ** expo
                elif modo == "d":
                    w = L ** expo * (1 + 0.5 * (L - F) / (L + F + 1))
                else:
                    w = (1 + (L - F) / (L + F + 1)) * L ** expo
                sc[:, j] = np.where(guarda[s["chave"]], (const + nec[s["chave"]]) * w, -np.inf)
            best = np.where(np.isfinite(sc).any(axis=1), sc.argmax(axis=1), -1)
            o = np.argsort(-sc, axis=1)
            seg = np.where(np.isfinite(np.take_along_axis(sc, o[:, 1:2], 1))[:, 0], o[:, 1], -1) if sc.shape[1] > 1 else np.full(len(best), -1)
            out[(t, modo)] = (best, seg)
        return out

    base = escolher(forca(pars), 0.5, 0.5)
    # conferência: a reimplementação reproduz b21d
    st = json.load(open(os.path.join(pasta, "subtemas_areas.json")))
    ids = un.index.to_numpy(); dif = tot = 0
    for (t, modo), (b, _) in base.items():
        for i in np.flatnonzero(pres[(t, modo)]):
            esp = st.get(ids[i], {}).get(t, {}).get(modo)
            got = tax[t][b[i]]["chave"] if b[i] >= 0 else None
            tot += 1; dif += (esp[0][0] if esp else None) != got
    print(f"reprodução de b21d: {tot - dif:,} de {tot:,} iguais")
    rng = np.random.default_rng(2026)
    igual = {k: np.zeros(len(un)) for k in base}
    top2 = {k: np.zeros(len(un)) for k in base}
    f0 = forca(pars)
    for it in range(N):
        if FONTE == "rotulos":   # só erro de rótulo: plano inteiro, cada rótulo cai com 10% (erro residual após conferência)
            f = forca(pars, rng, 0.1)
        elif FONTE in ("tudo", "planos"):
            amostra = [x for c, lst in por_cand.items() for x in rng.choice(np.array(lst, dtype=object), len(lst), replace=True)]
            f = forca(amostra, rng, 0.2)
        else:
            f = f0
        expo, const = (rng.uniform(0.3, 0.7), rng.uniform(0.25, 1.0)) if FONTE in ("tudo", "pesos") else (0.5, 0.5)
        esc = escolher(f, expo, const)
        for k, (b, _) in base.items():
            igual[k] += esc[k][0] == b
            top2[k] += (esc[k][0] == b) | (esc[k][1] == b)
    linhas = []
    for (t, modo), (b, _) in base.items():
        for i in np.flatnonzero(pres[(t, modo)]):
            linhas.append((ids[i], t, modo, tax[t][b[i]]["chave"] if b[i] >= 0 else "", igual[(t, modo)][i] / N, top2[(t, modo)][i] / N))
    df = pd.DataFrame(linhas, columns=["id_unidade", "tema", "modo", "subtema", "estab", "estab_top2"])
    sufixo = "" if FONTE == "tudo" else f"_{FONTE}"
    df.to_parquet(os.path.join(pasta, f"subtemas_estabilidade{sufixo}.parquet"), index=False)
    print("1º subtema continua entre os 2 mostrados (média):", round(df["estab_top2"].mean(), 3),
          "| >= 80%:", round((df["estab_top2"] >= 0.8).mean(), 3))
    df["selo"] = pd.cut(df["estab"], [-1, 0.5, 0.8, 1.01], labels=["sensível", "moderado", "estável"], right=False)
    print(f"\n{N} sorteios. Pares área-tema: {len(df):,}")
    print(df["selo"].value_counts(normalize=True).round(3).to_string())
    r = df.groupby(["tema", "subtema"]).agg(areas=("estab", "size"), estab_media=("estab", "mean"),
                                           pct_estavel=("estab", lambda x: (x >= 0.8).mean())).round(3).reset_index()
    r = r.merge(df.groupby(["tema", "subtema"])["estab_top2"].mean().round(3).reset_index(), on=["tema", "subtema"])
    r.sort_values("areas", ascending=False).to_csv(os.path.join(TEMAS, f"subtemas_estabilidade_resumo{sufixo}.csv"), index=False)
    print(r.sort_values("areas", ascending=False).head(30).to_string(index=False))


if __name__ == "__main__":
    main()
