# Análise de esforço por bairro: 2º turno de 2026

> **Produção independente e exclusiva da [Estel Tecnologia](https://estel.tec.br).** Esta ferramenta não tem relação com a
> campanha oficial de Lula, com o PT ou com qualquer partido, federação, coligação ou candidatura, e não foi encomendada
> nem paga por eles.

Mapa interativo que mostra, por **município, bairro e região metropolitana**, onde o mesmo esforço de campanha tende a
trazer mais votos para Lula no 2º turno de 2026, com **temas sugeridos para cada lugar** a partir dos planos de governo
registrados no TSE. Todos os números vêm de dados públicos e agregados (TSE, IBGE) e trazem intervalo de incerteza.

**Mapa:** https://rafadaguia.github.io/analise-de-esforco-por-bairros-lula-2026/ ·
**Como usar:** https://rafadaguia.github.io/analise-de-esforco-por-bairros-lula-2026/guia.html

## O que o mapa mostra

* **Nota de 1 a 7** para cada município, bairro e região metropolitana. A nota 7 indica onde o esforço tende a render mais
  votos novos. Ela combina os votos a recuperar por eleitor, a chance de que levar mais gente às urnas ajude Lula, a
  firmeza da estimativa e o tamanho do eleitorado.
* **Votos que dá para recuperar:** os votos que Lula perdeu além da média do país entre 2022 e 2026, mais o ganho de
  levar mais gente às urnas onde isso tende a ajudá-lo.
* **Temas para conversar:** temas com mais força para Lula no lugar, temas que o plano de Flávio Bolsonaro não trata,
  temas disputados e temas a evitar, com citação e página do plano oficial.
* **Soberania nacional:** força do tema nas cidades expostas ao tarifaço dos EUA (exportações, Comex Stat) e na Amazônia
  Legal.

## Como ler (e o que o mapa não diz)

* Fala de **lugares, não de pessoas**. A média de um bairro não descreve quem mora nele (falácia ecológica).
* As pessoas votam onde estão inscritas, que nem sempre é o bairro onde moram.
* **Não é previsão.** Os números mostram o que acontece se o comportamento de 2022 entre os turnos se repetir. Os
  intervalos medem a incerteza dentro de uma eleição, não uma mudança de comportamento entre eleições.
* A nota serve para **triagem**: ela muda com os pesos, o método e o desenho das áreas.
* Em BA, CE, ES, MG, PA, RJ e SP, a estimativa é **menos segura** (os cálculos não convergiram bem), e o mapa avisa.
* Os temas são **sugestões a partir de dados**, não pesquisa de opinião feita no lugar. Nenhuma sugestão usa cor ou raça,
  gênero, religião ou orientação sexual.

## Método, em resumo

1. **Áreas:** resultado por seção eleitoral (TSE) agregado por local de votação, geocodificado com as coordenadas
   oficiais do TSE (99,4% dos eleitores) e levado aos bairros do Censo 2022 (IBGE). Onde a cidade não tem bairros no
   IBGE, as áreas são grupos de locais de votação. São 19.191 áreas, e 89% dos eleitores ficam abaixo do município.
2. **Modelo:** inferência ecológica RxC hierárquica (Rosen, Jiang, King e Tanner, 2001) das transferências de voto entre os
   turnos de 2022, com a hierarquia país → UF → região metropolitana → município → área, ajustada por MCMC (PyMC, nutpie).
3. **Simulação:** Monte Carlo com 10.000 sorteios para os cenários do 2º turno de 2026.
4. **Validação:** em 20% das áreas deixadas de fora, o resultado real ficou dentro do intervalo de 90% em 95,7% dos casos
   (erro mediano de 0,77 ponto). Teste entre eleições (2018 → 2022 e 2014 → 2018) descrito no notebook.
5. **Temas:** importância nas pesquisas × perfil da área no Censo × força das propostas nos planos oficiais (566 parágrafos
   classificados por modelo de linguagem local, com conferência por código e citação literal).

Detalhes, tabelas e limites: [`analise_bairros.ipynb`](analise_bairros.ipynb).

## Principais resultados

| Medida (simulação condicional) | Mediana | Intervalo de 90% |
|---|---|---|
| Diferença Lula − Flávio no 2º turno, se 2022 se repetir | −6,61 milhões | −6,67 a −6,55 milhões |
| Mesma diferença, com a terceira via mais à direita | −8,31 milhões | −9,83 a −6,77 milhões |
| Votos que dá para recuperar (país) | 1,61 milhão | 1,56 a 1,66 milhão |

Tabelas por área, município, região metropolitana, UF e país em [`resultados/`](resultados/).

## Estrutura

| Pasta ou arquivo | Conteúdo |
|---|---|
| `docs/` | o site (GitHub Pages): mapas de municípios, bairros e regiões metropolitanas, e o guia "Como usar" |
| `bairros/` | o código da análise, etapa por etapa (`b01` a `b14`), e os insumos (`insumos/`: pesquisas, temas, contexto, catálogo das malhas de prefeitura) |
| `mapa/` | gerador do site e modelos das páginas; bibliotecas, fontes e marca em `mapa/lib/` |
| `resultados/` | tabelas finais em CSV |
| `Plano de governo/` | planos de governo registrados no TSE |
| `modelo/`, `painel/`, `inferencia_ecologica.py`, `frentes.py` | modelo municipal de referência (taxas nacionais usadas como priori) |
| `analise_bairros.ipynb`, `construir_notebook_bairros.py` | relatório técnico |

## Reprodução

Python 3.12. Os dados brutos (cerca de 15 GB) são baixados das fontes oficiais pelo primeiro comando.

```bash
uv venv .venv-bairros --python 3.12 && uv pip install --python .venv-bairros/bin/python -r requirements-bairros.txt
P=.venv-bairros/bin/python
$P bairros/baixar.py tudo
$P bairros/b01_secoes.py 2026 2022 2018 2014 2010 && $P bairros/b02_locais.py 2026 2022 2018 2014 2010
$P bairros/b03_geocodificar.py 2026 2022
$P bairros/b04a_censo_setores.py && $P bairros/b04_unidades.py U4 && $P bairros/b04c_nomes.py U4 && $P bairros/b04d_infra.py U4
$P bairros/rodar_ei.py U4 --paralelo 3
$P bairros/rodar_ei.py U4 --paralelo 3 --ufs $($P bairros/escolher_ajuste.py U4 instaveis) --longo && $P bairros/escolher_ajuste.py U4 incorporar
$P bairros/b06_montecarlo_bairros.py --unidade U4 --metodo MC --sorteios 10000 && $P bairros/b08_esforco.py --unidade U4 --metodo MC
$P bairros/b13_planos.py && $P bairros/b14_soberania.py --unidade U4 && $P bairros/b09_temas.py --unidade U4
$P bairros/b12_tabelas.py --unidade U4 --metodo MC
$P mapa/construir_mapa_bairros.py --unidade U4 --metodo MC && mapa/preparar_pages.sh
```

* O MCMC leva várias horas (paralelizado por UF). O Monte Carlo usa a GPU quando disponível (PyTorch MPS ou CUDA).
* A etapa `b13_planos.py` usa um modelo de linguagem local pelo [Ollama](https://ollama.com) (`gemma4:31b`).
* Sementes fixas em todos os scripts. O MCMC não é bit a bit reprodutível entre máquinas; os diagnósticos ficam
  registrados por UF.
* Para ver o site localmente: `npx http-server docs` (o PMTiles precisa de um servidor com requisições parciais).

## Fontes

TSE (resultado por seção e locais de votação, 2010–2026; planos de governo registrados) · IBGE (Censo 2022: malhas e
agregados por setor censitário; regiões metropolitanas) · malhas de bairros de prefeituras (catálogo conferido em
`bairros/insumos/prefeituras/catalogo.csv`) · OpenStreetMap (nomes de parte das áreas, © colaboradores do OpenStreetMap,
ODbL) · MTE (Novo CAGED) · MDS (Bolsa Família, CadÚnico) · MDIC (Comex Stat) · pesquisas registradas no TSE (Datafolha,
AtlasIntel, Quaest). Bibliotecas: MapLibre GL JS e PMTiles (BSD-3); fontes Archivo, Instrument Sans e Noto Sans (SIL OFL).

## Licença

Código, tabelas e mapas desta análise: [Creative Commons Atribuição 4.0 Internacional (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/deed.pt-br) (ver `LICENSE`). Ao reutilizar, cite: "Estel Tecnologia (estel.tec.br), Análise de esforço por bairro: 2º turno de 2026". Os dados de terceiros mantêm suas licenças: os nomes derivados do
OpenStreetMap seguem a ODbL, e as bibliotecas e fontes em `mapa/lib/` seguem as licenças incluídas na pasta.
