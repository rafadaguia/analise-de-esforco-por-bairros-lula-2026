#!/usr/bin/env python3
"""Inferência ecológica bayesiana das transferências de voto entre os turnos de 2022.

Por que RxC hierárquico, e não o EI de King (1997)
--------------------------------------------------
O método de King resolve tabelas 2x2: uma categoria de origem contra uma de
destino. Aqui a tabela é 4x3. O eleitorado de cada município sai do 1º turno
em quatro grupos (Lula, Bolsonaro, terceira via, fora: abstenção + brancos +
nulos) e chega ao 2º em três (Lula, Bolsonaro, fora). Aplicar King linha a
linha descartaria a restrição de que as linhas somam o 2º turno inteiro. O
modelo RxC de Rosen, Jiang, King e Tanner (2001) é a generalização bayesiana
hierárquica do método de King para esse caso, e é o que se implementa aqui
em PyMC. Diferenças em relação ao modelo de Rosen:

  * a taxa de cada município vem de um logit com efeito de faixa (parcialmente
    agregado entre as faixas) e covariáveis contextuais (porte e renda), em vez de um sorteio Dirichlet livre por município.
    Isso torna o modelo rápido o bastante para validação fora da amostra e
    reduz o viés de agregação que o EI clássico ignora;
  * a verossimilhança é Dirichlet sobre as proporções do 2º turno, com
    concentração que cresce com o eleitorado (expoente rho estimado). Uma
    multinomial com milhões de eleitores daria intervalos falsamente estreitos,
    e o OLS sobre votos absolutos deixava São Paulo, Rio e BH ditarem as taxas.

Faixas: definidas pelo voto de Lula no 1º turno (antes da transferência). A
versão anterior usava o 2º turno de 2022, ou seja, agrupava pelo resultado que
queria explicar, e aplicava as taxas a 2026 por uma faixa do 1º turno.

Saídas
------
  modelo/ei_2022.nc                   posterior completo (ArviZ / NetCDF)
  painel/taxas_ei_2022.csv            taxas por faixa e linha, mediana e intervalo de 90%
  painel/diagnostico_anomalia.csv     faixa 45-55%: método antigo, bootstrap e EI lado a lado
  painel/validacao_ei.csv             cobertura dos intervalos em municípios fora da amostra

Uso:
    .venv/bin/python inferencia_ecologica.py           # ajuste completo + validação
    # mais rápido, em paralelo (8 cadeias cada; usa 16 núcleos):
    .venv/bin/python inferencia_ecologica.py --sem-validacao & .venv/bin/python inferencia_ecologica.py --so-validacao
    .venv/bin/python inferencia_ecologica.py --rapido  # menos amostras, para testar
"""
import argparse, os, sys, time
import numpy as np
import pandas as pd
import pymc as pm
import pytensor.tensor as pt
import nutpie
import statsmodels.api as sm

RAIZ = os.path.dirname(os.path.abspath(__file__))
PAINEL = os.path.join(RAIZ, "painel")
MODELO = os.path.join(RAIZ, "modelo")

FAIXAS = [0, 35, 45, 55, 65, 100.0001]
ROTULOS = ["<35%", "35-45%", "45-55%", "55-65%", ">65%"]
ORIGEM = ["lula", "bolsonaro", "terceira_via", "fora"]     # 1º turno
DESTINO = ["lula", "bolsonaro", "fora"]                    # 2º turno
COVS = ["log_aptos_z", "log_renda_z"]
LIMITE_COV = 2.5
SEMENTE = 20261005


# ------------------------------------------------------------------ dados

def faixa(pct):
    return pd.cut(pct, FAIXAS, labels=ROTULOS, right=False)


def montar_2022():
    """Uma linha por município: 1º turno (4 grupos) e 2º turno (3 grupos), sobre os aptos."""
    d = pd.read_csv(os.path.join(PAINEL, "painel_final.csv"), dtype={"cd_mun_tse": str})
    d = d.dropna(subset=["QT_APTOS_1t", "QT_APTOS_2t"]).copy()
    N = d["QT_APTOS_1t"].to_numpy(float)
    l1, b1, t1 = (d[c].to_numpy(float) for c in ("lula_2022_1t", "bolso_2022_1t", "outros_2022_1t"))
    l2, b2 = d["lula_2022_2t"].to_numpy(float), d["bolso_2022_2t"].to_numpy(float)
    # O cadastro muda um pouco entre os turnos (até 632 aptos num município).
    # Ancoramos tudo nos aptos do 1º turno; "fora" absorve a diferença.
    x = np.c_[l1, b1, t1, N - l1 - b1 - t1] / N[:, None]
    y = np.c_[l2, b2, np.maximum(N - l2 - b2, 1.0)]
    y = y / y.sum(1, keepdims=True)
    d["lula_pct_1t_22"] = 100*l1/(l1 + b1 + t1)
    d["faixa_ei"] = faixa(d["lula_pct_1t_22"])
    return d.reset_index(drop=True), x, y, N


def covariaveis(aptos, renda, ref=None):
    """Covariáveis padronizadas. `ref` reaproveita média e desvio do ajuste (para aplicar a 2026).

    Só entram covariáveis de fora da eleição. A força de Lula no 1º turno já é uma das
    proporções de origem: deixar a taxa depender dela continuamente torna o modelo não
    identificável com dados agregados (King 1997, cap. 3). A dependência fica nas faixas,
    com agregação parcial entre elas."""
    bruto = np.c_[np.log(aptos), np.log(renda)]
    if ref is None:
        ref = (bruto.mean(0), bruto.std(0))
    # Limite em ±2,5 desvios: São Paulo está a 6,2 desvios da média em porte. Sem o
    # limite, o efeito linear do porte é extrapolado muito além dos dados e decide
    # sozinho as taxas das capitais (a de SP caía para 0,12 sem que os dados de SP,
    # onde o "fora" quase não mudou entre os turnos, dissessem isso).
    return np.clip((bruto - ref[0])/ref[1], -LIMITE_COV, LIMITE_COV), ref


# ----------------------------------------------------------------- modelo

def construir_modelo(x, y, N, g, w):
    coords = {"origem": ORIGEM, "destino_livre": DESTINO[:2], "faixa": ROTULOS,
              "cov": COVS, "obs": np.arange(len(N))}
    logN = np.log(N) - np.log(N).mean()
    with pm.Model(coords=coords) as m:
        # média nacional de cada linha (logit contra "fora") e dispersão entre faixas
        mu = pm.Normal("mu", 0, 2, dims=("origem", "destino_livre"))
        omega = pm.HalfNormal("omega", 1, dims=("origem", "destino_livre"))
        eta_z = pm.Normal("eta_z", 0, 1, dims=("faixa", "origem", "destino_livre"))
        eta = pm.Deterministic("eta", mu + omega*eta_z, dims=("faixa", "origem", "destino_livre"))
        gamma = pm.Normal("gamma", 0, 0.5, dims=("cov", "origem", "destino_livre"))

        logit = eta[g] + pt.einsum("ok,krc->orc", w, gamma)              # (obs, origem, 2)
        logit = pt.concatenate([logit, pt.zeros((len(N), 4, 1))], axis=2)
        beta = pt.special.softmax(logit, axis=2)                          # (obs, origem, destino)
        theta = pt.einsum("or,orc->oc", x, beta)

        # concentração cresce com o eleitorado: municípios grandes são menos ruidosos,
        # mas não infinitamente (rho < 1 = erro de especificação além da amostragem)
        log_k0 = pm.Normal("log_k0", np.log(300), 2)
        rho = pm.Beta("rho", 2, 2)
        kappa = pt.exp(log_k0 + rho*logN)
        pm.Dirichlet("y", a=kappa[:, None]*theta + 1e-6, observed=y)
    return m


def amostrar(m, rapido):
    comp = nutpie.compile_pymc_model(m)
    # 8 cadeias curtas em vez de 4 longas: mesmo total de amostras, metade do tempo de
    # parede (o nutpie roda uma cadeia por núcleo)
    kw = dict(draws=150, tune=300, chains=8) if rapido else dict(draws=500, tune=1000, chains=8)
    # low_rank: eta e gamma são correlacionados (a mesma taxa pode vir da faixa ou da
    # covariável); target_accept alto evita divergências no funil de omega
    return nutpie.sample(comp, seed=SEMENTE, progress_bar=False, save_warmup=False,
                         adaptation="low_rank", target_accept=0.95, **kw)


def betas(post, g, w):
    """Taxas municipais (amostras, obs, origem, destino) a partir do posterior."""
    eta = post["eta"].stack(s=("chain", "draw")).transpose("s", ...).values      # s,f,r,2
    gam = post["gamma"].stack(s=("chain", "draw")).transpose("s", ...).values    # s,k,r,2
    lg = eta[:, g] + np.einsum("ok,skrc->sorc", w, gam)
    lg = np.concatenate([lg, np.zeros(lg.shape[:3] + (1,))], axis=3)
    lg -= lg.max(3, keepdims=True)
    e = np.exp(lg)
    return e/e.sum(3, keepdims=True)


def resumo(a, q=(0.05, 0.5, 0.95)):
    return np.quantile(a, q, axis=0)


# --------------------------------------------------------- método antigo

def goodman(s):
    """Decomposição sem intercepto da versão anterior: a = terceira via, b = Δcomparecimento líquido."""
    bn1 = s["QT_VOTOS_BRANCOS_1t"] + s["QT_VOTOS_NULOS_1t"]
    bn2 = s["QT_VOTOS_BRANCOS_2t"] + s["QT_VOTOS_NULOS_2t"]
    X = np.c_[s["outros_2022_1t"], (s["QT_COMPARECIMENTO_2t"]-s["QT_COMPARECIMENTO_1t"])-(bn2-bn1)]
    yy = (s["lula_2022_2t"]-s["lula_2022_1t"]).to_numpy(float)
    coef, *_ = np.linalg.lstsq(X, yy, rcond=None)
    return coef


def diagnostico_anomalia(d, B=2000):
    """Faixa 45-55%: a anomalia sobrevive a mudar a definição de faixa, ao bootstrap, e a tirar as capitais?"""
    rng = np.random.default_rng(SEMENTE)
    v = d[d["outros_2022_1t"] > 300]
    linhas = []
    for nome, col in (("2º turno 2022 (versão anterior)", "lula_pct_22_2t"),
                      ("1º turno 2022 (pré-transferência)", "lula_pct_1t_22")):
        f = faixa(v[col])
        for rot in ROTULOS:
            s = v[f == rot]
            a, b = goodman(s)
            boot = np.array([goodman(s.iloc[rng.integers(0, len(s), len(s))]) for _ in range(B)])
            top3 = s.nlargest(3, "QT_APTOS_1t")
            a3, b3 = goodman(s.drop(top3.index))
            linhas.append({"definicao_faixa": nome, "faixa": rot, "municipios": len(s),
                           "b_goodman": b, "b_boot_p05": np.quantile(boot[:, 1], .05),
                           "b_boot_p95": np.quantile(boot[:, 1], .95),
                           "b_sem_3_maiores": b3, "3_maiores": ", ".join(top3["municipio"].str.title()),
                           "a_goodman": a, "a_boot_p05": np.quantile(boot[:, 0], .05),
                           "a_boot_p95": np.quantile(boot[:, 0], .95)})
    return pd.DataFrame(linhas)


# ------------------------------------------------------------------ saídas

def taxas_por_faixa(B, x, N, g):
    """Taxa agregada da faixa = média das taxas municipais ponderada pelos eleitores de cada origem."""
    linhas = []
    for gi, rot in enumerate(ROTULOS):
        idx = g == gi
        for r, orig in enumerate(ORIGEM):
            peso = (N[idx]*x[idx, r])
            agg = np.einsum("o,soc->sc", peso, B[:, idx, r, :])/peso.sum()      # s, destino
            for c, dest in enumerate(DESTINO):
                p05, p50, p95 = resumo(agg[:, c])
                linhas.append({"faixa": rot, "origem": orig, "destino": dest,
                               "p05": p05, "mediana": p50, "p95": p95})
            # entre quem saiu de "fora" e votou: fração que foi para Lula (comparável ao b antigo)
            if orig in ("fora", "terceira_via"):
                cond = agg[:, 0]/(agg[:, 0] + agg[:, 1])
                p05, p50, p95 = resumo(cond)
                linhas.append({"faixa": rot, "origem": orig, "destino": "lula_entre_votantes",
                               "p05": p05, "mediana": p50, "p95": p95})
    return pd.DataFrame(linhas)


def validar(d, x, y, N, g, w, rapido):
    """Ajusta em 80% dos municípios e mede a cobertura do intervalo de 90% nos outros 20%."""
    rng = np.random.default_rng(SEMENTE + 1)
    teste = rng.random(len(N)) < 0.2
    m = construir_modelo(x[~teste], y[~teste], N[~teste], g[~teste], w[~teste])
    tr = amostrar(m, rapido)
    post = tr.posterior
    Bt = betas(post, g[teste], w[teste])
    theta = np.einsum("or,sorc->soc", x[teste], Bt)
    k0 = post["log_k0"].stack(s=("chain", "draw")).values
    rho = post["rho"].stack(s=("chain", "draw")).values
    logN = np.log(N[teste]) - np.log(N[~teste]).mean()
    kappa = np.exp(k0[:, None] + rho[:, None]*logN[None])
    # predição: sorteio Dirichlet por amostra do posterior (via gamas)
    G = rng.gamma(kappa[..., None]*theta + 1e-6)
    pred = G/G.sum(2, keepdims=True)
    margem_pred = pred[..., 0] - pred[..., 1]
    margem_obs = y[teste, 0] - y[teste, 1]
    lo, hi = np.quantile(margem_pred, [.05, .95], axis=0)
    dentro = (margem_obs >= lo) & (margem_obs <= hi)
    # comparação: erro do método antigo (taxas fixas por faixa) para a mesma margem
    med = np.median(margem_pred, axis=0)
    out = pd.DataFrame({
        "faixa": np.array(ROTULOS)[g[teste]], "dentro_ic90": dentro,
        "erro_abs_pp": 100*np.abs(med - margem_obs), "aptos": N[teste]})
    tab = out.groupby("faixa", observed=True).agg(
        municipios=("dentro_ic90", "size"), cobertura_ic90=("dentro_ic90", "mean"),
        erro_mediano_pp=("erro_abs_pp", "median")).reindex(ROTULOS)
    tab.loc["TODOS"] = [len(out), out["dentro_ic90"].mean(), out["erro_abs_pp"].median()]
    return tab.reset_index()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapido", action="store_true")
    ap.add_argument("--sem-validacao", action="store_true")
    ap.add_argument("--so-validacao", action="store_true",
                    help="roda só a validação 80/20 (para executar em paralelo com o ajuste principal)")
    args = ap.parse_args()
    os.makedirs(MODELO, exist_ok=True)

    d, x, y, N = montar_2022()
    g = d["faixa_ei"].cat.codes.to_numpy()
    w, ref = covariaveis(N, d["renda_dom_pc"])
    print(f"2022: {len(d)} municípios | faixas (1º turno): "
          + ", ".join(f"{r} {n}" for r, n in zip(ROTULOS, np.bincount(g))))

    if args.so_validacao:
        print("[3] validação fora da amostra (80/20)")
        val = validar(d, x, y, N, g, w, args.rapido)
        val.to_csv(os.path.join(PAINEL, "validacao_ei.csv"), index=False)
        print(val.round(3).to_string(index=False))
        return 0

    print("\n[1] diagnóstico do método antigo (bootstrap de 2.000 reamostragens)")
    diag = diagnostico_anomalia(d)
    print(diag[["definicao_faixa", "faixa", "municipios", "b_goodman", "b_boot_p05",
                "b_boot_p95", "b_sem_3_maiores"]].round(3).to_string(index=False))

    print("\n[2] ajuste do modelo RxC hierárquico (nutpie)")
    t0 = time.time()
    tr = amostrar(construir_modelo(x, y, N, g, w), args.rapido)
    print(f"    {time.time()-t0:.0f}s")
    import arviz as az
    sm_ = az.summary(tr, var_names=["mu", "omega", "gamma", "log_k0", "rho"])
    rhat_max, ess_min = float(sm_["r_hat"].max()), float(sm_["ess_bulk"].min())
    div = int(tr.sample_stats["diverging"].sum())
    print(f"    R-hat máx {rhat_max:.3f} | ESS mín {ess_min:.0f} | divergências {div}")
    if rhat_max > 1.01:
        print(sm_.sort_values("r_hat", ascending=False).head(8)[["mean", "sd", "r_hat", "ess_bulk"]].to_string())
    print(f"    rho = {float(tr.posterior['rho'].median()):.3f} (0 = todos os municípios pesam igual; 1 = peso proporcional ao eleitorado)")
    tr.to_netcdf(os.path.join(MODELO, "ei_2022.nc"))
    np.savez(os.path.join(MODELO, "ei_2022_ref.npz"), media=ref[0], desvio=ref[1],
             logN_media=np.log(N).mean(), rhat_max=rhat_max, ess_min=ess_min, divergencias=div)

    B = betas(tr.posterior, g, w)
    taxas = taxas_por_faixa(B, x, N, g)
    taxas.to_csv(os.path.join(PAINEL, "taxas_ei_2022.csv"), index=False)

    # checagem: as taxas reproduzem o 2º turno nacional?
    proj = np.einsum("o,or,sorc->sc", N, x, B)
    real = (N[:, None]*y).sum(0)
    print("    2º turno nacional reconstruído (mediana) vs real: " + ", ".join(
        f"{dst} {np.median(proj[:, c])/1e6:.2f} mi / {real[c]/1e6:.2f} mi" for c, dst in enumerate(DESTINO)))

    v = taxas[taxas["destino"] == "lula_entre_votantes"]
    print("\n    fração para Lula entre quem passou a votar (origem 'fora') e entre a terceira via:")
    print(v.pivot(index="faixa", columns="origem", values=["p05", "mediana", "p95"]).reindex(ROTULOS).round(3).to_string())

    # lado a lado da faixa 45-55
    f = v[(v["faixa"] == "45-55%") & (v["origem"] == "fora")].iloc[0]
    diag["b_ei_mediana"] = np.where(diag["definicao_faixa"].str.startswith("1º"),
                                    diag["faixa"].map(v[v["origem"] == "fora"].set_index("faixa")["mediana"]), np.nan)
    diag["b_ei_p05"] = np.where(diag["definicao_faixa"].str.startswith("1º"),
                                diag["faixa"].map(v[v["origem"] == "fora"].set_index("faixa")["p05"]), np.nan)
    diag["b_ei_p95"] = np.where(diag["definicao_faixa"].str.startswith("1º"),
                                diag["faixa"].map(v[v["origem"] == "fora"].set_index("faixa")["p95"]), np.nan)
    diag.to_csv(os.path.join(PAINEL, "diagnostico_anomalia.csv"), index=False)
    print(f"\n    faixa 45-55%: EI dá {f['mediana']:.3f} (90%: {f['p05']:.3f} a {f['p95']:.3f})")

    if not args.sem_validacao:
        print("\n[3] validação fora da amostra (80/20)")
        val = validar(d, x, y, N, g, w, args.rapido)
        val.to_csv(os.path.join(PAINEL, "validacao_ei.csv"), index=False)
        print(val.round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
