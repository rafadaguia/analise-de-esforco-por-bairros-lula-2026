#!/usr/bin/env python3
"""Monta o notebook da análise por bairro (analise_bairros.ipynb), no padrão de analise_2turno.ipynb.

Os números do texto são lidos dos resultados no momento da montagem (variantes/ e painel/),
e as células de código refazem as tabelas a partir dos mesmos arquivos. Variante publicada: --unidade,
--metodo e --pesos (padrão: U4, MC, P2).

Uso:
  .venv-bairros/bin/python construir_notebook_bairros.py [--unidade U1 --metodo MC --pesos P2]
  .venv-bairros/bin/jupyter nbconvert --to notebook --execute --inplace analise_bairros.ipynb
"""
import argparse, json, os
import nbformat as nbf
import pandas as pd

RAIZ = os.path.dirname(os.path.abspath(__file__))
VAR = os.path.join(RAIZ, "variantes")


def fm(v, casas=0):
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def mil(v):
    return fm(v / 1000) + " mil" if abs(v) >= 1000 else fm(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unidade", default="U4"); ap.add_argument("--metodo", default="MC"); ap.add_argument("--pesos", default="P2")
    a = ap.parse_args()
    U, M, P = a.unidade, a.metodo, a.pesos
    pasta = os.path.join(VAR, U, M)
    gr = pd.read_parquet(os.path.join(pasta, "grupos_mc.parquet"))
    br = gr[gr["nivel"] == "pais"].set_index("medida")
    meta = json.load(open(os.path.join(pasta, "mc_meta.json")))
    med = json.load(open(os.path.join(VAR, U, "medidas.json")))
    comp = os.path.join(VAR, "comparacoes")
    fr = pd.read_csv(os.path.join(comp, "frentes.csv"))
    fr = fr[fr["variante"] == f"{U}/{M}"].set_index("frente")
    est = pd.read_csv(os.path.join(VAR, U, "historico", "estabilidade.csv"))
    e2226 = est[(est["de"] == "2022 T1") & (est["para"] == "2026 T1")].iloc[0]
    mud = pd.read_csv(os.path.join(pasta, "esforco_mudancas.csv"))
    mrp = pd.read_csv(os.path.join(comp, "mrp_x_ei.csv")).set_index("variante_mrp")
    faixa = lambda m: f"{mil(br.loc[m, 'mediana'])} (90%: {mil(br.loc[m, 'p05'])} a {mil(br.loc[m, 'p95'])})"
    tf = fr.loc["TODOS OS FOCOS"]

    nb = nbf.v4.new_notebook()
    C = []
    md = lambda t: C.append(nbf.v4.new_markdown_cell(t))
    co = lambda t: C.append(nbf.v4.new_code_cell(t))

    md(f"""# Onde ganhar votos para Lula exige menos esforço: o 2º turno de 2026 por bairro

**Estel Tecnologia** ([estel.tec.br](https://estel.tec.br)) · análise de 07 e 08/10/2026

> **Produção independente e exclusiva da Estel Tecnologia (estel.tec.br).** Esta ferramenta não tem relação com a campanha oficial de Lula, com o PT ou com qualquer partido, federação, coligação ou candidatura, e não foi encomendada nem paga por eles.

Esta análise leva ao nível de bairro a pergunta da versão municipal (v2.0, tag `v2.0`): **onde a campanha
deve gastar tempo e dinheiro entre os turnos?** Agora, com a pergunta mais fina: **onde cada voto a mais
para Lula custa menos esforço?**

> **Aviso de método.** Tudo aqui vem de dados agregados: resultado por local de votação (TSE) e perfil
> por setor censitário (IBGE). Nada descreve pessoas. O eleitor vota onde está a escola-sede da seção, não
> necessariamente onde mora. Quanto menor a área, maior o risco da **falácia ecológica**: o padrão de um
> bairro não diz nada sobre cada morador. As projeções supõem que o comportamento de 2022 entre os turnos se
> repete. Não é previsão, e não há "chance de vitória" em lugar nenhum deste documento.

Variante deste notebook: unidade **{U}**, método **{M}**, pesos **{P}** (ver seção 9).""")

    md(f"""## Resumo executivo

**0. Leia os intervalos como mínimos.** No backtesting entre eleições, o modelo errou mais do que os intervalos
indicavam (2018 → 2022: cobertura de 42%; 2014 → 2018: pior que o swing uniforme). Ele vale enquanto o comportamento
entre os turnos se parece com o de 2022.

**1. A geografia do voto por bairro está estável, o que torna o exercício possível.** Entre o 1º turno de
2022 e o de 2026, a fatia de Lula nas {fm(e2226['unidades'])} áreas tem correlação de
{fm(e2226['correlacao'], 3)}, e a queda variou pouco de área para área (desvio de {fm(e2226['desvio_da_variacao_pp'], 1)}
pontos em torno da média de {fm(e2226['variacao_media_pp'], 1)}).

**2. O ponto de partida continua ruim.** Repetido o comportamento de 2022 entre os turnos, a margem nacional
projetada é de {faixa('margem_base')} votos para Flávio. Com a terceira via mais à direita, {faixa('margem_dir')}.

**3. O potencial geográfico por bairro é da mesma ordem que o municipal.** Nos 200 municípios-foco da v2.0, as
áreas somam {mil(tf['pot_p50'])} votos de potencial, contra {mil(tf['pot_v2_municipal'])} no modelo municipal. O
ganho vem quase todo do Nordeste urbano ({mil(fr.loc['Nordeste urbano', 'pot_p50'])}, contra
{mil(fr.loc['Nordeste urbano', 'pot_v2_municipal'])}), onde a queda de Lula variou muito dentro das cidades.

**4. Os 7 níveis de esforço dependem dos pesos e do método.** Entre o esquema de pesos iguais e o de foco em
potencial, {fm(mud.loc[0, 'mudam_de_nivel'])} de {fm(mud.loc[0, 'unidades'])} áreas mudam de nível. No topo, cerca de 2/3
das áreas de nível 7 se mantêm. O componente frágil é a probabilidade de a mobilização render, que muda bastante
entre MCMC e ADVI. Use os níveis como triagem, não como ranking fino.

**5. Pesquisas e voto real divergem no bairro.** Levadas ao bairro por MRP (sexo, idade e cor), as pesquisas dão a
Lula {fm(mrp.loc['R3', 'dif_media_pp'], 1)} pontos a mais que o modelo ecológico, em média, com divergência acima de
10 pontos em {fm(mrp.loc['R3', 'pct_divergencia_maior_10pp'])}% das áreas: mais no Sul e Sudeste, menos no Nordeste. O
modelo ecológico, ancorado no voto, é a base; o MRP é contraste.""")

    md("""## 1. Desenho: as variantes

A tarefa foi rodada em modo autônomo. Toda dúvida com mais de um caminho razoável virou variante, registrada em
e comparada na seção 9:

| Eixo | Variantes |
|---|---|
| Unidade de análise | U1 bairros do IBGE (com recuo a subdistrito, distrito e município) · U2 áreas de influência dos locais de votação · U3 malhas das prefeituras + U1 |
| Método de inferência | MC: MCMC (NUTS, nutpie) por UF · M2: ADVI do país inteiro |
| Pesos do índice | P1 iguais · P2 foco em potencial · P3 foco em segurança da mobilização |
| Pesquisas (MRP) | R1 Datafolha · R2 AtlasIntel · R3 combinada |""")

    md("""## 2. Dados e unidade de análise

O TSE não publica resultado por bairro. A unidade é construída: **seção → local de votação → área → município →
região metropolitana → UF**. O TSE publica a latitude e a longitude de cada local de votação, e cada local vai para o
setor censitário do Censo 2022 onde cai a coordenada.""")
    co(f"""import json, pandas as pd
pd.set_option("display.width", 200); pd.set_option("display.max_columns", 30)
m = json.load(open("variantes/{U}/medidas.json"))
pd.Series(m["geocodificacao_2026_pct_eleitores"], name="% dos eleitores (2026)").to_frame()""")
    co("""pd.read_csv("variantes/comparacoes/unidades.csv")[["variante", "unidades_abaixo_do_municipio",
    "cobertura_pct_eleitores_abaixo_do_municipio", "eleitores_por_unidade_mediana", "unidades_fundidas_por_tamanho"]]""")
    md(f"""Leitura: a coordenada do TSE coloca {fm(med['geocodificacao_2026_pct_eleitores'].get('tse_ok', 0), 1)}% dos eleitores de 2026 num
setor do município certo. O bairro que o TSE declara bate com o bairro do IBGE do ponto em
{fm(med['concordancia_bairro_tse_ibge_pct_locais_2026'], 0)}% dos locais (nomes populares diferem dos oficiais; a discordância
não prova erro). Áreas com menos de 1.000 eleitores foram fundidas à vizinha mais próxima do mesmo município.""")

    md("""## 3. Série histórica

| Ano | Menor nível publicado | Levado ao bairro? |
|---|---|---|
| 1994 | município e zona | não |
| 1998 | seção, sem local de votação (e sem 2º turno) | não |
| 2002, 2006 | seção e nº do local, sem cadastro com coordenadas | não |
| 2010, 2014, 2018, 2022, 2026 | seção e local com coordenadas | **sim** |

**A série no nível de bairro começa em 2010.** Antes disso, não há como saber onde ficava cada local de votação
sem inventar dado.""")
    co(f"""pd.read_csv("variantes/{U}/historico/estabilidade.csv")""")
    co(f"""pd.read_csv("variantes/{U}/historico/transferencias.csv")""")

    md("""## 4. O modelo

O mesmo RxC hierárquico da v2.0 (Rosen, Jiang, King e Tanner, 2001): quatro origens no 1º turno (Lula, adversário,
terceira via, fora) e três destinos no 2º (Lula, adversário, fora), com verossimilhança Dirichlet. A hierarquia
desce ao bairro: **país → UF → região metropolitana → município → área**. As taxas nacionais por faixa do modelo
municipal entram como priori de cada UF (Bayes empírico). RM e município têm dois efeitos (um por destino), e a área,
dois, só onde o município tem mais de uma. Mais que isso não é identificável com dados agregados.""")
    co(f"""import glob
diag = pd.DataFrame([json.load(open(f)) for f in glob.glob("variantes/{U}/{M}/diag_??.json")])
diag[["uf", "unidades", "municipios", "segundos", "rhat_max", "ess_min", "divergencias", "descartadas"]].sort_values("rhat_max")""" if M == "MC" else "print('M2: ADVI, sem diagnóstico por cadeia')")
    md("""**Convergência.** As quantidades que entram nas projeções (fração para Lula entre quem votou, saldo líquido)
convergem melhor que os parâmetros. O que mistura mal é o nível de comparecimento da terceira via, pouco
identificado. As UFs com R-hat acima de 1,05 aparecem sinalizadas, e BA e CE tiveram cadeias em modos separados;
por isso essas UFs receberam um reajuste longo e, onde ele não resolveu, o selo de estimativa menos segura.""")

    md("""## 5. Validação

Duas validações: (a) **fora da amostra**, como na v2.0: ajuste em 80% das áreas e cobertura do intervalo de 90% nas
outras 20%; (b) **backtesting**: ajuste das transferências de uma eleição e previsão do 2º turno da seguinte a partir
do 1º turno dela, área por área, contra o swing uniforme.""")
    co(f"""import os
v = [json.load(open(f)) for f in glob.glob("variantes/{U}/{M}/diag_??_val.json")]
print("validação 80/20:", "pendente" if not v else f"{{len(v)}} UFs ajustadas")
p = "variantes/{U}/{M}/validacao.csv"
pd.read_csv(p) if os.path.exists(p) else None""")
    co(f"""p = "variantes/{U}/historico/backtest.csv"
pd.read_csv(p) if os.path.exists(p) else print("backtesting pendente")""")

    md(f"""## 6. Resultados

Nacional ({fm(meta['sorteios'])} sorteios de Monte Carlo, na GPU):

| Medida | Mediana e intervalo de 90% |
|---|---|
| Margem projetada, cenário base | {faixa('margem_base')} |
| Margem, terceira via mais à direita | {faixa('margem_dir')} |
| Potencial (terreno perdido + 2 pp onde a mobilização rende) | {faixa('potencial')} |
| Saldo de +2 pp de comparecimento em todas as áreas | {faixa('mob')} |

O saldo nacional de mobilizar em todo lugar é negativo: em muitas áreas, quem passa a votar vota mais em Flávio.
Mobilização precisa de endereço.""")
    co(f"""fr = pd.read_csv("variantes/comparacoes/frentes.csv")
fr[fr.variante == "{U}/{M}"].set_index("frente")[["areas", "pot_p50", "pot_v2_municipal", "areas_nivel7_P1"]].round(0)""")
    co(f"""es = pd.read_parquet("variantes/{U}/{M}/esforco.parquet")
mc = pd.read_parquet("variantes/{U}/{M}/unidades_mc.parquet")
t = es.merge(mc[["id_unidade", "terreno", "mob_p50", "lula_pct_26", "desloc"]], on="id_unidade")
top = t[t["nivel_{P}"] == 7].sort_values("pot_p50", ascending=False)
top[["uf", "municipio", "nome", "tipo", "aptos", "pot_p05", "pot_p50", "pot_p95", "pot_mil", "prob_mob_rende", "nivel_P1", "nivel_P2", "nivel_P3"]].head(30).round(2)""")
    co(f"""# distribuição dos níveis por frente (pesos {P})
pd.crosstab(t["frente"], t["nivel_{P}"], margins=True)""")

    md("""## 7. Pesquisas levadas ao bairro (MRP) e o modelo ecológico

Cruzamentos publicados pelo Datafolha (nacional) e pela AtlasIntel (estaduais), extraídos dos relatórios e
conferidos por soma. Como só há marginais publicadas, o MRP é sintético (MrsP): um modelo aditivo em sexo, idade,
cor e região ou UF, pós-estratificado pela composição de cada área no Censo 2022. Renda, escolaridade e religião
ficam de fora da pós-estratificação, porque o Censo não as publica por bairro. Orientação sexual não tem dado oficial
por bairro nem por município e não é usada.""")
    co("""pd.read_csv("variantes/comparacoes/mrp_x_ei.csv")""")
    co("""pd.read_csv("variantes/comparacoes/mrp_x_ei_uf.csv").sort_values("div_media_pp")""")

    md("""## 8. Perfil e temas por área

O perfil vem do Censo 2022 por setor (sexo, idade, cor ou raça, alfabetização e renda do responsável), somado
na área, e do contexto municipal (Novo CAGED, Bolsa Família e CadÚnico). Os temas são **hipóteses de comunicação**
derivadas de dados agregados: importância do tema nas pesquisas × perfil da área × existência de proposta com
fonte. Nenhum gatilho usa cor ou raça, gênero, religião ou orientação sexual. "Flávio mais fraco" = temas que o plano
de governo dele não menciona (salário mínimo, escala 6x1, isenção do IR, regra da Previdência), com fonte na matriz.""")
    co(f"""tm = pd.read_parquet("variantes/{U}/temas_unidades.parquet")
tm["temas_aderentes_lula"].str.split(";").explode().value_counts().to_frame("áreas em que o tema está entre os 3 primeiros")""")
    co(f"""tm.merge(es[["id_unidade", "nivel_{P}", "pot_p50"]], on="id_unidade").query("nivel_{P} == 7") \\
  .sort_values("pot_p50", ascending=False)[["uf", "nome", "temas_aderentes_lula", "temas_flavio_mais_fraco", "temas_disputados", "sinais_fortes"]].head(15)""")

    md("""### 8.1 O que os planos de governo oficiais dizem, tema a tema

Os planos registrados no TSE (`Plano de governo/proposta-pt.pdf` e `proposta-pl.pdf`) foram segmentados em parágrafos
e classificados por um modelo de linguagem **local** (nada saiu da máquina), com conferência por código: tema e público
só valem com evidência textual no parágrafo, a meta numérica é detectada no texto, e a citação é sempre literal.
Força = compromissos concretos + 2 × metas numéricas.""")
    co("""pp = pd.read_csv("bairros/insumos/temas/propostas_por_tema.csv")
pp.pivot_table(index="tema", columns="candidato", values=["compromissos", "metas", "forca"], fill_value=0).astype(int)""")
    co("""pp[pp.candidato == "lula"][["tema", "citacao_pagina", "citacao"]].sort_values("tema").head(25)""")
    md("""### 8.2 Soberania nacional: onde o tema pode ter força

Não há pesquisa com recorte geográfico sobre o tema. Nacionalmente, 64% aprovam a defesa da soberania diante das tarifas
dos EUA (Genial/Quaest, set/2025), e 47% concordam mais com Lula do que com Flávio (35%) sobre o tarifaço
(Genial/Quaest, jun/2026). A força local é aproximada pela **exposição ao mercado dos EUA** (exportações de 2025 por
município, Comex Stat/MDIC) e pela **Amazônia Legal**. É uma hipótese: onde o tarifaço pesa na economia local, a defesa
da soberania tende a ressoar mais. O Comex atribui a exportação ao município do estabelecimento exportador (às vezes a
sede), e não desce ao bairro: no bairro, o sinal é o do município.""")
    co("""sb = pd.read_csv("bairros/insumos/contexto/soberania_municipios.csv")
print(sb["forca_soberania"].value_counts())
sb[sb.forca_soberania == "alta"].sort_values("exp_eua_usd", ascending=False).head(25)[
    ["municipio", "uf", "exp_eua_usd", "parcela_eua", "eua_por_eleitor", "sede_exportadora", "amazonia_legal"]]""")
    co(f"""import os
p = "variantes/{U}/soberania_rm.csv"
pd.read_csv(p).head(15) if os.path.exists(p) else print("pendente: b14 para {U}")""")
    co(f"""p = "variantes/{U}/soberania_areas.csv"
if os.path.exists(p):
    a = pd.read_csv(p)
    if "coincide_baixo_esforco" in a:
        display(a[a.coincide_baixo_esforco.fillna(False).astype(bool)].sort_values("pot_p50", ascending=False)[["uf", "nome", "cd_mun_ibge", "nivel_P2", "pot_p50", "motivo"]].head(25))""")

    md("""## 9. Variantes lado a lado""")
    co("""pd.read_csv("variantes/comparacoes/metodo_MC_x_M2.csv")""")
    co(f"""pd.read_csv("variantes/{U}/{M}/esforco_mudancas.csv")""")

    md("""## 10. O que isto não diz

* **Não descreve pessoas.** Um bairro de nível 7 não tem "eleitores fáceis"; tem, no agregado, muito voto a recuperar
  por eleitor e um histórico de mobilização que tendeu a favorecer Lula.
* **Local de votação não é moradia.** As áreas descrevem quem vota nas escolas da área. O perfil do Censo descreve
  quem mora nela.
* **Falácia ecológica.** O risco cresce quanto menor a área. As áreas têm, na mediana, cerca de 4 mil eleitores.
* **Transferências de 2022.** A projeção supõe que eleitores de terceira via e quem não votou se comportam como em
  2022. A terceira via de 2026 é mais à direita: o cenário "direita" existe para isso.
* **Pesquisas.** São marginais publicadas por dois institutos. O MRP ignora renda, escolaridade e religião, que o
  Censo não traz por bairro. O 1º turno mostrou erro das pesquisas a favor de Lula.
* **Temas.** São hipóteses de comunicação, não diagnóstico. Não dependem de raça, gênero ou religião.
* **Os níveis são triagem.** Mudam com os pesos e com o método (seção 9).""")

    md(f"""## 11. Reprodução

```bash
# ambiente (Python 3.12)
uv venv .venv-bairros --python 3.12 && uv pip install --python .venv-bairros/bin/python -r requirements-bairros.txt
P=.venv-bairros/bin/python
$P bairros/baixar.py tudo                     # TSE e IBGE (~15 GB), com retomada
$P bairros/b01_secoes.py 2026 2022 2018 2014 2010
$P bairros/b02_locais.py 2026 2022 2018 2014 2010
$P bairros/b03_geocodificar.py 2026 2022
$P bairros/b04a_censo_setores.py
$P bairros/b04_unidades.py U1 U2 U3
$P bairros/rodar_ei.py {U} --paralelo 3          # MCMC por UF (checkpoints em variantes/{U}/MC)
$P bairros/b05_ei_bairros.py --unidade {U} --metodo M2 && $P bairros/b05b_m2_por_uf.py --unidade {U}
$P bairros/b06_montecarlo_bairros.py --unidade {U} --metodo {M} --sorteios 10000
$P bairros/b08_esforco.py --unidade {U} --metodo {M}
$P bairros/b07a_pesquisas.py && $P bairros/b07b_mrp.py --unidade {U}
$P bairros/b09_temas.py --unidade {U}
$P bairros/b11_comparar.py
$P mapa/construir_mapa_bairros.py --unidade {U} --metodo {M} --pesos {P}
$P construir_notebook_bairros.py --unidade {U} --metodo {M} --pesos {P}
```

Sementes fixas em todos os scripts. Versões dos pacotes em `requirements-bairros.txt`. O MCMC não é bit a bit
reprodutível entre execuções nesta máquina: a checagem de cadeias presas e os diagnósticos ficam
registrados em `variantes/*/MC/diag_*.json`.

**Fontes:** TSE (Dados Abertos), IBGE (Censo 2022: malhas e agregados por setor; RMs), malhas
de bairros de prefeituras, MTE (Novo CAGED), MDS (Bolsa Família, CadÚnico), Datafolha e AtlasIntel (pesquisas
registradas no TSE).""")

    nb["cells"] = C
    nb["metadata"]["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    nbf.write(nb, os.path.join(RAIZ, "analise_bairros.ipynb"))
    print(f"analise_bairros.ipynb: {len(C)} células ({U}/{M}/{P})")


if __name__ == "__main__":
    main()
