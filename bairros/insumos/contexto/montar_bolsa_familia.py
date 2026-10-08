"""bolsa_familia.csv a partir do MiSocial/VIS DATA (MDS), nível municipal (tipo_s=mes_mu)."""
import json
from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parents[3]
SRC = BASE / "dados_bairros/outros/mds_misocial"
OUT = Path(__file__).resolve().parent
api = pd.DataFrame(json.load(open(BASE / "dados_bairros/outros/ibge_regioes_geograficas/ibge_api_municipios_nivelado.json")))
mapa = dict(zip(api["municipio-id"] // 10, api["municipio-id"]))

frames = []
for f in sorted(SRC.glob("misocial_mes_mu_*.csv")):
    frames.append(pd.read_csv(f, dtype={"codigo_ibge": int, "valor_repassado_bolsa_familia_s": str}))
d = pd.concat(frames)
d["cd_municipio_ibge"] = d.codigo_ibge.map(mapa)
assert d.cd_municipio_ibge.notna().all(), d[d.cd_municipio_ibge.isna()]
d["valor_repassado"] = pd.to_numeric(d.valor_repassado_bolsa_familia_s)
out = pd.DataFrame({
    "cd_municipio_ibge": d.cd_municipio_ibge.astype(int), "uf": d.sigla_uf, "anomes": d.anomes_s,
    "pbf_familias_beneficiarias": d.qtd_familias_beneficiarias_bolsa_familia_i,
    "pbf_pessoas_beneficiarias": d.qtd_pessoas_beneficiarias_bolsa_familia_i,
    "pbf_valor_repassado": d.valor_repassado,
    "pbf_valor_medio_familia": d.pbf_vlr_medio_benef_f.round(2),
    "pbf_valor_medio_calc": (d.valor_repassado / d.qtd_familias_beneficiarias_bolsa_familia_i).round(2),
    "cadunico_familias_cadastradas": d.cadun_qtd_familias_cadastradas_i,
    "cadunico_pessoas_cadastradas": d.cadun_qtd_pessoas_cadastradas_i,
    "cadunico_familias_pobreza": d.cadun_qtd_familias_cadastradas_pobreza_pbf_i,
    "cadunico_familias_baixa_renda": d.cadun_qtd_familias_cadastradas_baixa_renda_i,
    "cadunico_familias_acima_meio_sm": d.cadun_qtd_familias_cadastradas_rfpc_acima_meio_sm_i,
})
latest = out.anomes.max()
out[out.anomes == latest].sort_values("cd_municipio_ibge").to_csv(OUT / "bolsa_familia.csv", index=False)
out.sort_values(["anomes", "cd_municipio_ibge"]).to_csv(OUT / "bolsa_familia_meses.csv", index=False)
print(latest, out.groupby("anomes")[["pbf_familias_beneficiarias", "pbf_valor_repassado", "cadunico_familias_cadastradas"]].sum())
x = out[out.anomes == latest]
print((x.pbf_valor_medio_familia - x.pbf_valor_medio_calc).abs().describe())
