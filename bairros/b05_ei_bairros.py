#!/usr/bin/env python3
"""Etapa B5: inferência ecológica RxC hierárquica no nível de bairro (unidade).

Estende o modelo de inferencia_ecologica.py (Rosen, Jiang, King e Tanner, 2001; mesma tabela
4x3, mesma verossimilhança Dirichlet com concentração crescente no eleitorado, mesmas faixas
pelo voto de Lula no 1º turno) para a hierarquia

    país -> UF -> região metropolitana -> município -> unidade (bairro)

    logit[i, origem, destino] = eta[faixa_i] + w_i·gamma + a_rm[rm_i] + a_mun[mun_i] + u_i[destino]

  * país: as taxas por faixa (eta) do modelo municipal publicado (v2.0, modelo/ei_2022.nc)
    entram como priori informativa, centrada na mediana nacional e com desvio
    max(2 x desvio posterior, 0,3). É a agregação parcial no nível nacional, em duas etapas
    (aproximação empírica de Bayes ao modelo conjunto; o modelo conjunto é a variante M2).
  * UF: cada UF é ajustada à parte (lotes em paralelo, checkpoint por UF); eta e gamma
    podem se afastar da média nacional.
  * RM, município: efeitos aleatórios em todas as 8 células (origem x destino livre), com
    escala estimada (não centrados). Município fora de RM: a_rm = 0.
  * unidade: deslocamento comum a todas as origens, por destino (2 parâmetros por unidade).
    Com dados agregados, mais que isso por unidade não é identificável.

Variantes de método:
  MC  MCMC (nutpie, NUTS) em todas as UFs, 4 cadeias por UF
  M2  ADVI (PyMC) do país inteiro num só modelo (UF como mais um nível de efeito aleatório)
  M3  MCMC com amostra reduzida (metade das unidades de cada município grande) - só se MC for inviável

Checagem de cadeias (o MCMC não é determinístico entre execuções): cadeia com
log-verossimilhança média mais de 20 unidades abaixo da melhor é descartada e registrada.

Uso:
  python bairros/b05_ei_bairros.py --unidade U1 --metodo MC [--ufs SP MG] [--validacao] [--rapido]
  python bairros/b05_ei_bairros.py --unidade U1 --metodo M2
"""
import argparse, json, os, sys, time
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np
import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from inferencia_ecologica import ORIGEM, DESTINO, ROTULOS, SEMENTE, faixa  # noqa: E402

PROC = os.path.join(RAIZ, "dados_bairros", "proc")
VAR = os.path.join(RAIZ, "variantes")
LIMITE_COV = 2.5
COVS = ["log_aptos_z", "log_renda_z"]
TOL_LOGP = 20.0


# ------------------------------------------------------------------ dados

def agregar(variante, ano, turnos=(1, 2)):
    """Votos por unidade e turno, a partir das seções (só presidente)."""
    import duckdb
    su = os.path.join(VAR, variante, "secao_unidade.parquet" if ano in (2022, 2026) else "secao_unidade_hist.parquet")
    sec = os.path.join(PROC, f"secoes_{ano}.parquet")
    q = f"""
      SELECT su.id_unidade, s.turno, ANY_VALUE(su.cd_mun_ibge) cd_mun_ibge, ANY_VALUE(s.uf) uf,
             ANY_VALUE(su.nome_rm) nome_rm,
             SUM(s.lula) lula, SUM(s.adversario) adv, SUM(s.terceiros) terc, SUM(s.brancos) brancos,
             SUM(s.nulos) nulos, SUM(s.aptos) aptos, SUM(s.comparecimento) comparec, COUNT(*) secoes
      FROM '{sec}' s JOIN (SELECT * FROM '{su}' WHERE ano = {ano}) su
        ON s.uf = su.uf AND s.cd_mun_tse = su.cd_mun_tse AND s.zona = su.zona AND s.secao = su.secao
      WHERE s.uf <> 'ZZ' AND s.turno IN ({",".join(map(str, turnos))})
      GROUP BY su.id_unidade, s.turno
      ORDER BY su.id_unidade, s.turno"""   # ordem fixa: sem ela o DuckDB devolve as linhas em ordem variável
    return duckdb.sql(q).df()


def montar(variante, ano=2022):
    """Uma linha por unidade com 1º (4 grupos) e 2º turno (3 grupos) de `ano`, como montar_2022()."""
    a = agregar(variante, ano)
    t1 = a[a["turno"] == 1].set_index("id_unidade")
    t2 = a[a["turno"] == 2].set_index("id_unidade")
    d = t1.join(t2[["lula", "adv", "aptos"]], rsuffix="_2t", how="inner")
    d = d[(d["aptos"] > 0) & (d["lula"] + d["adv"] + d["terc"] > 0)].copy()
    un = pd.read_parquet(os.path.join(VAR, variante, "unidades.parquet"))
    un["renda_resp"] = un["renda_resp_soma"] / un["resp_com_renda"]
    d = d.join(un.set_index("id_unidade")[["renda_resp", "tipo", "nome"]], how="left")
    # renda ausente (unidade residual, sigilo): média ponderada do município
    rm_mun = un.groupby("cd_mun_ibge").apply(lambda g: g["renda_resp_soma"].sum()/max(g["resp_com_renda"].sum(), 1),
                                             include_groups=False)
    d["renda_resp"] = d["renda_resp"].where(d["renda_resp"] > 0, d["cd_mun_ibge"].map(rm_mun))
    d["renda_resp"] = d["renda_resp"].where(d["renda_resp"] > 0)
    d["renda_resp"] = d["renda_resp"].fillna(d.groupby("uf")["renda_resp"].transform("median")).fillna(d["renda_resp"].median())
    N = d["aptos"].to_numpy(float)
    l1, b1, t1_ = (d[c].to_numpy(float) for c in ("lula", "adv", "terc"))
    l2, b2 = d["lula_2t"].to_numpy(float), d["adv_2t"].to_numpy(float)
    x = np.c_[l1, b1, t1_, np.maximum(N - l1 - b1 - t1_, 0)] / N[:, None]
    x = x / x.sum(1, keepdims=True)
    y = np.c_[l2, b2, np.maximum(N - l2 - b2, 1.0)]
    y = y / y.sum(1, keepdims=True)
    # zero votos num destino (unidade minúscula): a Dirichlet exige proporções > 0
    y = np.maximum(y, 1e-4); y = y / y.sum(1, keepdims=True)
    d["lula_pct_1t"] = 100*l1/(l1 + b1 + t1_)
    d["faixa_ei"] = faixa(d["lula_pct_1t"])
    return d.reset_index(), x, y, N


def covariaveis(aptos, renda, ref=None):
    bruto = np.c_[np.log(aptos), np.log(renda)]
    if ref is None:
        ref = (bruto.mean(0), bruto.std(0))
    return np.clip((bruto - ref[0])/ref[1], -LIMITE_COV, LIMITE_COV), ref


def prioris_nacionais():
    """Mediana e desvio das taxas por faixa (eta) do modelo municipal v2.0 (convergente)."""
    import xarray as xr
    post = xr.open_datatree(os.path.join(RAIZ, "modelo", "ei_2022.nc"))["posterior"].to_dataset()
    eta = post["eta"].stack(s=("chain", "draw"))
    return eta.median("s").values, np.maximum(2*eta.std("s").values, 0.3)


def indices(d, colunas):
    out = {}
    for c in colunas:
        cats, idx = np.unique(d[c].fillna("__nenhum__").astype(str), return_inverse=True)
        out[c] = (idx, cats)
    return out


# ----------------------------------------------------------------- modelo

# Informação externa sobre a terceira via (--priori-terc): Datafolha, véspera do 2º turno de 2022 (BR-08297/2022, p. 4):
# eleitores de Tebet 59% Lula / 41% Bolsonaro nos válidos, 21% branco ou nulo e 7% indecisos; de Ciro 56% / 44%, 18% e 5%.
# Ponderado pelos votos do 1º turno (Tebet 4,92 mi, Ciro 3,60 mi): 57,7% para Lula entre os válidos. Fora (branco, nulo,
# indeciso ou abstenção) em torno de 25%. Entra como priori nas células da terceira via, com folga para variação regional.
PRIORI_TERC = {"logit_lula_vs_adv": float(np.log(0.577 / 0.423)), "dp_razao": 0.35,
               "log_odds_vota": float(np.log(0.75 / 0.25)), "dp_vota": 0.5}


def construir(x, y, N, g, w, mun, rm, tem_rm, eta_mu, eta_sd, uf=None, logN_ref=None, priori_terc=False):
    import pymc as pm
    import pytensor.tensor as pt
    n = len(N)
    n_mun, n_rm = mun.max() + 1, rm.max() + 1
    coords = {"origem": ORIGEM, "destino_livre": DESTINO[:2], "faixa": ROTULOS, "cov": COVS}
    logN = np.log(N) - (np.log(N).mean() if logN_ref is None else logN_ref)
    with pm.Model(coords=coords) as m:
        eta = pm.Normal("eta", eta_mu, eta_sd, dims=("faixa", "origem", "destino_livre"))
        if priori_terc:   # pesquisa de 2022 sobre os eleitores da terceira via (ver PRIORI_TERC)
            pr = PRIORI_TERC
            razao = eta[:, 2, 0] - eta[:, 2, 1]
            vota = pt.logsumexp(eta[:, 2, :], axis=1)          # log(odds de votar em um dos dois vs. ficar de fora)
            pm.Potential("priori_terc", pm.logp(pm.Normal.dist(pr["logit_lula_vs_adv"], pr["dp_razao"]), razao).sum()
                         + pm.logp(pm.Normal.dist(pr["log_odds_vota"], pr["dp_vota"]), vota).sum())
        gamma = pm.Normal("gamma", 0, 0.5, dims=("cov", "origem", "destino_livre"))
        # município: 2 efeitos (um por destino), comuns às origens. Com 8 por município o modelo
        # não identificava nada nos muitos municípios de unidade única (ESS 3 em SP no teste)
        s_mun = pm.HalfNormal("s_mun", 0.5, shape=2)
        z_mun = pm.Normal("z_mun", 0, 1, shape=(n_mun, 2))
        a_mun = (s_mun * z_mun)[:, None, :]
        # RM: idem, 2 efeitos. Com 8, s_rm das células da terceira via formava um funil (R-hat 1,21)
        s_rm = pm.HalfNormal("s_rm", 0.3, shape=2)
        z_rm = pm.Normal("z_rm", 0, 1, shape=(n_rm, 2))
        a_rm = (s_rm * z_rm * tem_rm[:, None])[:, None, :]
        # unidade: só onde o município tem mais de uma (senão se confunde com o município)
        multi = np.bincount(mun, minlength=n_mun)[mun] > 1
        u_idx = np.where(multi, np.cumsum(multi) - 1, int(multi.sum()))
        s_u = pm.HalfNormal("s_u", 0.3, shape=2)
        z_u = pm.Normal("z_u", 0, 1, shape=(max(int(multi.sum()), 1), 2))
        u = pt.concatenate([s_u * z_u, pt.zeros((1, 2))], axis=0)[u_idx]
        logit = eta[g] + pt.einsum("ok,krc->orc", w, gamma) + a_mun[mun] + a_rm[rm] + u[:, None, :]
        if uf is not None:  # modelo conjunto do país (M2): UF como mais um nível
            n_uf = uf.max() + 1
            s_uf = pm.HalfNormal("s_uf", 0.5, dims=("origem", "destino_livre"))   # UF: 8 células (há dados de sobra)
            z_uf = pm.Normal("z_uf", 0, 1, shape=(n_uf, 4, 2))
            logit = logit + (s_uf * z_uf)[uf]
        logit = pt.concatenate([logit, pt.zeros((n, 4, 1))], axis=2)
        beta = pt.special.softmax(logit, axis=2)
        theta = pt.einsum("or,orc->oc", x, beta)
        log_k0 = pm.Normal("log_k0", np.log(300), 2)
        rho = pm.Beta("rho", 2, 2)
        kappa = pt.exp(log_k0 + rho*logN)
        pm.Dirichlet("y", a=kappa[:, None]*theta + 1e-6, observed=y)
    return m


LONGO = False   # --longo: 4.000 de aquecimento e target_accept 0,98 (UFs que não convergiram)
AJUSTE = {}     # --tune/--draws/--cadeias: sobrepõem o padrão (reajuste extralongo: 10.000 / 1.500 / 12)


def amostrar_mcmc(m, rapido, cadeias=6):
    import nutpie
    cadeias = AJUSTE.get("cadeias") or cadeias
    comp = nutpie.compile_pymc_model(m)
    # completo: 2.000 de aquecimento e 1.000 sorteios. Com 1.000/500, R-hat chegou a 1,08 em SP
    # (terceira via) e 3 de 4 cadeias da BA ficaram em modo inferior
    kw = dict(draws=200, tune=300, chains=cadeias) if rapido else dict(draws=1000, tune=4000 if LONGO else 2000, chains=cadeias)
    if not rapido:
        kw.update({k: v for k, v in (("tune", AJUSTE.get("tune")), ("draws", AJUSTE.get("draws"))) if v})
    return nutpie.sample(comp, seed=SEMENTE, progress_bar=False, save_warmup=False,
                         adaptation="low_rank", target_accept=0.98 if (LONGO or AJUSTE) else 0.95, cores=cadeias, **kw)


def ds(no):
    return no.to_dataset() if hasattr(no, "to_dataset") else no


def descartar_presas(tr):
    """Cadeias presas em modo inferior. Devolve posterior, estatísticas e o registro."""
    post, st = ds(tr.posterior), ds(tr.sample_stats)
    lp = st["logp"].mean("draw").values
    boas = np.where(lp >= lp.max() - TOL_LOGP)[0]
    reg = {"logp_cadeias": [round(float(v), 1) for v in lp], "descartadas": [int(i) for i in range(len(lp)) if i not in boas]}
    return post.isel(chain=boas), st.isel(chain=boas), reg


def diagnostico(post):
    import arviz as az
    s = az.summary(post, var_names=["eta", "gamma", "s_mun", "s_rm", "s_u", "log_k0", "rho"])
    return float(s["r_hat"].max()), float(s["ess_bulk"].min())


# ------------------------------------------------------------- execução

def ajustar_uf(variante, metodo, uf, rapido, validacao, out, ano=2022):
    """Ajusta uma UF (MCMC). Checkpoint: pula se o posterior já existe."""
    import xarray as xr
    tag = f"{uf}{'_val' if validacao else ''}"
    arq = os.path.join(out, f"post_{tag}.nc")
    if os.path.exists(arq):
        return json.load(open(os.path.join(out, f"diag_{tag}.json")))
    d, x, y, N = montar(variante, ano)
    w, ref = covariaveis(N, d["renda_resp"])           # padronização nacional (mesma em todas as UFs)
    logN_ref = np.log(N).mean()
    sel = (d["uf"] == uf).to_numpy()
    d, x, y, N, w = d[sel].reset_index(drop=True), x[sel], y[sel], N[sel], w[sel]
    ix = indices(d, ["cd_mun_ibge", "nome_rm"])
    mun, rm = ix["cd_mun_ibge"][0], ix["nome_rm"][0]
    tem_rm = (ix["nome_rm"][1] != "__nenhum__").astype(float)
    g = d["faixa_ei"].cat.codes.to_numpy()
    eta_mu, eta_sd = prioris_nacionais()
    if ano != 2022:
        # backtesting: a priori nacional vem do ajuste de 2022, que é justamente o que se quer prever.
        # Sem ela, priori vaga (o teste fica um pouco pessimista em relação ao modelo principal)
        eta_mu, eta_sd = np.zeros_like(eta_mu), np.full_like(eta_sd, 1.5)
    treino = np.ones(len(N), bool)
    if validacao:
        treino = np.random.default_rng(SEMENTE + 1).random(len(N)) >= 0.2
    t0 = time.time()
    m = construir(x[treino], y[treino], N[treino], g[treino], w[treino], mun[treino], rm[treino], tem_rm,
                  eta_mu, eta_sd, logN_ref=logN_ref, priori_terc=AJUSTE.get("priori_terc", False))
    tr = amostrar_mcmc(m, rapido)
    post, st, reg = descartar_presas(tr)
    rhat, ess = diagnostico(post)
    div = int(st["diverging"].sum())
    keep = ["eta", "gamma", "s_mun", "z_mun", "s_rm", "z_rm", "s_u", "z_u", "log_k0", "rho"]
    post[keep].to_netcdf(arq)
    np.savez(os.path.join(out, f"dados_{tag}.npz"), ids=d["id_unidade"].to_numpy(str), treino=treino,
             mun=mun, rm=rm, tem_rm=tem_rm, g=g, w=w, x=x, y=y, N=N, logN_ref=logN_ref,
             ref_media=ref[0], ref_desvio=ref[1])
    diag = {"uf": uf, "validacao": validacao, "unidades": int(len(N)), "unidades_treino": int(treino.sum()),
            "municipios": int(mun.max() + 1), "rms": int(tem_rm.sum()), "segundos": round(time.time() - t0),
            "rhat_max": round(rhat, 3), "ess_min": round(ess), "divergencias": div, "cadeias": len(reg["logp_cadeias"]),
            "aquecimento": AJUSTE.get("tune") or (4000 if LONGO else 2000), "priori_terc": bool(AJUSTE.get("priori_terc")), **reg}
    json.dump(diag, open(os.path.join(out, f"diag_{tag}.json"), "w"))
    return diag


def ajustar_m2(variante, out, iteracoes=60000):
    """ADVI do país inteiro, UF como nível de efeito aleatório."""
    import pymc as pm
    arq = os.path.join(out, "post_BR.nc")
    if os.path.exists(arq):
        return
    d, x, y, N = montar(variante)
    w, ref = covariaveis(N, d["renda_resp"])
    ix = indices(d, ["cd_mun_ibge", "nome_rm", "uf"])
    tem_rm = (ix["nome_rm"][1] != "__nenhum__").astype(float)
    eta_mu, eta_sd = prioris_nacionais()
    g = d["faixa_ei"].cat.codes.to_numpy()
    t0 = time.time()
    m = construir(x, y, N, g, w, ix["cd_mun_ibge"][0], ix["nome_rm"][0], tem_rm, eta_mu, eta_sd, uf=ix["uf"][0])
    with m:
        ap = pm.fit(iteracoes, method="advi", random_seed=SEMENTE, progressbar=False,
                    callbacks=[pm.variational.callbacks.CheckParametersConvergence(tolerance=1e-3, diff="relative")])
        tr = ap.sample(1000, random_seed=SEMENTE)
    keep = ["eta", "gamma", "s_mun", "z_mun", "s_rm", "z_rm", "s_u", "z_u", "s_uf", "z_uf", "log_k0", "rho"]
    ds(tr.posterior)[keep].to_netcdf(arq)
    np.savez(os.path.join(out, "dados_BR.npz"), ids=d["id_unidade"].to_numpy(str), mun=ix["cd_mun_ibge"][0],
             rm=ix["nome_rm"][0], uf=ix["uf"][0], uf_cats=ix["uf"][1], tem_rm=tem_rm, g=g, w=w, x=x, y=y, N=N,
             logN_ref=np.log(N).mean(), ref_media=ref[0], ref_desvio=ref[1])
    hist = np.asarray(ap.hist)
    json.dump({"uf": "BR", "metodo": "ADVI", "unidades": int(len(N)), "segundos": round(time.time() - t0),
               "iteracoes": int(len(hist)), "elbo_final": float(-hist[-1000:].mean())},
              open(os.path.join(out, "diag_BR.json"), "w"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unidade", default="U1")
    ap.add_argument("--metodo", default="MC", choices=["MC", "M2", "M3"])
    ap.add_argument("--ufs", nargs="*")
    ap.add_argument("--rapido", action="store_true")
    ap.add_argument("--validacao", action="store_true")
    ap.add_argument("--longo", action="store_true")
    ap.add_argument("--tune", type=int); ap.add_argument("--draws", type=int); ap.add_argument("--cadeias", type=int)
    ap.add_argument("--priori-terc", action="store_true", help="usa a pesquisa de 2022 sobre a terceira via como priori")
    ap.add_argument("--sufixo", default="", help="pasta de saída <metodo><sufixo> (ex.: _extralongo)")
    ap.add_argument("--ano", type=int, default=2022, help="ano das transferências 1º->2º turno (backtesting: 2018, 2014, 2010)")
    a = ap.parse_args()
    global LONGO
    LONGO = a.longo
    AJUSTE.update({k: v for k, v in (("tune", a.tune), ("draws", a.draws), ("cadeias", a.cadeias), ("priori_terc", a.priori_terc)) if v})
    out = os.path.join(VAR, a.unidade, a.metodo + ("_rapido" if a.rapido else "") + ("_longo" if a.longo else "") + ("" if a.ano == 2022 else f"_{a.ano}") + a.sufixo)
    os.makedirs(out, exist_ok=True)
    if a.metodo == "M2":
        ajustar_m2(a.unidade, out)
        return
    for uf in a.ufs:
        diag = ajustar_uf(a.unidade, a.metodo, uf, a.rapido, a.validacao, out, a.ano)
        print(json.dumps(diag), flush=True)


if __name__ == "__main__":
    main()
