"""Monta rm.csv, rm_longo.csv e regioes_geograficas.csv a partir dos arquivos oficiais do IBGE
baixados em dados_bairros/outros/ibge_rm e dados_bairros/outros/ibge_regioes_geograficas."""
import json, re
from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parents[3]
RM = BASE / "dados_bairros/outros/ibge_rm/Composicao_RM_2025.xlsx"
RG = BASE / "dados_bairros/outros/ibge_regioes_geograficas"
OUT = Path(__file__).resolve().parent

api = pd.DataFrame(json.load(open(RG / "ibge_api_municipios_nivelado.json")))
mun = api.rename(columns={"municipio-id": "cd_municipio_ibge", "municipio-nome": "nome_municipio",
                          "UF-sigla": "uf"})[["cd_municipio_ibge", "nome_municipio", "uf"]]

# ---- Regiões geográficas (API de localidades = composição vigente; xlsx 2017 = publicação original)
rg = api.rename(columns={"municipio-id": "cd_municipio_ibge", "municipio-nome": "nome_municipio", "UF-sigla": "uf",
                         "regiao-imediata-id": "cd_rgi", "regiao-imediata-nome": "nome_rgi",
                         "regiao-intermediaria-id": "cd_rgint", "regiao-intermediaria-nome": "nome_rgint",
                         "regiao-nome": "grande_regiao"})
rg = rg[["cd_municipio_ibge", "nome_municipio", "uf", "grande_regiao", "cd_rgi", "nome_rgi", "cd_rgint", "nome_rgint"]]
x17 = pd.read_excel(RG / "regioes_geograficas_composicao_por_municipios_2017_20180911.xlsx")
chk = rg.merge(x17, left_on="cd_municipio_ibge", right_on="CD_GEOCODI", how="left")
rg["igual_tabela_2017"] = (chk["cod_rgi"] == chk["cd_rgi"]) & (chk["cod_rgint"] == chk["cd_rgint"])
rg.sort_values("cd_municipio_ibge").to_csv(OUT / "regioes_geograficas.csv", index=False)

# ---- Recortes metropolitanos 2025
def tipo(nome):
    n = nome.strip()
    if n.startswith("Região Metropolitana"):
        return "RM"
    if "Integrada de Desenvolvimento" in n:
        return "RIDE"
    return "RM"  # colar / área de expansão / entorno: partes de recortes de RM

def parte(cat, sub):
    c = cat.strip()
    if c.startswith("Região"):
        return "integrante" if sub == "NÃO TEM" else sub
    return c  # Colar Metropolitano, Área de Expansão Metropolitana, Entorno ...

m = pd.read_excel(RM, sheet_name=0)
lm = pd.DataFrame({
    "cd_municipio_ibge": m.COD_MUN, "uf": m.SIGLA_UF,
    "nome_rm": m.LABEL_CATMETROPOL.str.strip(),
    "nome_oficial": m.NOME_CATMETROPOL.str.strip(),
    "recorte": m.LABEL_RECMETROPOL.str.strip(),
    "tipo": m.NOME_CATMETROPOL.map(tipo),
    "categoria": [parte(c, s) for c, s in zip(m.NOME_CATMETROPOL, m.NOME_SUBCATMETROPOL)],
    "legislacao": m.LEG.astype(str).str.replace(r"\s+", " ", regex=True).str.strip(),
    "data_legislacao": m.DATA.astype(str),
})
# colar/área de expansão/entorno: nome_rm passa a ser a RM do recorte
mask = ~m.NOME_CATMETROPOL.str.strip().str.startswith("Região")
lm.loc[mask, "nome_rm"] = "RM de " + lm.loc[mask, "recorte"]
a = pd.read_excel(RM, sheet_name=1)
la = pd.DataFrame({
    "cd_municipio_ibge": a.COD_MUN, "uf": a.SIGLA_UF, "nome_rm": a.LABEL_CATAU.str.strip(),
    "nome_oficial": a.NOME_CATAU.str.strip(), "recorte": a.LABEL_RECAU.str.strip(), "tipo": "AU",
    "categoria": ["integrante" if s == "NÃO TEM" else s for s in a.NOME_SUBCATAU],
    "legislacao": a.LEG.astype(str).str.replace(r"\s+", " ", regex=True).str.strip(),
    "data_legislacao": a.DATA.astype(str)})
longo = pd.concat([lm, la])
# São Paulo aparece em 5 sub-regiões da RMSP: consolida
longo = (longo.groupby(["cd_municipio_ibge", "uf", "nome_rm", "nome_oficial", "recorte", "tipo", "legislacao", "data_legislacao"],
                       as_index=False).agg(categoria=("categoria", lambda s: "; ".join(sorted(set(s))))))
longo["data_referencia"] = "2025-12-31"
longo.sort_values(["cd_municipio_ibge", "tipo", "nome_rm"]).to_csv(OUT / "rm_longo.csv", index=False)

ordem = {"RM": 0, "RIDE": 1, "AU": 2}
longo["_o"] = longo.tipo.map(ordem)
g = longo.sort_values(["cd_municipio_ibge", "_o", "nome_rm"]).groupby("cd_municipio_ibge")
wide = g.agg(nome_rm=("nome_rm", "first"), tipo=("tipo", "first"), categoria=("categoria", "first"),
             n_arranjos=("nome_rm", "size"),
             todos_arranjos=("nome_rm", lambda s: " | ".join(s))).reset_index()
wide = mun.merge(wide, on="cd_municipio_ibge", how="left")
wide["n_arranjos"] = wide.n_arranjos.fillna(0).astype(int)
wide["data_referencia"] = "2025-12-31"
wide = wide[["cd_municipio_ibge", "nome_municipio", "uf", "nome_rm", "tipo", "categoria", "n_arranjos", "todos_arranjos", "data_referencia"]]
wide.sort_values("cd_municipio_ibge").to_csv(OUT / "rm.csv", index=False)
print(wide.tipo.value_counts(dropna=False)); print((wide.n_arranjos > 1).sum(), "municípios em >1 arranjo")
print(rg.igual_tabela_2017.value_counts())
