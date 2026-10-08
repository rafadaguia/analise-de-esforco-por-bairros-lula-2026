#!/usr/bin/env python3
"""Etapa B4a: perfil do Censo 2022 por setor censitário (só agregados públicos do IBGE).

Para cada setor: hierarquia territorial (bairro, subdistrito, distrito, município,
concentração urbana) e contagens que somam ao agregar em bairros:

  pop, pop_15m (15 anos ou mais), sexo x faixa etária (15+), cor ou raça,
  alfabetizados 15+, responsáveis com rendimento e soma do rendimento do responsável.

"X" no arquivo do IBGE é valor suprimido por sigilo estatístico: vira ausente (NaN),
nunca zero. Proporções são calculadas só sobre setores com o dado (as colunas
*_base guardam a população de referência efetivamente coberta).

Escolaridade (nível de ensino), religião e renda por faixa NÃO existem por setor no
Censo 2022 publicado até aqui: não são estimadas.

Saída: dados_bairros/proc/censo_setores.parquet
"""
import io, os, zipfile
import numpy as np
import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IBGE = os.path.join(RAIZ, "dados_bairros", "ibge")
PROC = os.path.join(RAIZ, "dados_bairros", "proc")

TERRIT = ["CD_SETOR", "SITUACAO", "AREA_KM2", "CD_UF", "CD_MUN", "NM_MUN", "CD_DIST", "NM_DIST", "CD_SUBDIST",
          "NM_SUBDIST", "CD_BAIRRO", "NM_BAIRRO", "CD_CONCURB", "NM_CONCURB", "CD_RGI", "NM_RGI"]


def ler(zipn, colunas=None):
    z = zipfile.ZipFile(os.path.join(IBGE, zipn))
    n = [x for x in z.namelist() if x.endswith(".csv")][0]
    raw = z.read(n)
    for enc in ("utf-8", "latin-1"):
        try:
            txt = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    d = pd.read_csv(io.StringIO(txt), sep=";", dtype=str, usecols=colunas)
    d.columns = [c.upper() if c.lower() == "cd_setor" else c for c in d.columns]
    return d


def num(d, cols):
    for c in cols:
        d[c] = pd.to_numeric(d[c].str.replace(",", ".", regex=False).replace("X", np.nan), errors="coerce")
    return d


def main():
    os.makedirs(PROC, exist_ok=True)
    b = ler("setores_basico_BR_20260520.zip")
    b = b[[c for c in TERRIT if c in b.columns] + ["v0001", "v0007"]].rename(columns={"v0001": "pop", "v0007": "domicilios"})
    b = num(b, ["pop", "domicilios", "AREA_KM2"])

    dem = num(ler("setores_demografia_BR.zip"), [f"V010{i:02d}" for i in range(6, 42)])
    # 15+ por sexo: faixas 15-19 a 70+ (V01012-V01019 masculino, V01023-V01030 feminino)
    idades = ["15_19", "20_24", "25_29", "30_39", "40_49", "50_59", "60_69", "70m"]
    s = pd.DataFrame({"CD_SETOR": dem["CD_SETOR"]})
    for i, f in enumerate(idades):
        s[f"m_{f}"] = dem[f"V010{12+i:02d}"]
        s[f"f_{f}"] = dem[f"V010{23+i:02d}"]
    s["pop_15m"] = dem[[f"V010{34+i:02d}" for i in range(8)]].sum(axis=1, min_count=8)
    s["homens_15m"] = s[[f"m_{f}" for f in idades]].sum(axis=1, min_count=8)
    s["mulheres_15m"] = s[[f"f_{f}" for f in idades]].sum(axis=1, min_count=8)

    cor = num(ler("setores_cor_ou_raca_BR.zip", ["CD_SETOR", "V01317", "V01318", "V01319", "V01320", "V01321"]),
              ["V01317", "V01318", "V01319", "V01320", "V01321"])
    cor = cor.rename(columns={"V01317": "branca", "V01318": "preta", "V01319": "amarela", "V01320": "parda",
                              "V01321": "indigena"})

    alf_cols = [f"V00{644+i}" for i in range(13)]
    alf = num(ler("setores_alfabetizacao_BR.zip", ["CD_setor"] + alf_cols), alf_cols)
    alf["alfabetizados_15m"] = alf[alf_cols].sum(axis=1, min_count=13)
    alf = alf[["CD_SETOR", "alfabetizados_15m"]]

    ren = num(ler("setores_renda_responsavel.zip"), ["V06001", "V06002", "V06004", "V06005", "V06006"])
    ren["resp_com_renda"] = ren["V06001"]
    # soma do rendimento = média x nº de responsáveis com rendimento (agregável); a mediana não agrega
    ren["renda_resp_soma"] = ren["V06004"] * ren["V06001"]
    ren["renda_resp_var"] = ren["V06005"]
    ren["renda_resp_mediana"] = ren["V06006"]
    ren = ren[["CD_SETOR", "resp_com_renda", "renda_resp_soma", "renda_resp_var", "renda_resp_mediana"]]

    d = b.merge(s, on="CD_SETOR", how="left").merge(cor, on="CD_SETOR", how="left") \
         .merge(alf, on="CD_SETOR", how="left").merge(ren, on="CD_SETOR", how="left")
    for c in ("CD_UF", "CD_MUN"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    # o arquivo do IBGE termina com linhas de nota (sem código de setor numérico)
    d = d[d["CD_MUN"].notna() & d["CD_SETOR"].str.fullmatch(r"\d{15}", na=False)]
    d.to_parquet(os.path.join(PROC, "censo_setores.parquet"), index=False)
    print(f"{len(d):,} setores | pop {d['pop'].sum():,.0f} | com bairro: {d['CD_BAIRRO'].notna().mean():.1%} dos setores, "
          f"{d.loc[d['CD_BAIRRO'].notna(), 'pop'].sum()/d['pop'].sum():.1%} da população")
    for c in ("pop_15m", "branca", "alfabetizados_15m", "resp_com_renda"):
        print(f"  {c:20s} setores sem o dado (sigilo): {d[c].isna().mean():.2%}, "
              f"pop desses setores {d.loc[d[c].isna(), 'pop'].sum()/d['pop'].sum():.2%}")


if __name__ == "__main__":
    main()
