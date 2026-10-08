"""caged.csv a partir das tabelas oficiais do Novo CAGED (MTE), arquivo '3-tabelas_Agosto de 2026.xlsx'.
- 12 meses (set/25-ago/26, com ajustes): Tabela 3.
- Ano 2025 (com ajustes): soma jan-dez/2025 da Tabela 8.1; estoque = estoque de dez/2025.
- Estoque do 12m = estoque de ago/2026 da Tabela 8.1."""
import json
from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parents[3]
F = BASE / "dados_bairros/outros/mte_novo_caged_tabelas/3-tabelas_Agosto_de_2026.xlsx"
OUT = Path(__file__).resolve().parent
api = pd.DataFrame(json.load(open(BASE / "dados_bairros/outros/ibge_regioes_geograficas/ibge_api_municipios_nivelado.json")))
mapa = dict(zip(api["municipio-id"] // 10, api["municipio-id"]))

t3 = pd.read_excel(F, sheet_name="Tabela 3", header=None, skiprows=6)
t3 = t3[pd.to_numeric(t3[2], errors="coerce").notna()]
assert "Set/25 a Ago/26" in str(pd.read_excel(F, sheet_name="Tabela 3", header=None, nrows=5).iloc[4, 12])
d12 = pd.DataFrame({"cd6": t3[2].astype(int), "uf": t3[1], "admissoes": t3[12], "desligamentos": t3[13], "saldo": t3[14],
                    "variacao_relativa_pct": t3[15]})

h = pd.read_excel(F, sheet_name="Tabela 8.1", header=None, nrows=6)
t8 = pd.read_excel(F, sheet_name="Tabela 8.1", header=None, skiprows=6)
t8 = t8[pd.to_numeric(t8[2], errors="coerce").notna()]
meses = h.iloc[4].ffill()
def cols(mes, var):
    return [c for c in t8.columns if c >= 4 and meses[c] == mes and h.iloc[5, c] == var]
nomes_2025 = [f"{m}/2025" for m in ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto",
                                     "Setembro", "Outubro", "Novembro", "Dezembro"]]
assert all(cols(m, "Saldos") for m in nomes_2025), "meses 2025 ausentes"
def soma(var):
    return t8[[cols(m, var)[0] for m in nomes_2025]].apply(pd.to_numeric).sum(axis=1)
d25 = pd.DataFrame({"cd6": t8[2].astype(int), "uf": t8[1], "admissoes": soma("Admissões"),
                    "desligamentos": soma("Desligamentos"), "saldo": soma("Saldos"),
                    "estoque": pd.to_numeric(t8[cols("Dezembro/2025", "Estoque")[0]])})
est_ago26 = dict(zip(t8[2].astype(int), pd.to_numeric(t8[cols("Agosto/2026", "Estoque")[0]])))
d12["estoque"] = d12.cd6.map(est_ago26)
# confere: soma dos saldos 12m da 8.1 = Tabela 3
m12 = ["Setembro/2025", "Outubro/2025", "Novembro/2025", "Dezembro/2025"] + [f"{m}/2026" for m in
       ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto"]]
chk = t8[[cols(m, "Saldos")[0] for m in m12]].apply(pd.to_numeric).sum(axis=1)
dif = (pd.Series(chk.values, index=t8[2].astype(int)) - d12.set_index("cd6").saldo).abs()
print("diferença máx 8.1 x Tabela 3 (saldo 12m):", dif.max())

d12["periodo"] = "12m_2025-09_a_2026-08"
d25["periodo"] = "ano_2025"
d25["variacao_relativa_pct"] = pd.NA
out = pd.concat([d12, d25])
out["cd_municipio_ibge"] = out.cd6.map(mapa)
print("sem correspondência IBGE:", out[out.cd_municipio_ibge.isna()].cd6.unique())
out = out.dropna(subset=["cd_municipio_ibge"])
out["cd_municipio_ibge"] = out.cd_municipio_ibge.astype(int)
out["estoque_referencia"] = out.periodo.map({"12m_2025-09_a_2026-08": "2026-08", "ano_2025": "2025-12"})
out = out[["cd_municipio_ibge", "uf", "periodo", "admissoes", "desligamentos", "saldo", "estoque", "estoque_referencia", "variacao_relativa_pct"]]
for c in ["admissoes", "desligamentos", "saldo", "estoque"]:
    out[c] = pd.to_numeric(out[c]).astype("Int64")
out.sort_values(["periodo", "cd_municipio_ibge"]).to_csv(OUT / "caged.csv", index=False)
print(out.groupby("periodo")[["admissoes", "desligamentos", "saldo", "estoque"]].sum())
print(out.groupby("periodo").size())
