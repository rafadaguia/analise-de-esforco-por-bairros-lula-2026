# Análise de esforço por bairro: 2º turno de 2026

> **Produção independente e exclusiva da [Estel Tecnologia](https://estel.tec.br).** Esta ferramenta não tem relação com a
> campanha oficial de Lula, com o PT ou com qualquer partido, federação, coligação ou candidatura, e não foi encomendada
> nem paga por eles.

Mapa interativo que mostra, por **município, bairro e região metropolitana**, onde o mesmo esforço de campanha tende a
trazer mais votos para Lula no 2º turno de 2026, com **temas sugeridos para cada lugar** a partir dos planos de governo
registrados no TSE. Todos os números vêm de dados públicos e agregados (TSE, IBGE) e trazem intervalo de incerteza.

**Mapa:** https://rafadaguia.github.io/analise-de-esforco-por-bairros-lula-2026/ ·
**Como usar:** https://rafadaguia.github.io/analise-de-esforco-por-bairros-lula-2026/guia.html ·
**Relatórios por cidade (PDF):** https://rafadaguia.github.io/analise-de-esforco-por-bairros-lula-2026/relatorios/00_INDICE.pdf

## Objetivo

Este trabalho existe para ajudar no planejamento tático de organizações e grupos de campanha: definir onde concentrar forças. Entre o 1º turno (4 de outubro) e o 2º turno (25 de outubro de 2026) são só três semanas, e não há tempo nem gente para estar em todo lugar. O mapa, os relatórios e as tabelas apontam em que estados, cidades e bairros o mesmo esforço tende a render mais votos para Lula, o que fazer em cada lugar (conversa, reconquista ou levar gente às urnas) e com que temas. É uma ferramenta de triagem para decidir rápido, a ser conferida com quem conhece o território, e não uma previsão de resultado.

## O que o mapa mostra

* **Nota de 1 a 7** para cada município, bairro e região metropolitana. A nota 7 indica onde o esforço tende a render mais
  votos novos. Ela combina os votos a recuperar por eleitor, a chance de que levar mais gente às urnas ajude Lula, a
  firmeza da estimativa e o tamanho do eleitorado.
* **Votos que dá para recuperar:** os votos que Lula perdeu além da média do país entre 2022 e 2026, mais o ganho de
  levar mais gente às urnas onde isso tende a ajudá-lo.
* **Temas para conversar:** temas com mais força para Lula no lugar, temas que o plano de Flávio Bolsonaro não trata,
  temas disputados e temas a evitar, com citação e página do plano oficial.
* **Relatório em PDF por cidade:** os 5.571 municípios têm um relatório com resumo, o que fazer,
  principais achados (histórico do PT, abstenção, renda, Bolsa Família, emprego, região metropolitana), áreas prioritárias
  e temas, com a posição da cidade no país e entre cidades do mesmo porte. O botão "Baixar o relatório" aparece na ficha da cidade e dos bairros.
* **Soberania nacional:** força do tema nas cidades expostas ao tarifaço dos EUA (exportações, Comex Stat) e na Amazônia
  Legal.

## Como ler (e o que o mapa não diz)

* Fala de **lugares, não de pessoas**. A média de um bairro não descreve quem mora nele (falácia ecológica).
* As pessoas votam onde estão inscritas, que nem sempre é o bairro onde moram.
* **Não é previsão.** Os números mostram o que acontece se o comportamento de 2022 entre os turnos se repetir. Os
  intervalos medem a incerteza dentro de uma eleição, não uma mudança de comportamento entre eleições.
* A nota serve para **triagem**: ela muda com os pesos, o método e o desenho das áreas.
* Em BA, CE, PA e RJ, a estimativa é **menos segura** (os cálculos não convergiram bem), e o mapa avisa. SP, MG e ES saíram
  dessa lista em 09/10, depois de um reajuste com o dobro de cadeias.
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
| `docs/` | o site (GitHub Pages): mapas de municípios, bairros e regiões metropolitanas, o guia "Como usar" e os relatórios em PDF (`docs/relatorios/`) |
| `bairros/` | o código da análise, etapa por etapa (`b01` a `b16`), e os insumos (`insumos/`: pesquisas, temas, contexto, catálogo das malhas de prefeitura) |
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
$P bairros/rodar_ei.py U4 --paralelo 2 --ufs $($P bairros/escolher_ajuste.py U4 instaveis) --tune 10000 --draws 1500 --cadeias 12 \
  --sufixo _extralongo && $P bairros/escolher_ajuste.py U4 incorporar MC_extralongo
$P bairros/b06_montecarlo_bairros.py --unidade U4 --metodo MC --sorteios 10000 && $P bairros/b08_esforco.py --unidade U4 --metodo MC
$P bairros/b13_planos.py && $P bairros/b14_soberania.py --unidade U4 && $P bairros/b09_temas.py --unidade U4
$P bairros/b12_tabelas.py --unidade U4 --metodo MC
$P mapa/construir_mapa_bairros.py --unidade U4 --metodo MC
$P bairros/b15_relatorios_cidades.py && PUPPETEER_DIR=<pasta com node_modules/puppeteer-core> $P bairros/b16_relatorios_pdf.py --publico
mapa/preparar_pages.sh docs
```

* O MCMC leva várias horas (paralelizado por UF). O Monte Carlo usa a GPU quando disponível (PyTorch MPS ou CUDA).
* A etapa `b13_planos.py` usa um modelo de linguagem local pelo [Ollama](https://ollama.com) (`gemma4:31b`).
* Sementes fixas em todos os scripts. O MCMC não é bit a bit reprodutível entre máquinas; os diagnósticos ficam
  registrados por UF.
* Os relatórios por cidade (`b15`) são regras fixas sobre os números, sem texto gerado por modelo de linguagem; o PDF
  (`b16`) usa o Chrome sem interface por meio do `puppeteer-core` (Node.js).
* Para ver o site localmente: `npx http-server docs` (o PMTiles precisa de um servidor com requisições parciais).

## Todas as fontes de dados

Tudo o que entrou no estudo, com o uso de cada fonte. São dados públicos e agregados: nenhum dado de pessoa
identificável foi usado.

### Tribunal Superior Eleitoral (TSE), Portal de Dados Abertos

* **Votação por seção eleitoral**, presidente, 1º e 2º turnos de 2010, 2014, 2018 e 2022 e 1º turno de 2026
  (arquivo de 2026 publicado em 06/10/2026). Base de todo o estudo: votos de cada candidato em cada urna.
* **Detalhe da votação por seção**: eleitores aptos, comparecimento, abstenção, brancos e nulos.
* **Eleitorado por local de votação** (2010 a 2026): endereço, bairro declarado e coordenadas de cada escola de votação.
  Usado para pôr cada urna no mapa.
* **Votação por candidato, município e zona** (1994 a 2026): série histórica e conferência dos totais.
* **Planos de governo registrados** no sistema DivulgaCandContas: Lula (PT) e Flávio Bolsonaro (PL). Base dos temas e das
  citações. Os arquivos estão na pasta `Plano de governo/`.
* **Registro das pesquisas eleitorais** (número de registro, amostra, margem de erro).

### Instituto Brasileiro de Geografia e Estatística (IBGE)

* **Malha de setores censitários do Censo 2022** (468 mil setores): a menor divisão do território.
* **Malhas de bairros, distritos e subdistritos de 2022**: os bairros oficiais (18.269, em 895 municípios).
* **Agregados por setor censitário do Censo 2022**: população, idade, alfabetização e domicílios (abastecimento de água,
  esgoto e coleta de lixo). A tabela de cor ou raça foi lida para o perfil das áreas, mas **não entra em nenhuma nota nem em
  nenhuma sugestão de tema**.
* **Rendimento do responsável pelo domicílio, por setor (Censo 2022)**: renda média de cada área.
* **Favelas e comunidades urbanas (Censo 2022)**: setores identificados como favela.
* **Composição das regiões metropolitanas, RIDEs e aglomerações urbanas** (referência 31/12/2025).
* **Regiões geográficas imediatas e intermediárias** e **malhas de municípios e estados**.
* **SIDRA**: população, renda e alfabetização por município (estudo municipal de origem).

### Prefeituras e governos estaduais

* **Malhas de bairros de 30 prefeituras**, usadas só na variante de comparação: Aracaju, Belo Horizonte, Brasília (GDF),
  Curitiba, Diadema, Duque de Caxias, Florianópolis, Fortaleza, Guarulhos, João Pessoa, Juiz de Fora, Londrina, Maceió
  (portal de dados do Governo de Alagoas), Manaus, Maringá, Mogi das Cruzes, Natal, Niterói, Ponta Grossa, Porto Alegre,
  Porto Velho, Recife, Rio de Janeiro, Salvador, Santo André, Santos, São Bernardo do Campo, São Paulo (GeoSampa),
  Teresina e Vitória. Endereço e conferência de cada uma: `bairros/insumos/prefeituras/catalogo.csv`.

### Outros órgãos federais

* **Ministério do Trabalho e Emprego (MTE), Novo CAGED**: saldo de empregos formais por município (12 meses até
  agosto de 2026 e ano de 2025).
* **Ministério do Desenvolvimento e Assistência Social (MDS), VIS DATA / MI Social**: famílias no Bolsa Família, valor
  médio e famílias no CadÚnico, por município (agosto e setembro de 2026).
* **Ministério do Desenvolvimento, Indústria, Comércio e Serviços (MDIC), Comex Stat**: exportações de 2025 por
  município, para os EUA e no total. Base do tema soberania nacional.

### Pesquisas de opinião

* **Datafolha**: relatórios completos do 2º turno (registros BR-08039/2026, de 29/09 a 01/10/2026, e BR-04496/2026, de
  18 e 19/08/2026) e pesquisas sobre o principal problema do país.
* **AtlasIntel**: 20 pesquisas estaduais do 2º turno (27/09 a 02/10/2026) e Latam Pulse (AtlasIntel/Bloomberg).
* **Quaest** (contratantes TV Globo/O Globo, Pax e Genial): principal problema do país e apoio à defesa da soberania.
* **Ipsos**, "What Worries the World" (setembro de 2026).
* Lista com registro, amostra e margem de erro: `bairros/insumos/pesquisas/pesquisas.csv` e
  `bairros/insumos/temas/importancia_temas.csv`.

### Veículos de imprensa e agências de checagem

Usados para localizar números publicados de pesquisas e declarações públicas dos candidatos (cada linha com link e data em
`bairros/insumos/temas/`): Agência Lupa, Aos Fatos, Brasil de Fato, CNN Brasil, Congresso em Foco, Diário de Pernambuco,
Diário do Grande ABC, Estado de Minas, Estadão/Broadcast (via Terra), Gazeta do Povo, InfoMoney, Jornal Opção, Metrópoles,
NC News, Poder360 e SBT News.

### Mapas, nomes e recursos visuais

* **OpenStreetMap** (consulta pela Overpass API, 08/10/2026): nomes de bairros e localidades onde o IBGE não tem bairro.
  © colaboradores do OpenStreetMap, licença ODbL.
* **Coordenadas das sedes municipais**: base aberta kelvins/municipios-brasileiros (licença MIT).
* **Glifos Noto Sans** (Protomaps basemaps-assets), **fontes Archivo e Instrument Sans** (Google Fonts), todas com licença
  SIL OFL, e **logo da Estel Tecnologia** (estel.tec.br).

### O que não foi usado

* RAIS (exige login para a tabela municipal) e qualquer microdado de pessoa.
* Religião, escolaridade por nível e renda por faixa por bairro: não existem no Censo 2022 publicado e não foram estimados.
* Orientação sexual: nunca estimada.

## Ferramentas

* **Python 3.12**: linguagem de toda a análise.
* **DuckDB**: banco de dados analítico que lê direto os arquivos do TSE e do IBGE (dezenas de milhões de linhas) e faz as
  somas por seção, local e área.
* **pandas e NumPy**: tabelas e contas.
* **GeoPandas, Shapely e pyogrio**: mapas e geometria (ponto dentro de polígono, união de setores em áreas).
* **scikit-learn (k-means) e SciPy**: agrupamento das escolas de votação em áreas onde a cidade não tem bairros oficiais;
  busca de vizinhos e otimização.
* **RapidFuzz**: comparação aproximada de nomes (bairro declarado no TSE contra bairro do IBGE).
* **PyMC, PyTensor e nutpie**: o modelo estatístico e o amostrador MCMC (NUTS) que estima as transferências de votos.
* **ArviZ e xarray**: diagnóstico das cadeias (R-hat, tamanho efetivo da amostra) e armazenamento dos resultados.
* **PyTorch**: simulação de Monte Carlo na placa de vídeo (GPU), com 10.000 sorteios.
* **joblib**: processamento em paralelo por estado.
* **Ollama com o modelo gemma4 (31B)**: modelo de linguagem rodando no próprio computador, sem envio de dados, que
  classificou os 566 parágrafos dos planos de governo por tema. Cada classificação foi conferida por regras no texto.
* **Apple Vision (ocrmac)**: leitura (OCR) das tabelas em imagem dos relatórios da AtlasIntel, no próprio computador.
* **PyMuPDF**: leitura do texto dos planos de governo e dos relatórios de pesquisa em PDF.
* **tippecanoe e PMTiles**: transformam as 19 mil áreas em "blocos" de mapa leves, servidos num único arquivo.
* **MapLibre GL JS**: o mapa interativo no navegador, sem servidor e sem serviços externos.
* **Jupyter**: o notebook técnico (`analise_bairros.ipynb`) com todas as tabelas e diagnósticos.
* **python-markdown e Chrome sem interface (puppeteer-core)**: geração dos relatórios em PDF de cada cidade.

## Metodologias

* **Geocodificação dos locais de votação.** Cada escola de votação recebe a coordenada oficial do TSE (99,4% dos
  eleitores). Sem coordenada, usa-se a de outro ano, o nome do bairro declarado ou, por último, o município.
* **Construção das áreas.** O resultado das urnas é somado por escola e levado ao bairro do IBGE onde a escola fica.
  Onde a cidade não tem bairros oficiais, as escolas próximas são agrupadas (k-means) e a área é o entorno delas.
  Áreas com menos de 1.000 eleitores são juntadas à vizinha. Resultado: 19.191 áreas.
* **Inferência ecológica RxC hierárquica** (Rosen, Jiang, King e Tanner, 2001). O voto é secreto: não se sabe para
  onde foi cada eleitor. O modelo estima, a partir dos totais de cada área no 1º e no 2º turno de 2022, que fração dos
  eleitores de cada candidato (e de quem não votou) foi para Lula, para o adversário ou ficou de fora. A estimativa usa
  níveis encaixados (país, estado, região metropolitana, município e área), para que áreas pequenas aprendam com as
  vizinhas.
* **MCMC e diagnóstico.** O modelo é ajustado por amostragem (NUTS), com 6 a 12 cadeias independentes por estado.
  Cadeias presas numa solução pior são descartadas. Onde o R-hat passa de 1,05 ou sobram poucas cadeias boas, o mapa
  avisa que a estimativa é menos segura.
* **Validação.** O modelo foi ajustado sem 20% das áreas e testado nelas: o resultado real ficou dentro do intervalo de
  90% em 95,7% dos casos. Também foi testado entre eleições (2018 → 2022 e 2014 → 2018), onde acerta menos: por isso os
  intervalos não cobrem mudança de comportamento entre eleições.
* **Simulação de Monte Carlo.** 10.000 sorteios dos parâmetros estimados aplicados ao 1º turno de 2026, em dois cenários
  (repetição de 2022 e eleitores de outros candidatos mais para Flávio). Daí saem as medianas e os intervalos de 90%.
* **Votos que dá para recuperar.** Terreno perdido (queda de Lula entre 2022 e 2026 além da média do país) mais o ganho de
  levar 2 em cada 100 eleitores a mais às urnas, só onde isso tende a ajudar Lula.
* **Nota de 1 a 7.** Junta quatro medidas, cada uma em posição relativa (de 0 a 1) entre as áreas: votos a recuperar por
  eleitor (peso 55%), chance de a mobilização ajudar (15%), firmeza da estimativa (15%) e tamanho do eleitorado (15%). As
  áreas são divididas em sete grupos do mesmo tamanho. Municípios e regiões metropolitanas recebem a nota da mesma forma.
* **Temas por lugar.** Importância do tema nas pesquisas nacionais × relevância para o perfil da área no Censo (renda,
  saneamento, favelas, área rural, exposição ao tarifaço) × força das propostas de cada plano de governo (compromissos e
  metas contados parágrafo a parágrafo). Daí saem os temas para puxar, de contraste, disputados e a evitar.
* **Soberania nacional.** Exposição da cidade ao mercado dos EUA (exportações por eleitor e parcela das exportações) e
  Amazônia Legal.
* **Relatórios por cidade.** Para os 5.571 municípios do país, os achados saem de regras fixas sobre
  os números, sem texto gerado por modelo de linguagem: cada frase mostra o número que a sustenta.
* **Estimativa por pesquisa (MrsP, comparação).** As pesquisas estaduais foram combinadas com o perfil do Censo numa
  estimativa por área, usada só para comparar com o modelo eleitoral. Ela não entra no mapa.

## Licença

Código, tabelas e mapas desta análise: [Creative Commons Atribuição 4.0 Internacional (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/deed.pt-br) (ver `LICENSE`). Ao reutilizar, cite: "Estel Tecnologia (estel.tec.br), Análise de esforço por bairro: 2º turno de 2026". Os dados de terceiros mantêm suas licenças: os nomes derivados do
OpenStreetMap seguem a ODbL, e as bibliotecas e fontes em `mapa/lib/` seguem as licenças incluídas na pasta.
