#!/usr/bin/env python3
"""Etapa B2: cadastro de locais de votação (TSE) de 2022 e 2026, com coordenadas.

O TSE publica, por seção, o local de votação com endereço, bairro declarado, CEP e
latitude/longitude. Esta etapa:

  1. lê o cadastro por seção (`eleitorado_local_votacao_{ano}.zip`) e normaliza as
     coordenadas (o separador decimal é vírgula em 2026 e ponto em 2022);
  2. resolve seções agregadas: em seções agregadas a votação é apurada na seção
     principal (NR_SECAO_PRINCIPAL), então elas herdam o local da principal;
  3. gera uma tabela de locais (ano, UF, município TSE, zona, nº do local) com
     coordenada, nº de seções e eleitores.

Saídas:
  dados_bairros/proc/locais_secao_{ano}.parquet   seção -> local
  dados_bairros/proc/locais_{ano}.parquet         um registro por local
"""
import os, sys, tempfile, zipfile
import duckdb

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TSE = os.path.join(RAIZ, "dados_bairros", "tse")
PROC = os.path.join(RAIZ, "dados_bairros", "proc")


def coord(col):
    # "-15,5954586" (2026) e "-9.827566" (2022); -1 ou vazio = sem coordenada
    return (f"TRY_CAST(NULLIF(NULLIF(REPLACE({col}, ',', '.'), '-1'), '') AS DOUBLE)")


def processar(ano):
    os.makedirs(PROC, exist_ok=True)
    s_out = os.path.join(PROC, f"locais_secao_{ano}.parquet")
    l_out = os.path.join(PROC, f"locais_{ano}.parquet")
    if os.path.exists(l_out):
        print(f"{ano}: já existe")
        return
    z = zipfile.ZipFile(os.path.join(TSE, f"eleitorado_local_votacao_{ano}.zip"))
    nomes = [n for n in z.namelist() if n.endswith(".csv")]
    # 2026 traz um arquivo por UF e um _BRASIL; usa só o _BRASIL quando existir
    br = [n for n in nomes if "BRASIL" in n] or nomes
    con = duckdb.connect()
    con.execute("SET threads TO 4")
    with tempfile.TemporaryDirectory(dir=PROC) as tmp:
        for n in br:
            z.extract(n, tmp)
        arqs = ", ".join(f"'{os.path.join(tmp, n)}'" for n in br)
        src = f"read_csv([{arqs}], delim=';', header=true, encoding='latin-1', all_varchar=true)"
        con.execute(f"""
            CREATE TABLE s AS SELECT
              CAST(NR_TURNO AS INT) turno, SG_UF uf, CAST(CD_MUNICIPIO AS INT) cd_mun_tse, NM_MUNICIPIO municipio,
              CAST(NR_ZONA AS INT) zona, CAST(NR_SECAO AS INT) secao,
              CAST(CD_TIPO_SECAO_AGREGADA AS INT) tipo_agregada, CAST(NR_SECAO_PRINCIPAL AS INT) secao_principal,
              CAST(NR_LOCAL_VOTACAO AS INT) nr_local, NM_LOCAL_VOTACAO nm_local, DS_TIPO_LOCAL tipo_local,
              DS_ENDERECO endereco, NM_BAIRRO bairro_tse, NR_CEP cep,
              {coord('NR_LATITUDE')} lat, {coord('NR_LONGITUDE')} lon,
              DS_SITU_SECAO situacao_secao, DS_SITU_LOCALIDADE situacao_localidade,
              CAST(QT_ELEITOR_SECAO AS INT) eleitores
            FROM {src} WHERE SG_UF <> 'ZZ'""")
    # coordenadas fora do território brasileiro (aprox.) contam como ausentes
    con.execute("""UPDATE s SET lat = NULL, lon = NULL
                   WHERE lat IS NULL OR lon IS NULL OR lat NOT BETWEEN -34.0 AND 5.5 OR lon NOT BETWEEN -74.5 AND -28.5
                      OR (lat = 0 AND lon = 0)""")
    # cada seção uma vez por turno; o local de votação vale para os dois turnos, usamos o do 1º
    t1 = con.execute("SELECT MIN(turno) FROM s").fetchone()[0]
    con.execute(f"CREATE TABLE s1 AS SELECT * FROM s WHERE turno = {t1}")
    con.execute(f"COPY (SELECT {ano} ano, * EXCLUDE (turno) FROM s1 ORDER BY uf, cd_mun_tse, zona, secao) "
                f"TO '{s_out}' (FORMAT parquet, COMPRESSION zstd)")
    con.execute(f"""
        COPY (SELECT {ano} ano, uf, cd_mun_tse, ANY_VALUE(municipio) municipio, zona, nr_local,
                     ANY_VALUE(nm_local) nm_local, ANY_VALUE(tipo_local) tipo_local, ANY_VALUE(endereco) endereco,
                     ANY_VALUE(bairro_tse) bairro_tse, ANY_VALUE(cep) cep,
                     MEDIAN(lat) lat, MEDIAN(lon) lon,
                     -- quando seções do mesmo local trazem coordenadas diferentes (raro), guarda a dispersão
                     MAX(lat) - MIN(lat) + MAX(lon) - MIN(lon) dispersao_graus,
                     COUNT(*) secoes, SUM(eleitores) eleitores
              FROM s1 GROUP BY uf, cd_mun_tse, zona, nr_local ORDER BY uf, cd_mun_tse, zona, nr_local)
        TO '{l_out}' (FORMAT parquet, COMPRESSION zstd)""")
    r = con.execute(f"""SELECT COUNT(*), SUM(eleitores), SUM(CASE WHEN lat IS NULL THEN eleitores END),
                               COUNT(*) FILTER (WHERE lat IS NULL), COUNT(*) FILTER (WHERE dispersao_graus > 0.01)
                        FROM '{l_out}'""").fetchone()
    print(f"{ano}: {r[0]:,} locais | {r[1]:,} eleitores | sem coordenada: {r[3]:,} locais, "
          f"{(r[2] or 0):,} eleitores ({100*(r[2] or 0)/r[1]:.2f}%) | locais com coordenadas divergentes: {r[4]}")


if __name__ == "__main__":
    for ano in (sys.argv[1:] or ["2026", "2022"]):
        processar(int(ano))
