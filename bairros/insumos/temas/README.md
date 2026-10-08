# Matriz de temas: Lula (PT) x Flávio Bolsonaro (PL), 2º turno de 2026

Levantamento feito em 07 e 08/10/2026.

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `matriz_temas.csv` | 61 linhas: tema × candidato × fonte. Colunas: `tema, candidato, posicao_resumo, trecho, fonte_tipo (plano_governo/declaracao/checagem), url, veiculo, data, verificacao` |
| `importancia_temas.csv` | 41 linhas, com números publicados de pesquisas sobre o "maior/principal problema do país" |
| `propostas_paragrafos.csv`, `propostas_por_tema.csv` | Os planos de governo oficiais (pasta `Plano de governo/`), por parágrafo e por tema, com página e citação literal (`bairros/b13_planos.py`) |

### Temas cobertos
Emprego; jornada 6x1; renda e salário mínimo; custo de vida, inflação e alimentos; saúde (SUS); educação; segurança pública; moradia (MCMV/Casa Verde e Amarela); transporte e mobilidade; programas sociais; impostos (isenção do IR); previdência; agronegócio e meio ambiente; costumes e religião. Também entraram quatro temas com destaque na campanha: corrupção, que é o 2º problema mais citado na Quaest de setembro; instituições (STF, fim da reeleição, "censura"); endividamento e apostas.

### Critério da coluna `verificacao`
- `primaria`: texto do próprio plano de governo, lido no PDF.
- `secundaria`: declaração noticiada por pelo menos dois veículos identificáveis, ou checagem de agência (Lupa, Aos Fatos).
- `nao_verificado`: declaração que encontrei em um único veículo. São 5 linhas e precisam de confirmação antes de ir para a matéria.
- Nenhuma célula tema × candidato ficou sem fonte, então nenhuma linha leva `sem_fonte`.

## Fontes

**Planos de governo**
- Lula/PT, "Programa de Governo 2026", 84 p. O endereço oficial no TSE é `divulgacandcontas.tse.jus.br/divulga/rest/arquivo/doc/120016993257`. **Esse endereço devolveu "Access Denied" (HTTP 403, Akamai) à requisição automatizada, e não tentei contornar o bloqueio.** Por isso usei a cópia publicada pelo Congresso em Foco em 08/08/2026. SHA-256: `75e2dab7…e47b`.
- Flávio/PL, "Para o Brasil Vencer o Atraso", 76 p. Usei a cópia publicada pelo Poder360 em 13/08/2026 (`static.poder360.com.br/...FLAVIO-BOLSONARO-PARA-O-BRASIL-VENCER-O-ATRASO-1-1.pdf`). SHA-256: `ff60b7ae…b4f0`. Não achei o link direto do TSE para esse plano.
- **Pendência:** comparar as duas cópias com os PDFs do DivulgaCandContas, abrindo pelo navegador, e checar se houve plano substituído depois do registro. A matéria do Congresso em Foco fala em "novo plano".

**Declarações:** Poder360, CNN Brasil, SBT News, Exame, InfoMoney/Reuters, Congresso em Foco, Estado de Minas, Estadão/Broadcast (via Terra), Gazeta do Povo, Diário do Grande ABC, Jornal Opção e NC News. Os links estão em cada linha.

**Checagens:** Agência Lupa (01/10 e 04/10/2026) e Aos Fatos (02/10/2026, sobre a live de Flávio). Não encontrei checagem do Comprova sobre esses temas.

**Pesquisas:** Quaest/Globo (BR-07065/2026), Quaest/Pax, Datafolha (março), AtlasIntel/Bloomberg e Ipsos "What Worries the World".

## Limitações (ler antes de usar)

1. **Os trechos de declarações vieram de resumos automáticos das páginas.** Uma ferramenta de leitura web resumiu cada página antes de eu ver o texto. As citações parecem literais, mas **é preciso conferir cada `trecho` de `declaracao` na matéria original antes de publicar.** As linhas de checagem marcadas "[paráfrase da checagem]" não são citação literal.
2. **Acentos foram removidos** de todos os campos dos CSVs, inclusive dos trechos. Para citar, copie o texto acentuado do PDF ou da matéria. Nos planos, o número da página está em `posicao_resumo`.
3. **Datas:** nos planos, `data` é a data de publicação da cópia, não a do protocolo no TSE. Nas declarações, é a data da fala quando a reportagem informa; se não, é a data da matéria.
4. **Ausências que pesam no 2º turno.** O plano de Flávio **não menciona salário mínimo nem a isenção do IR até R$ 5 mil**: as duas posições dele vêm de falas (Veja, 15/6; Jornal Nacional, 27/8) e de seu coordenador econômico, Adolfo Sachsida (25/9). O plano de Lula **não menciona "tarifa zero"** no transporte, embora o tema tenha sido citado por Haddad. Também **não menciona aborto**. A posição de Lula sobre aborto que circula ("sou contra o aborto") é de **abril de 2022** e ficou fora da matriz porque não é desta campanha.
5. **Falas de terceiros:** a linha de Sachsida (salário mínimo e Previdência) e a carta de evangélicos do PT (8/6) não são falas dos candidatos. Isso está indicado em `posicao_resumo`.
6. **Episódios em disputa:**
   - Vídeo de Flávio sobre o preço da carne: a coligação de Lula foi ao TSE alegando montagem fora de contexto. Não verifiquei se o TSE já decidiu.
   - Frase de Flávio sobre "decretar que o Brasil é do Senhor Jesus Cristo": a campanha diz que se tratava de uma oração simbólica na posse.
   - Ao noticiar a crítica, a Exame tem título e primeiro parágrafo que se contradizem; usei a citação do SBT News.
   - Cuidado com acusações entre candidatos (por exemplo, "pai do tigrinho" e a associação de Lula a pedofilia, apontadas como falsas por Lupa e Aos Fatos): reproduzir sem a checagem ao lado traz **risco de difamação**. Passar pela edição.
7. **Lacunas de declaração:** não encontrei falas recentes dos dois sobre educação, moradia e transporte, nem de Flávio sobre segurança fora do plano. Nesses temas a matriz se apoia só nos planos.
8. **Viés das fontes:** algumas matérias vêm de veículos com linha editorial marcada (Gazeta do Povo, Brasil 247, Revista Fórum). Usei esses veículos só para corroborar e privilegiei o veículo mais neutro na coluna `url`.

## Pesquisas: cuidados metodológicos

- **As perguntas não são comparáveis entre institutos.** Quaest e Datafolha usam resposta única (estimulada ou espontânea, conforme o instituto). AtlasIntel e Ipsos aceitam **múltipla escolha**, e por isso os percentuais somam mais de 100%. Não ranqueie temas misturando institutos.
- **Quaest:** há duas pesquisas próximas. A Quaest/Globo, com eleitores (30/8–1/9, BR-07065/2026), mostra violência com 31%. A Quaest/Pax, com população de 16+ anos (12–15/9), mostra violência com 28% e corrupção com 22%. Uma matéria do Brasil 247 atribui outra combinação de números a "10–13/9, BR-03607/2026" que **não consegui reconciliar** com as duas, e por isso ficou fora.
- **Datafolha:** o dado mais recente que encontrei é de **março de 2026** (saúde 21%, segurança 19%). Não achei Datafolha de "maior problema" de agosto a outubro de 2026. Os números da Quaest/Globo vieram de um veículo secundário (Diário de Pernambuco).
- **Recorte de renda até 2 SM:** o único número publicado que achei é o de corrupção no Datafolha de março (6%). Não encontrei "maior problema" por renda em pesquisas de setembro ou outubro. Para isso, seria preciso pedir os relatórios completos aos institutos.
- **Ipsos:** a amostra brasileira é online, mais urbana e mais escolarizada, e não tem registro no TSE. O slide com o dado do Brasil (52% para crime e violência) traz o rótulo "August 2026 | Wave 223" dentro do relatório de setembro (onda 225). Confirme a onda antes de citar.
- **Nenhuma das pesquisas é posterior ao 1º turno** (04/10/2026).

## Revisão humana recomendada
- Editor: conferir literalmente as citações (item 1) e as 5 linhas `nao_verificado`.
- Jurídico: qualquer uso das acusações mútuas citadas nas checagens.
