#!/usr/bin/env python3
"""Etapa B21c: indicadores de necessidade local para os subtemas, por área e por município.

Área (Censo 2022 por setor, somado na área; CNES com coordenadas):
  pct_0a4, pct_15a24, pct_60m, pct_70m       parte da população em cada faixa de idade (0-4: Censo, demografia V01031)
  analfab_15m                                 % de pessoas de 15+ que não sabem ler e escrever
  renda_resp                                  renda média do responsável pelo domicílio (R$)
  sem_esgoto, sem_agua, sem_lixo, favela      infraestrutura (b04d)
  rural                                       % da população em setores rurais
  ubs_dist_km, urgencia_dist_km               distância do centro populacional da área à UBS e ao pronto-atendimento mais
                                              próximos (CNES: tipos 01/02/32/71/72 e 05/15/20/21/73)
  ubs_por_10mil                               UBS dentro da área por 10 mil moradores
Município:
  especialidade_por_100mil, caps_por_100mil   policlínicas e centros de especialidade (tipos 04/36) e CAPS (70) por 100 mil hab.
  creche_cobertura                            matrículas em creche (INEP 2024) por criança de 0 a 3 anos (0,8 x 0-4 do Censo)
  integral_pct                                % das matrículas do fundamental e médio em tempo integral (INEP 2024)
  escolas_sem_internet_pct                    % das escolas públicas em funcionamento sem internet para os alunos (INEP 2024)
  bf_pct, pobreza_cadunico                    famílias no Bolsa Família / domicílios; famílias em pobreza no CadÚnico / domicílios
  caged_var                                   variação % do emprego formal em 12 meses (Novo CAGED)
  agro_familiar_pct, agro_sem_ater_pct,       Censo Agropecuário 2017: estabelecimentos da agricultura familiar (% do total), % sem
  agro_sem_energia_pct                        orientação técnica e % sem energia elétrica entre os familiares
  eua_agro/ind/petroleo_por_eleitor           exportações aos EUA em 2025 (Comex Stat, SH4) por eleitor, por grupo de produto
  amazonia                                    1 se Amazônia Legal
Saídas: variantes/<U>/subtemas_ind_area.parquet e subtemas_ind_municipio.parquet
"""
import json, os, sys, zipfile, glob
import numpy as np
import pandas as pd
import duckdb
from sklearn.neighbors import BallTree

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(RAIZ, "dados_bairros", "proc")
SUB = os.path.join(RAIZ, "dados_bairros", "subtemas")
R_TERRA = 6371.0
UBS, URG, ESP, CAPS = {"01", "02", "32", "71", "72"}, {"05", "15", "20", "21", "73"}, {"04", "36"}, {"70"}
AGRO = ("0901", "0201", "0202", "0206", "0207", "0210", "1602", "2009", "0804", "0805", "0806", "0810", "0302", "0303", "0304",
        "1701", "2401", "4401", "4403", "4407", "4409", "1801", "0306")
IND = ("72", "73", "84", "85", "86", "87", "88", "64", "40", "94", "48", "47", "28", "29", "39", "76")
PETRO = ("2709", "2710", "2711", "2713")


def main():
    uni = sys.argv[1] if len(sys.argv) > 1 else "U4"
    pasta = os.path.join(RAIZ, "variantes", uni)
    un = pd.read_parquet(os.path.join(pasta, "unidades.parquet"), columns=["id_unidade", "cd_mun_ibge", "uf", "pop", "eleitores_2026"])
    su = pd.read_parquet(os.path.join(pasta, "setor_unidade.parquet"), columns=["CD_SETOR", "id_unidade"]).drop_duplicates("CD_SETOR")
    cs = pd.read_parquet(os.path.join(PROC, "censo_setores.parquet"))
    cs["CD_SETOR"] = cs["CD_SETOR"].astype(str)
    su["CD_SETOR"] = su["CD_SETOR"].astype(str)
    # setores de áreas pequenas fundidas à vizinha (b04): seguem para a área de destino, como em b04b
    lu = pd.read_parquet(os.path.join(pasta, "local_unidade.parquet"), columns=["id_unidade_original", "id_unidade"]).dropna()
    fusao = dict(zip(lu["id_unidade_original"], lu["id_unidade"]))
    su["id_unidade"] = su["id_unidade"].map(lambda x: fusao.get(x, x))
    # 0 a 4 anos (Censo, demografia)
    z = zipfile.ZipFile(os.path.join(RAIZ, "dados_bairros", "ibge", "setores_demografia_BR.zip"))
    nm = z.namelist()[0]
    with z.open(nm) as f:
        d04 = pd.read_csv(f, sep=";", usecols=["CD_setor", "V01031"], dtype=str, encoding="latin-1")
    d04["CD_SETOR"] = d04["CD_setor"].str.strip(); d04["c04"] = pd.to_numeric(d04["V01031"], errors="coerce")
    cs = cs.merge(d04[["CD_SETOR", "c04"]], on="CD_SETOR", how="left")
    cs["p15a24"] = cs[["m_15_19", "f_15_19", "m_20_24", "f_20_24"]].sum(axis=1)
    cs["p60m"] = cs[["m_60_69", "f_60_69", "m_70m", "f_70m"]].sum(axis=1)
    cs["p70m"] = cs[["m_70m", "f_70m"]].sum(axis=1)
    cs["pop_rural"] = np.where(cs["SITUACAO"] == "Rural", cs["pop"], 0)
    s = su.merge(cs, on="CD_SETOR", how="left")
    ag = s.groupby("id_unidade").agg(pop=("pop", "sum"), c04=("c04", "sum"), p15a24=("p15a24", "sum"), p60m=("p60m", "sum"),
                                     p70m=("p70m", "sum"), pop15=("pop_15m", "sum"), alf=("alfabetizados_15m", "sum"),
                                     rr=("renda_resp_soma", "sum"), nr=("resp_com_renda", "sum"), prur=("pop_rural", "sum"))
    a = pd.DataFrame(index=ag.index)
    for c, src in (("pct_0a4", "c04"), ("pct_15a24", "p15a24"), ("pct_60m", "p60m"), ("pct_70m", "p70m"), ("rural", "prur")):
        a[c] = 100 * ag[src] / ag["pop"].replace(0, np.nan)
    a["analfab_15m"] = 100 * (1 - ag["alf"] / ag["pop15"].replace(0, np.nan))
    a["renda_resp"] = ag["rr"] / ag["nr"].replace(0, np.nan)
    inf = pd.read_parquet(os.path.join(pasta, "infra_areas.parquet")).set_index("id_unidade")
    a = a.join(inf.rename(columns={"pct_sem_esgoto_adequado": "sem_esgoto", "pct_sem_agua_rede": "sem_agua",
                                   "pct_sem_coleta_lixo": "sem_lixo", "pct_pop_favela": "favela"}))
    # CNES: estabelecimentos ativos com coordenada no Brasil (inclui Fernando de Noronha, lon -32)
    pt = pd.read_parquet(os.path.join(PROC, "setores_pontos.parquet")); pt["CD_SETOR"] = pt["CD_SETOR"].astype(str)
    pt = pt.merge(cs[["CD_SETOR", "pop"]], on="CD_SETOR", how="left"); pt["pop"] = pt["pop"].fillna(0)
    zc = zipfile.ZipFile(os.path.join(SUB, "cnes_estabelecimentos.zip"))
    with zc.open(zc.namelist()[0]) as f:
        cn = pd.read_csv(f, sep=";", dtype=str, encoding="latin-1",
                         usecols=["CO_CNES", "CO_IBGE", "TP_UNIDADE", "NU_LATITUDE", "NU_LONGITUDE", "CO_MOTIVO_DESAB", "CO_AMBULATORIAL_SUS"])
    cn = cn[cn["CO_MOTIVO_DESAB"].isna()].copy()
    cn["tp"] = cn["TP_UNIDADE"].str.zfill(2)
    cn["lat"] = pd.to_numeric(cn["NU_LATITUDE"], errors="coerce"); cn["lon"] = pd.to_numeric(cn["NU_LONGITUDE"], errors="coerce")
    ok = cn["lat"].between(-34, 6) & cn["lon"].between(-74, -28)
    # coordenada conferida: o estabelecimento precisa estar a até 30 km de algum setor do próprio município
    # (coordenadas trocadas ou do município errado deixam de contar nas distâncias)
    pt["m6"] = pt["CD_SETOR"].str[:6]
    longe = pd.Series(False, index=cn.index)
    for m6_, g in cn[ok].groupby("CO_IBGE"):
        ps = pt[pt["m6"] == m6_]
        if len(ps) == 0:
            continue
        dd, _ = BallTree(np.radians(ps[["lat", "lon"]].to_numpy()), metric="haversine").query(np.radians(g[["lat", "lon"]].to_numpy()), k=1)
        longe.loc[g.index] = dd[:, 0] * R_TERRA > 30
    print(f"CNES ativos: {len(cn):,}; coordenada válida: {ok.sum():,}; descartados por estarem fora do município: {longe.sum():,}")
    cn["geo_ok"] = ok & ~longe

    def sel(tipos):
        e = cn[cn["geo_ok"] & cn["tp"].isin(tipos)]
        return e[e["CO_AMBULATORIAL_SUS"].fillna("").str.upper().eq("SIM") | (e["tp"] != "01")]
    ubs, urg = sel(UBS), sel(URG)
    # por setor: distância ao mais próximo e postos a até 2 km por 10 mil moradores a até 2 km; área = média pelos moradores
    xyz = np.radians(pt[["lat", "lon"]].to_numpy())
    for nome, e in (("ubs_dist_km", ubs), ("urgencia_dist_km", urg)):
        dd, _ = BallTree(np.radians(e[["lat", "lon"]].to_numpy()), metric="haversine").query(xyz, k=1)
        pt[nome] = dd[:, 0] * R_TERRA
    r2 = 2 / R_TERRA
    pt["ubs_2km"] = BallTree(np.radians(ubs[["lat", "lon"]].to_numpy()), metric="haversine").query_radius(xyz, r2, count_only=True)
    bts = BallTree(xyz, metric="haversine"); popv = pt["pop"].to_numpy(); pop2 = np.zeros(len(pt))
    for k0 in range(0, len(pt), 20000):
        idx = bts.query_radius(xyz[k0:k0 + 20000], r2)
        pop2[k0:k0 + 20000] = [popv[ix].sum() for ix in idx]
    pt["ubs_por_10mil"] = 1e4 * pt["ubs_2km"] / np.maximum(pop2, 1)
    sp = su.merge(pt, on="CD_SETOR")
    sp["w"] = sp["pop"].clip(lower=1)
    for c in ("ubs_dist_km", "urgencia_dist_km", "ubs_por_10mil"):
        a[c] = (sp[c] * sp["w"]).groupby(sp["id_unidade"]).sum() / sp.groupby("id_unidade")["w"].sum()
    # só as áreas do mapa; as residuais (locais não localizados, sem setor) recebem os valores da cidade
    a = a.reindex(un["id_unidade"])
    a.index.name = "id_unidade"
    a = a.join(un.set_index("id_unidade")[["cd_mun_ibge", "uf"]])
    sp["m"] = sp["CD_SETOR"].str[:7]
    cols_area = [c for c in a.columns if c not in ("cd_mun_ibge", "uf")]
    a["ind_da_cidade"] = a["pct_0a4"].isna()
    st_m = sp.assign(w=sp["pop"]).groupby("m")
    cid = pd.DataFrame({c: a.groupby(a["cd_mun_ibge"].astype("Int64").astype(str))[c].mean() for c in cols_area})
    for c in cols_area:
        a.loc[a["ind_da_cidade"], c] = a.loc[a["ind_da_cidade"], "cd_mun_ibge"].astype("Int64").astype(str).map(cid[c])
    a.reset_index().to_parquet(os.path.join(pasta, "subtemas_ind_area.parquet"), index=False)
    print(f"áreas: {len(a):,} (com valores da cidade: {int(a['ind_da_cidade'].sum())})"); print(a.describe().T[["mean", "50%"]].round(2).to_string())

    # ------------------------------------------------------------------ municípios
    popm = cs.assign(m=cs["CD_MUN"].astype("Int64").astype(str)).groupby("m").agg(pop=("pop", "sum"), c04=("c04", "sum"), dom=("domicilios", "sum"))
    m = pd.DataFrame(index=popm.index)
    cn["m"] = cn["CO_IBGE"].astype(str).str[:6]
    m6 = pd.Series(popm.index.str[:6], index=popm.index)
    for nome, tipos in (("especialidade_por_100mil", ESP), ("caps_por_100mil", CAPS)):
        c = cn[cn["tp"].isin(tipos)].groupby("m").size()
        m[nome] = 1e5 * m6.map(c).fillna(0) / popm["pop"].replace(0, np.nan)
    zi = zipfile.ZipFile(os.path.join(SUB, "microdados_censo_escolar_2024.zip"))
    nm = [n for n in zi.namelist() if n.endswith("microdados_ed_basica_2024.csv")][0]
    cols = ["CO_MUNICIPIO", "TP_DEPENDENCIA", "TP_SITUACAO_FUNCIONAMENTO", "IN_INTERNET_ALUNOS", "QT_MAT_INF_CRE", "QT_MAT_FUND",
            "QT_MAT_FUND_INT", "QT_MAT_MED", "QT_MAT_MED_INT"]
    with zi.open(nm) as f:
        es = pd.read_csv(f, sep=";", usecols=cols, dtype=str, encoding="latin-1")
    for c in cols[3:]:
        es[c] = pd.to_numeric(es[c], errors="coerce").fillna(0)
    es = es[es["TP_SITUACAO_FUNCIONAMENTO"] == "1"]
    g = es.groupby("CO_MUNICIPIO")
    m["creche_cobertura"] = 100 * g["QT_MAT_INF_CRE"].sum().reindex(m.index) / (0.8 * popm["c04"]).replace(0, np.nan)
    m["integral_pct"] = 100 * (g["QT_MAT_FUND_INT"].sum() + g["QT_MAT_MED_INT"].sum()).reindex(m.index) / \
        (g["QT_MAT_FUND"].sum() + g["QT_MAT_MED"].sum()).reindex(m.index).replace(0, np.nan)
    pub = es[es["TP_DEPENDENCIA"].isin(["1", "2", "3"])].groupby("CO_MUNICIPIO")["IN_INTERNET_ALUNOS"]
    m["escolas_sem_internet_pct"] = 100 * (1 - pub.mean()).reindex(m.index)
    ctx = os.path.join(RAIZ, "bairros", "insumos", "contexto")
    bf = pd.read_csv(os.path.join(ctx, "bolsa_familia.csv"), dtype={"cd_municipio_ibge": str}).sort_values("anomes").groupby("cd_municipio_ibge").last()
    m["bf_pct"] = 100 * bf["pbf_familias_beneficiarias"].reindex(m.index) / popm["dom"].replace(0, np.nan)
    m["pobreza_cadunico"] = 100 * bf["cadunico_familias_pobreza"].reindex(m.index) / popm["dom"].replace(0, np.nan)
    cg = pd.read_csv(os.path.join(ctx, "caged.csv"), dtype={"cd_municipio_ibge": str})
    m["caged_var"] = cg[cg["periodo"].str.startswith("12m")].set_index("cd_municipio_ibge")["variacao_relativa_pct"].reindex(m.index)
    # Censo Agropecuário 2017
    def agro(prefixo, chave_cat, alvo):
        tot, fam, fam_alvo = {}, {}, {}
        for f in glob.glob(os.path.join(SUB, "agro", f"{prefixo}_*.json")):
            for v in json.load(open(f)):
                for r in v["resultados"]:
                    cl = {c["id"]: list(c["categoria"].keys())[0] for c in r["classificacoes"]}
                    for sr in r["series"]:
                        mun = sr["localidade"]["id"]; val = sr["serie"]["2017"]
                        val = 0.0 if val in ("-", "X", "...", "..") else float(val)
                        fam_ = cl["829"] == "46304"; al = cl[chave_cat] == alvo
                        if not fam_ and not al: tot[mun] = tot.get(mun, 0) + val
                        if fam_ and not al: fam[mun] = fam.get(mun, 0) + val
                        if fam_ and al: fam_alvo[mun] = fam_alvo.get(mun, 0) + val
        return pd.Series(tot), pd.Series(fam), pd.Series(fam_alvo)
    tot, fam, ater = agro("ater", "12567", "113111")
    m["agro_familiar_pct"] = 100 * fam.reindex(m.index) / tot.reindex(m.index).replace(0, np.nan)
    m["agro_sem_ater_pct"] = 100 * (1 - ater.reindex(m.index) / fam.reindex(m.index).replace(0, np.nan))
    _, fam_e, sem_e = agro("energia", "309", "3018")
    m["agro_sem_energia_pct"] = 100 * sem_e.reindex(m.index) / fam_e.reindex(m.index).replace(0, np.nan)
    # Comex Stat: exportações aos EUA em 2025 por grupo de produto
    cx = pd.DataFrame(json.load(open(os.path.join(RAIZ, "dados_bairros", "outros", "comexstat", "exp_2025_eua_sh4.json")))["data"]["list"])
    cx["fob"] = pd.to_numeric(cx["metricFOB"], errors="coerce")
    cx["grupo"] = np.where(cx["headingCode"].isin(PETRO), "petroleo", np.where(cx["headingCode"].isin(AGRO), "agro",
                           np.where(cx["headingCode"].str[:2].isin(IND), "ind", "outro")))
    sob = pd.read_csv(os.path.join(ctx, "soberania_municipios.csv"), dtype={"cd_municipio_ibge": str})
    import unicodedata
    norm = lambda x: "".join(c for c in unicodedata.normalize("NFKD", str(x).lower()) if c.isalnum())
    sob["chave"] = sob["municipio"].map(norm) + "-" + sob["uf"]
    cx["chave"] = cx["noMunMinsgUf"].str.rsplit(" - ", n=1).str[0].map(norm) + "-" + cx["noMunMinsgUf"].str.rsplit(" - ", n=1).str[1]
    piv = cx.pivot_table(index="chave", columns="grupo", values="fob", aggfunc="sum").fillna(0)
    sob = sob.set_index("chave").join(piv)
    sob = sob.set_index("cd_municipio_ibge")
    for g_ in ("agro", "ind", "petroleo"):
        m[f"eua_{g_}_por_eleitor"] = (sob[g_] / sob["aptos_26"].replace(0, np.nan)).reindex(m.index).fillna(0) if g_ in sob else 0
    m["amazonia"] = sob["amazonia_legal"].astype(float).reindex(m.index).fillna(0)
    m.index.name = "cd_mun_ibge"
    m.reset_index().to_parquet(os.path.join(pasta, "subtemas_ind_municipio.parquet"), index=False)
    print(f"municípios: {len(m):,}"); print(m.describe().T[["count", "mean", "50%"]].round(2).to_string())


if __name__ == "__main__":
    main()
