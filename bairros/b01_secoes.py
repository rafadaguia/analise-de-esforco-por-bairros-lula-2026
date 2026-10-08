#!/usr/bin/env python3
"""Etapa B1: votação de presidente por seção eleitoral (TSE), 2022 e 2026, em Parquet.

Uma linha por (ano, turno, UF, município TSE, zona, seção), com:
  lula, adversario (Bolsonaro em 2022, Flávio em 2026: o nº 22 nos dois anos),
  terceiros (demais candidatos), brancos, nulos, nr_local_votacao
e, do detalhe da seção: aptos, comparecimento, abstenções.

Só agregados por seção, como o TSE publica. Nenhum dado de eleitor individual.

Entradas: dados_bairros/tse/votacao_secao_{ano}_BR.zip, detalhe_votacao_secao_{ano}.zip
Saída:    dados_bairros/proc/secoes_{ano}.parquet
"""
import os, sys, tempfile, zipfile
import duckdb

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TSE = os.path.join(RAIZ, "dados_bairros", "tse")
PROC = os.path.join(RAIZ, "dados_bairros", "proc")
LULA, ADV, BRANCO, NULO = 13, 22, 95, 96


def extrair(zipn, padrao, tmp):
    """Extrai o(s) CSV(s) que casam com `padrao` e devolve os caminhos."""
    z = zipfile.ZipFile(os.path.join(TSE, zipn))
    csvs = [n for n in z.namelist() if n.endswith(".csv")]
    # os zips do TSE trazem um arquivo por UF e, conforme o ano, um _BR (só presidente, país
    # inteiro) e/ou um _BRASIL (todos os cargos). Ler mais de um duplica as seções.
    nomes = ([n for n in csvs if n.endswith("_BR.csv")] or [n for n in csvs if n.endswith("_BRASIL.csv")]
             or [n for n in csvs if padrao in n])
    for n in nomes:
        z.extract(n, tmp)
    return [os.path.join(tmp, n) for n in nomes]


def ler_csv(con, caminhos):
    lista = ", ".join(f"'{c}'" for c in caminhos)
    return (f"read_csv([{lista}], delim=';', header=true, encoding='latin-1', all_varchar=true, "
            f"quote='\"', parallel=true)")


def processar(ano):
    global ADV
    os.makedirs(PROC, exist_ok=True)
    saida = os.path.join(PROC, f"secoes_{ano}.parquet")
    if os.path.exists(saida):
        print(f"{ano}: já existe {saida}")
        return
    con = duckdb.connect()
    con.execute("SET threads TO 4")
    with tempfile.TemporaryDirectory(dir=PROC) as tmp:
        votos = ler_csv(con, extrair(f"votacao_secao_{ano}_BR.zip", "", tmp))
        # adversário do PT: o 2º mais votado no 1º turno (Serra 2010, Aécio 2014, Bolsonaro 2018 e 2022, Flávio 2026)
        ADV = con.execute(f"""SELECT NR_VOTAVEL FROM {votos} WHERE CD_CARGO='1' AND NR_TURNO='1'
                               AND NR_VOTAVEL NOT IN ('{LULA}','{BRANCO}','{NULO}')
                               GROUP BY 1 ORDER BY SUM(CAST(QT_VOTOS AS BIGINT)) DESC LIMIT 1""").fetchone()[0]
        con.execute(f"""
            CREATE TABLE v AS
            SELECT CAST(NR_TURNO AS INT) turno, SG_UF uf, CAST(CD_MUNICIPIO AS INT) cd_mun_tse,
                   NM_MUNICIPIO municipio, CAST(NR_ZONA AS INT) zona, CAST(NR_SECAO AS INT) secao,
                   CAST(NR_LOCAL_VOTACAO AS INT) nr_local,
                   SUM(CASE WHEN NR_VOTAVEL='{LULA}' THEN CAST(QT_VOTOS AS INT) ELSE 0 END) lula,
                   SUM(CASE WHEN NR_VOTAVEL='{ADV}' THEN CAST(QT_VOTOS AS INT) ELSE 0 END) adversario,
                   SUM(CASE WHEN NR_VOTAVEL NOT IN ('{LULA}','{ADV}','{BRANCO}','{NULO}') THEN CAST(QT_VOTOS AS INT) ELSE 0 END) terceiros,
                   SUM(CASE WHEN NR_VOTAVEL='{BRANCO}' THEN CAST(QT_VOTOS AS INT) ELSE 0 END) brancos,
                   SUM(CASE WHEN NR_VOTAVEL='{NULO}' THEN CAST(QT_VOTOS AS INT) ELSE 0 END) nulos
            FROM {votos} WHERE CD_CARGO='1'
            GROUP BY ALL""")
        # 3º colocado nacional, isolado (como em preparar_dados.py): a composição do resto importa
        top = con.execute(f"""SELECT NR_VOTAVEL, NM_VOTAVEL, SUM(CAST(QT_VOTOS AS BIGINT)) v FROM {votos}
                              WHERE CD_CARGO='1' AND NR_TURNO='1' GROUP BY ALL ORDER BY v DESC LIMIT 8""").fetchall()
        print(f"{ano} 1º turno, mais votados: " + "; ".join(f"{n} {nm.title()} {v:,}" for n, nm, v in top))

        det = ler_csv(con, extrair(f"detalhe_votacao_secao_{ano}.zip", "", tmp))
        cols = [c[0] for c in con.execute(f"DESCRIBE SELECT * FROM {det}").fetchall()]
        # o nome da coluna de abstenção muda entre anos (QT_ABSTENCOES / QT_ABSTENCAO)
        abst = "QT_ABSTENCOES" if "QT_ABSTENCOES" in cols else "QT_ABSTENCAO"
        con.execute(f"""
            CREATE TABLE d AS
            SELECT CAST(NR_TURNO AS INT) turno, SG_UF uf, CAST(CD_MUNICIPIO AS INT) cd_mun_tse,
                   CAST(NR_ZONA AS INT) zona, CAST(NR_SECAO AS INT) secao,
                   SUM(CAST(QT_APTOS AS INT)) aptos, SUM(CAST(QT_COMPARECIMENTO AS INT)) comparecimento,
                   SUM(CAST({abst} AS INT)) abstencoes
            FROM {det} WHERE CD_CARGO='1' GROUP BY ALL""")
        con.execute(f"""
            COPY (SELECT {ano} ano, v.*, d.aptos, d.comparecimento, d.abstencoes
                  FROM v LEFT JOIN d USING (turno, uf, cd_mun_tse, zona, secao)
                  ORDER BY turno, uf, cd_mun_tse, zona, secao)
            TO '{saida}' (FORMAT parquet, COMPRESSION zstd)""")
        r = con.execute(f"""SELECT turno, COUNT(*), SUM(lula), SUM(adversario), SUM(terceiros), SUM(aptos),
                                   SUM(comparecimento), COUNT(*) FILTER (WHERE aptos IS NULL)
                            FROM '{saida}' GROUP BY 1 ORDER BY 1""").fetchall()
        for t, n, l, a, te, ap, co, sem in r:
            print(f"  {ano} T{t}: {n:,} seções | Lula {l:,} | nº22 {a:,} | terceiros {te:,} | aptos {ap:,} | "
                  f"comparec. {co:,} | seções sem detalhe {sem}")


if __name__ == "__main__":
    for ano in (sys.argv[1:] or ["2026", "2022"]):
        processar(int(ano))
