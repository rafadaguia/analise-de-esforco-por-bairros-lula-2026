#!/usr/bin/env python3
"""Etapa B04g: subdistritos com o nome oficial do IBGE (Censo 2022).

A conferência de nomes (b04e) trocava o nome de algumas áreas pelo lugar mais próximo do OpenStreetMap. Em subdistritos
(regiões administrativas do DF, distritos de São Paulo, regionais de Contagem etc.), o nome que os moradores reconhecem é
o oficial: Ceilândia, e não "Setor de Materiais de Construção e arredores"; Grajaú, e não "Jardim São Nicolau e
arredores". Aqui, a área de subdistrito recebe o nome oficial do subdistrito onde mora a maior parte da sua população,
salvo quando o nome oficial é genérico ("1º Subdistrito", "Zona 04", "Região Administrativa 2"). Se duas áreas do mesmo
município ficariam com o mesmo nome, a segunda mantém o nome anterior.

Saída: atualiza a coluna nome de variantes/<U>/unidades.parquet (a anterior fica em nome_antes_oficial) e grava
variantes/<U>/nomes_oficiais.csv com as trocas.
"""
import os, re, sys
import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERICO = re.compile(r"subdistrito|^zona\b|zona rural|regi[aã]o administrativa|^\d|^distrito\b|^sede$|^setor \d|"
                      r"^(norte|sul|leste|oeste|centro|central)$", re.I)
norm = lambda s: "".join(c for c in __import__("unicodedata").normalize("NFKD", str(s).lower()) if c.isalnum())
LIMPA = re.compile(r"^(U\.?T\.?P\.?|MZ\s*\d+\s*-|Administração Regional)\s*", re.I)   # prefixos de planejamento


def main():
    uni = sys.argv[1] if len(sys.argv) > 1 else "U4"
    arq = os.path.join(RAIZ, "variantes", uni, "unidades.parquet")
    un = pd.read_parquet(arq)
    su = pd.read_parquet(os.path.join(RAIZ, "variantes", uni, "setor_unidade.parquet"))
    cs = pd.read_parquet(os.path.join(RAIZ, "dados_bairros", "proc", "censo_setores.parquet"), columns=["CD_SETOR", "NM_SUBDIST", "NM_DIST", "pop"])
    # sem subdistrito (ex.: distritos de São Paulo), vale o nome do distrito
    cs["NM_SUBDIST"] = cs["NM_SUBDIST"].fillna(cs["NM_DIST"])
    su["CD_SETOR"] = su["CD_SETOR"].astype(str); cs["CD_SETOR"] = cs["CD_SETOR"].astype(str)
    x = su[su["id_unidade"].str.match(r"^S\d{11}$")].merge(cs, on="CD_SETOR")
    of = x.dropna(subset=["NM_SUBDIST"]).groupby(["id_unidade", "NM_SUBDIST"])["pop"].sum().reset_index() \
        .sort_values("pop", ascending=False).drop_duplicates("id_unidade").set_index("id_unidade")["NM_SUBDIST"]
    if "nome_antes_oficial" not in un:
        un["nome_antes_oficial"] = un["nome"]
    base = un.set_index("id_unidade")
    trocas = []
    usados = {(m_, norm(n_)): None for m_, n_ in zip(base["cd_mun_ibge"], base["nome_antes_oficial"])}
    for uid, nome in of.items():
        nome = LIMPA.sub("", str(nome)).strip()
        if len(nome) > 32 and "/" in nome:   # nomes compostos longos (Goiânia): fica o primeiro
            nome = nome.split("/")[0].strip()
        if uid not in base.index or not nome or GENERICO.search(nome):
            continue
        if norm(nome) == norm(base.at[uid, "municipio"]):   # distrito-sede: o nome da cidade não identifica a área
            continue
        atual = base.at[uid, "nome_antes_oficial"]
        if str(nome).lower() in str(atual).lower():
            continue
        mun = base.at[uid, "cd_mun_ibge"]
        if (mun, norm(nome)) in usados:   # outra área da cidade já tem esse nome
            continue
        usados[(mun, norm(nome))] = uid
        trocas.append({"id_unidade": uid, "municipio": base.at[uid, "municipio"], "antes": atual, "oficial": nome})
    tr = pd.DataFrame(trocas)
    un["nome"] = un["nome_antes_oficial"]
    if len(tr):
        un.loc[un["id_unidade"].isin(tr["id_unidade"]), "nome"] = un["id_unidade"].map(tr.set_index("id_unidade")["oficial"])
    un.to_parquet(arq, index=False)
    tr.to_csv(os.path.join(RAIZ, "variantes", uni, "nomes_oficiais.csv"), index=False)
    print(f"{len(tr)} subdistritos com nome oficial")
    print(tr.head(40).to_string(index=False))


if __name__ == "__main__":
    main()
