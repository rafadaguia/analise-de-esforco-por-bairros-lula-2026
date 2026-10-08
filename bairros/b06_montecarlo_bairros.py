#!/usr/bin/env python3
"""Etapa B6: Monte Carlo dos cenários do 2º turno de 2026 por unidade (bairro), na GPU (MPS).

Mesma lógica de simulacao_montecarlo.py, uma unidade por linha em vez de um município:

  1. parâmetros: um sorteio do posterior da UF (b05) dá as taxas de cada unidade;
  2. resíduo (bootstrap): erro da margem de 2022 de uma unidade da mesma faixa, sorteado
     com reposição e somado à projeção;
  3. cenário: base (2022 se repete) ou direita (fração phi ~ U(0; 0,5) do que a terceira via
     transferia a Lula vai para o adversário). +2 pp de comparecimento onde a mediana do
     saldo da mobilização é positiva.

"Terreno perdido" da unidade: queda de Lula entre o 2º turno de 2022 e o 1º de 2026 além da
queda média nacional, em votos válidos de 2026 (com bootstrap da média nacional).

Unidade sem dado de 2022 (local de votação novo): efeito da unidade sorteado da priori
hierárquica (N(0, s_u)), não zero, para a incerteza ficar honesta.

Mais sorteios que amostras do posterior: o posterior é reamostrado com reposição; o resto da
variação vem do resíduo e do cenário.

Saídas em variantes/<U>/<M>/:
  unidades_mc.parquet   mediana e intervalo de 90% de cada parcela, por unidade
  grupos_mc.parquet     o mesmo somado por município, RM, UF, frente e país (soma por sorteio)

Uso: python bairros/b06_montecarlo_bairros.py --unidade U1 --metodo MC [--sorteios 10000]
"""
import argparse, glob, json, os, sys, time
import numpy as np
import pandas as pd
import torch
import xarray as xr

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ); sys.path.insert(0, os.path.join(RAIZ, "bairros"))
from inferencia_ecologica import ROTULOS, SEMENTE, faixa  # noqa: E402
from frentes import frente  # noqa: E402
import b05_ei_bairros as b5  # noqa: E402

DEV = "mps" if torch.backends.mps.is_available() else "cpu"
Q = torch.tensor([0.05, 0.5, 0.95])


def dados_2026(variante):
    a = b5.agregar(variante, 2026, turnos=(1,)).set_index("id_unidade")
    a2 = b5.agregar(variante, 2022, turnos=(2,)).set_index("id_unidade")
    un = pd.read_parquet(os.path.join(b5.VAR, variante, "unidades.parquet")).set_index("id_unidade")
    un["renda_resp"] = un["renda_resp_soma"] / un["resp_com_renda"]
    d = a.join(un[["renda_resp", "tipo", "nome", "municipio", "cd_mun_ibge"]], rsuffix="_u", how="left")
    d["validos"] = d["lula"] + d["adv"] + d["terc"]
    d = d[d["validos"] > 0].copy()
    d["lula_pct_26"] = 100*d["lula"]/d["validos"]
    d = d.join(a2[["lula", "adv"]].rename(columns={"lula": "lula_22_2t", "adv": "adv_22_2t"}), how="left")
    d["lula_pct_22_2t"] = 100*d["lula_22_2t"]/(d["lula_22_2t"] + d["adv_22_2t"])
    d["desloc"] = d["lula_pct_26"] - d["lula_pct_22_2t"]
    return d.reset_index()


def quantis(t):
    return torch.quantile(t.float().cpu(), Q, dim=0).numpy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unidade", default="U1"); ap.add_argument("--metodo", default="MC")
    ap.add_argument("--sorteios", type=int, default=10000); ap.add_argument("--bloco", type=int, default=1000)
    a = ap.parse_args()
    S = a.sorteios
    pasta = os.path.join(b5.VAR, a.unidade, a.metodo)
    rng = np.random.default_rng(SEMENTE + 7)
    torch.manual_seed(SEMENTE + 7)
    t0 = time.time()

    d22, x22, y22, N22 = b5.montar(a.unidade)
    d26 = dados_2026(a.unidade)
    ufs = sorted(os.path.basename(p)[5:7] for p in glob.glob(os.path.join(pasta, "post_??.nc")) if not p.endswith("post_BR.nc"))
    d26 = d26[d26["uf"].isin(ufs)].reset_index(drop=True)
    mun_nome = pd.read_csv(os.path.join(RAIZ, "painel", "painel_municipios.csv"), usecols=["cd_municipio_ibge", "municipio"]) \
        .dropna().astype({"cd_municipio_ibge": int}).set_index("cd_municipio_ibge")["municipio"]
    d26["municipio_tse"] = d26["cd_mun_ibge"].map(mun_nome)
    d26["frente"] = [frente(u, m) for u, m in zip(d26["uf"], d26["municipio_tse"])]
    n = len(d26)
    print(f"{n:,} unidades em {len(ufs)} UFs | {S:,} sorteios | {DEV}", flush=True)

    # ---------------- terreno perdido (não depende do modelo), bootstrap da média nacional
    ok = d26["desloc"].notna().to_numpy()
    des = np.nan_to_num(d26["desloc"].to_numpy(float)); val = d26["validos"].to_numpy(float)
    nac = np.average(des[ok], weights=val[ok])
    idx_ok = np.where(ok)[0]
    nac_b = np.empty(S)
    for i0 in range(0, S, 500):
        bi = idx_ok[rng.integers(0, len(idx_ok), size=(min(500, S - i0), len(idx_ok)))]
        nac_b[i0:i0 + len(bi)] = (des[bi]*val[bi]).sum(1)/val[bi].sum(1)
    terr = np.where(ok, np.maximum(-(des - nac), 0)/100*val, 0)
    print(f"queda média nacional (unidades): {nac:+.2f} pp (90%: {np.quantile(nac_b, .05):+.2f} a {np.quantile(nac_b, .95):+.2f})", flush=True)

    # ---------------- resíduos de 2022 por faixa (todas as UFs), mediana do posterior
    pools = {gi: [] for gi in range(len(ROTULOS))}

    res = {k: np.zeros((3, n), np.float32) for k in ("mob", "frac_lula_novos", "terc_base", "terc_dir", "margem_base", "margem_dir",
                                                       "lula2_base", "lula2_dir")}
    prob_rende = np.zeros(n, np.float32)
    # somas por grupo e sorteio (para intervalos de municípios, RMs, UFs, frentes e país)
    grupos = {"municipio": d26["cd_mun_ibge"].astype(str).to_numpy(), "rm": d26["nome_rm"].fillna("(fora de RM)").to_numpy(),
              "uf": d26["uf"].to_numpy(), "frente": d26["frente"].to_numpy(), "pais": np.array(["BR"]*n)}
    gidx = {k: np.unique(v, return_inverse=True) for k, v in grupos.items()}
    medidas = ("margem_base", "margem_dir", "mob", "terc_base", "terc_dir")
    gsum = {(k, m): np.zeros((S, len(gidx[k][0])), np.float32) for k in grupos for m in medidas}
    mob_all = np.zeros((S, n), np.float16)   # guardado para o potencial (precisa da mediana antes)
    phi = rng.uniform(0, 0.5, S)

    for uf in ufs:
        post = xr.open_dataset(os.path.join(pasta, f"post_{uf}.nc"))
        st = post.stack(s=("chain", "draw"))
        P = st.sizes["s"]
        dz = np.load(os.path.join(pasta, f"dados_{uf}.npz"))
        # categorias de município/RM do ajuste (mesma ordem de np.unique em b05.indices)
        sub22 = d22[d22["uf"] == uf].reset_index(drop=True)
        mun_cats = np.unique(sub22["cd_mun_ibge"].fillna("__nenhum__").astype(str))
        rm_cats = np.unique(sub22["nome_rm"].fillna("__nenhum__").astype(str))
        tem_rm = (rm_cats != "__nenhum__").astype(np.float32)
        multi = np.bincount(dz["mun"], minlength=len(mun_cats))[dz["mun"]] > 1
        u_pos = {iu: k for k, iu in enumerate(dz["ids"][multi])} if "z_u" in post else {}

        sel = np.where(d26["uf"].to_numpy() == uf)[0]
        du = d26.iloc[sel]
        L, Bv, T = (du[c].to_numpy(float) for c in ("lula", "adv", "terc"))
        N = du["aptos"].to_numpy(float)
        cnt = np.c_[L, Bv, T, np.maximum(N - L - Bv - T, 0)]
        g = faixa(pd.Series(100*L/(L + Bv + T))).cat.codes.to_numpy()
        renda = du["renda_resp"].where(du["renda_resp"] > 0).fillna(sub22["renda_resp"].median()).to_numpy()
        w, _ = b5.covariaveis(N, renda, (dz["ref_media"], dz["ref_desvio"]))
        m_i = np.searchsorted(mun_cats, du["cd_mun_ibge"].astype(str).to_numpy())
        m_i = np.where(mun_cats[np.minimum(m_i, len(mun_cats) - 1)] == du["cd_mun_ibge"].astype(str).to_numpy(), m_i, -1)
        r_i = np.searchsorted(rm_cats, du["nome_rm"].fillna("__nenhum__").astype(str).to_numpy())
        r_i = np.minimum(r_i, len(rm_cats) - 1)
        u_i = np.array([u_pos.get(i, -1) for i in du["id_unidade"]])

        # resíduos de 2022 desta UF (mediana do posterior) -> pools nacionais por faixa
        g22 = dz["g"]; x = dz["x"]; y = dz["y"]
        eta = torch.tensor(st["eta"].transpose("s", ...).values, device=DEV, dtype=torch.float32)       # s,f,r,2
        gam = torch.tensor(st["gamma"].transpose("s", ...).values, device=DEV, dtype=torch.float32)     # s,k,r,2
        V = lambda k: st[k].transpose("s", ...).values     # (as dimensões de s_* e z_* têm nomes diferentes no xarray)
        amun = torch.tensor(V("s_mun")[:, None, :] * V("z_mun"), device=DEV, dtype=torch.float32)    # s,m,2
        arm = torch.tensor(V("s_rm")[:, None, :] * V("z_rm"), device=DEV, dtype=torch.float32) * torch.tensor(tem_rm, device=DEV, dtype=torch.float32)[None, :, None]
        su = torch.tensor(st["s_u"].transpose("s", ...).values, device=DEV, dtype=torch.float32)        # s,2
        zu = torch.tensor(st["z_u"].transpose("s", ...).values, device=DEV, dtype=torch.float32)        # s,nu,2

        def taxas(idx_s, gg, ww, mm, rr, uu):
            e = eta[idx_s][:, gg] + torch.einsum("ok,skrc->sorc", torch.tensor(ww, device=DEV, dtype=torch.float32), gam[idx_s])
            mm_t = torch.tensor(np.maximum(mm, 0), device=DEV)
            am = amun[idx_s][:, mm_t]
            if (mm < 0).any():   # município sem dado em 2022: efeito sorteado da priori hierárquica
                smun = torch.tensor(st["s_mun"].transpose("s", ...).values, device=DEV, dtype=torch.float32)[idx_s]
                novo_m = torch.randn(len(idx_s), len(mm), 2, device=DEV) * smun[:, None, :]
                am = torch.where(torch.tensor(mm < 0, device=DEV)[None, :, None], novo_m, am)
            ar = arm[idx_s][:, torch.tensor(rr, device=DEV)]
            uu_t = torch.tensor(np.maximum(uu, 0), device=DEV)
            uv = zu[idx_s][:, uu_t] if zu.shape[1] > 0 else torch.zeros(len(idx_s), len(uu), 2, device=DEV)
            sem = torch.tensor(uu < 0, device=DEV)
            novo = torch.randn(len(idx_s), len(uu), 2, device=DEV)
            uv = torch.where(sem[None, :, None], novo, uv) * su[idx_s][:, None, :]
            lg = e + (am + ar + uv)[:, :, None, :]
            lg = torch.cat([lg, torch.zeros(lg.shape[:3] + (1,), device=DEV)], dim=3)
            return torch.softmax(lg, dim=3)                                          # s, obs, origem, destino

        # pools de resíduos com a mediana das taxas de 2022 (usa até 500 amostras do posterior)
        ss = torch.tensor(rng.choice(P, size=min(P, 500), replace=False), device=DEV)
        ids22 = dz["ids"]
        u22 = np.array([u_pos.get(i, -1) for i in ids22])
        B22 = taxas(ss, g22, dz["w"], dz["mun"], dz["rm"], u22)
        th = torch.einsum("or,sorc->soc", torch.tensor(x, device=DEV, dtype=torch.float32), B22)
        pred = torch.median(th[..., 0] - th[..., 1], dim=0).values.cpu().numpy()
        r22 = (y[:, 0] - y[:, 1]) - pred
        for gi in range(len(ROTULOS)):
            pools[gi].append(r22[g22 == gi])
        del B22, th

        cnt_t = torch.tensor(cnt, device=DEV, dtype=torch.float32)
        N_t = torch.tensor(N, device=DEV, dtype=torch.float32)
        T_t = torch.tensor(T, device=DEV, dtype=torch.float32)
        pool_uf = {gi: np.concatenate(pools[gi]) if len(np.concatenate(pools[gi])) else np.zeros(1) for gi in range(len(ROTULOS))}
        for i0 in range(0, S, a.bloco):
            b = min(a.bloco, S - i0)
            idx_s = torch.tensor(rng.integers(0, P, b), device=DEV)
            Bs = taxas(idx_s, g, w, m_i, r_i, u_i)
            proj = torch.einsum("or,borc->boc", cnt_t, Bs)
            rr = np.stack([pool_uf[gi][rng.integers(0, len(pool_uf[gi]), b)] for gi in g], axis=1)
            mb = proj[..., 0] - proj[..., 1] + torch.tensor(rr, device=DEV, dtype=torch.float32)*N_t
            c = Bs[:, :, 3, 0]/(Bs[:, :, 3, 0] + Bs[:, :, 3, 1])
            mob = 0.02*N_t*(2*c - 1)
            tb = T_t*(Bs[:, :, 2, 0] - Bs[:, :, 2, 1]); tl = T_t*Bs[:, :, 2, 0]
            ph = torch.tensor(phi[i0:i0 + b], device=DEV, dtype=torch.float32)[:, None]
            md, td = mb - 2*ph*tl, tb - 2*ph*tl
            vals = {"margem_base": mb, "margem_dir": md, "mob": mob, "terc_base": tb, "terc_dir": td}
            for (k, mname), arr in gsum.items():
                gi_ = torch.tensor(gidx[k][1][sel], device=DEV)
                acc = torch.zeros(b, arr.shape[1], device=DEV).index_add_(1, gi_, vals[mname])
                arr[i0:i0 + b] += acc.cpu().numpy()
            mob_all[i0:i0 + b, sel] = mob.cpu().numpy().astype(np.float16)
            # quantis por unidade: acumula as amostras da UF num tensor e resume no fim do loop da UF
            if i0 == 0:
                acum = {k: [] for k in res}
            # fatia de Lula entre os dois candidatos no 2º turno projetado (comparável ao MRP)
            dois = (proj[..., 0] + proj[..., 1]).clamp(min=1)
            l2b = ((proj[..., 0] + proj[..., 1] + mb)/2/dois).clamp(0, 1)
            l2d = ((proj[..., 0] + proj[..., 1] + md)/2/dois).clamp(0, 1)
            for k, v in (("mob", mob), ("frac_lula_novos", c), ("terc_base", tb), ("terc_dir", td),
                         ("margem_base", mb), ("margem_dir", md), ("lula2_base", l2b), ("lula2_dir", l2d)):
                acum[k].append(v.cpu().half())
        for k in res:
            full = torch.cat(acum[k]).float()
            res[k][:, sel] = torch.quantile(full, Q, dim=0).numpy() if full.shape[1] else 0
        prob_rende[sel] = (torch.cat(acum["mob"]).float() > 0).float().mean(0).numpy()
        del acum
        print(f"  {uf}: {len(sel):,} unidades | {time.time() - t0:.0f}s", flush=True)

    # ---------------- potencial (terreno + 2 pp onde a mobilização rende)
    rende = res["mob"][1] > 0
    pot_q = np.zeros((3, n), np.float32)
    terr_b_cols = []
    for i0 in range(0, n, 2000):
        sl = slice(i0, min(n, i0 + 2000))
        tb_ = np.where(ok[sl], np.maximum(-(des[sl][None] - nac_b[:, None]), 0)/100*val[sl][None], 0)
        pot = tb_ + np.where(rende[sl], mob_all[:, sl].astype(np.float32), 0)
        pot_q[:, sl] = np.quantile(pot, [.05, .5, .95], axis=0)
        terr_b_cols.append(tb_.astype(np.float32))
    terr_b = np.concatenate(terr_b_cols, axis=1)
    pot_draw_sum = {}
    for k in grupos:
        inv = gidx[k][1]
        mob_r = np.where(rende[None], mob_all.astype(np.float32), 0)
        tot = np.zeros((S, len(gidx[k][0])), np.float32)
        for gi_ in range(0, n, 4000):
            sl = slice(gi_, min(n, gi_ + 4000))
            np.add.at(tot.T, inv[sl], (terr_b[:, sl] + mob_r[:, sl]).T)
        pot_draw_sum[k] = tot

    out = d26[["id_unidade", "uf", "cd_mun_ibge", "municipio", "municipio_tse", "nome_rm", "frente", "tipo", "nome",
               "aptos", "validos", "lula", "adv", "terc", "lula_pct_26", "lula_pct_22_2t", "desloc"]].copy()
    out["terreno"] = terr
    for k, v in res.items():
        out[f"{k}_p05"], out[f"{k}_p50"], out[f"{k}_p95"] = v
    out["pot_p05"], out["pot_p50"], out["pot_p95"] = pot_q
    out["prob_mob_rende"] = prob_rende
    out.to_parquet(os.path.join(pasta, "unidades_mc.parquet"), index=False)

    linhas = []
    for k in grupos:
        cats = gidx[k][0]
        for mname in medidas:
            q = np.quantile(gsum[(k, mname)], [.05, .5, .95], axis=0)
            pp = (gsum[(k, mname)] > 0).mean(0)
            for j, cat in enumerate(cats):
                linhas.append({"nivel": k, "grupo": cat, "medida": mname, "p05": q[0, j], "mediana": q[1, j], "p95": q[2, j], "prob_positivo": pp[j]})
        q = np.quantile(pot_draw_sum[k], [.05, .5, .95], axis=0)
        for j, cat in enumerate(cats):
            linhas.append({"nivel": k, "grupo": cat, "medida": "potencial", "p05": q[0, j], "mediana": q[1, j], "p95": q[2, j], "prob_positivo": 1.0})
    pd.DataFrame(linhas).to_parquet(os.path.join(pasta, "grupos_mc.parquet"), index=False)
    json.dump({"sorteios": S, "dispositivo": DEV, "segundos": round(time.time() - t0), "nac_desloc": nac,
               "unidades": n, "ufs": ufs}, open(os.path.join(pasta, "mc_meta.json"), "w"))
    br = pd.DataFrame(linhas).query("nivel == 'pais'")
    print(br[["medida", "p05", "mediana", "p95"]].round(0).to_string(index=False))
    print(f"FIM {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
