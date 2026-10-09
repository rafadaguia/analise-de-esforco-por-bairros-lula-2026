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
  avisa que a estimativa é menos segura. Nesses estados, um teste extra refaz a nota de cada área com grupos diferentes
  de cadeias e compara com o ruído normal da simulação: se a nota não muda além do ruído, o aviso fica mais leve
  ("cálculo difícil, mas a nota foi conferida e é estável").
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
