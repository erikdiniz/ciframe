# Proposta — Sequências de Acordes Customizadas

## Abordagem escolhida

O catálogo de músicas/gêneros continua vindo do CSV em memória; **apenas o
catálogo de sequências** vai para um SQLite local. A busca por sequência passa
a ser calculada em tempo real sobre `musica.cifra`, com **uma regra única e
restrita**: a sequência precisa aparecer como bloco contíguo **e** a música não
pode ter nenhum acorde fora do conjunto da sequência. Essa é a mesma regra que
gerou as tags atuais, então as 6 originais continuam com os mesmos resultados e
qualquer sequência nova obedece à mesma definição. O frontend deixa de ter a
lista hardcoded e passa a ler o catálogo do backend, com um formulário de
cadastro.

### Algoritmo de matching

**Definição.** Uma sequência é uma lista ordenada de acordes. A comparação é
feita token a token contra `musica.cifra` — a lista ordenada, com repetições,
que vem do CSV — e **não** contra `musica.acordes`, que perde ordem e repetição.
Normaliza-se apenas a caixa para minúsculas; não se remove baixo (`/`), não se
normaliza enarmonia e não se ignora repetição. A sequência casa com a música se
aparecer como um **bloco contíguo** de tokens **e** se todos os acordes da
música pertencerem ao conjunto de acordes da sequência.

**Regra única.** Não existe modo permissivo nem tratamento especial para as 6:
a mesma condição vale para qualquer sequência do catálogo. É exatamente a
condição que `scripts/generate_data_set.py:7-24` usou para gerar `SEQ_FAMOSA`; a
pesquisa mostrou que ela reproduz as tags atuais sem diferença: 199/296/4/5/7/3
músicas para as sequências 0-5.

**Exemplo.** Para a sequência `C,G,Am,F`:

- `C G Am F` casa: o bloco existe e não há acorde fora do conjunto.
- `C G Am F Dm` **não** casa: `Dm` está fora do conjunto da sequência.
- `C G D Am F` não casa: o bloco não é contíguo.
- `C F Am G` não casa: a ordem é diferente.

**Por que essa regra.** Ela tem três virtudes: (1) é a regra histórica, então a
regressão das 6 é exata por construção; (2) dá um significado preciso e
testável a “a música usa essa sequência” — a música é construída só com aqueles
acordes; (3) mantém o catálogo uniforme, sem duas semânticas dependendo da
origem da linha. O custo é intencional: uma sequência nova só retorna músicas
que usam **exclusivamente** os acordes dela. Uma música com a progressão e uma
ponte com outro acorde não aparece; para incluí-la, o usuário precisaria
cadastrar uma sequência que cubra também os acordes da ponte e que ainda apareça
como bloco contíguo. Isso é uma decisão de produto, não um efeito colateral
escondido.

**Regressão.** O critério é igualdade de **conjunto**: para cada uma das 6, a
união de todas as páginas de `/similares` deve ser exatamente o conjunto de
`id_unico_musica` capturado antes da mudança. Ordem e composição de página não
fazem parte do contrato — a ordem atual depende da iteração de um `set` de
gêneros e varia com `PYTHONHASHSEED` (pesquisa §2.3). Para tornar a paginação
determinística, os resultados serão ordenados por popularidade decrescente e
`id_unico_musica` crescente antes do corte de 100. Isso pode mudar quais músicas
caem na página 1, mas não o conjunto; o frontend já ordena por popularidade
dentro da página, então o efeito visível é uma melhora, não uma quebra.

**Desempenho.** A varredura de 67.585 músicas leva ~400 ms (pesquisa §1.5). O
resultado por sequência é cacheado em memória (lista já ordenada, por `id` da
sequência); como o dataset é imutável durante o processo e as sequências não
têm update/delete, não há invalidação. A primeira busca de cada sequência paga
a varredura; as páginas seguintes filtram por gênero e cortam a lista. O cache
tem limite de entradas para não crescer sem controle.

### Banco de dados

SQLite via `sqlite3` da stdlib. Arquivo `db/deciframe.sqlite3` ao lado de
`main.py` (configurável por `DECIFRAME_DB`), criado e semeado de forma
idempotente no startup. Zero dependência nova; oferece transações e `UNIQUE`, e
um único arquivo cabe no container único local do ADR 0001. PostgreSQL/MySQL
exigiriam um serviço externo; JSON puro e TinyDB perderiam constraint/ACID
(TinyDB ainda adicionaria dependência); DuckDB adicionaria um binário grande
para um catálogo minúsculo. O catálogo de músicas/gêneros continua no CSV e em
memória; nada disso vai para o banco.

Persistência no Docker: volume nomeado `deciframe-db` montado em `/app/db`; o
Dockerfile declara `VOLUME ["/app/db"]` e o README passa a mostrar
`docker run -p 8080:8080 -v deciframe-db:/app/db ciframe`. `db/` entra em
`.gitignore` e `.dockerignore` para um banco local não ir para a imagem. Um
único worker do gunicorn torna a concorrência de escrita trivial; ainda assim,
a inicialização usa `CREATE TABLE IF NOT EXISTS`, seed idempotente,
`busy_timeout` e queries parametrizadas. Se o banco não puder ser aberto ou
inicializado, o processo falha no startup; não há fallback silencioso para um
catálogo vazio.

A coluna `SEQ_FAMOSA` continua sendo lida para `Musica.seqs_famosas` **apenas**
para não alterar a resposta de `/musica/<id>/`; ela deixa de ser a fonte da
busca por sequência. Um teste vai zerar `seqs_famosas` em memória e confirmar
que as 6 continuam retornando o baseline, provando que a busca não depende mais
do CSV.

### Esquema de dados (alto nível)

Uma única tabela `sequencias`:

| Campo | Tipo | Papel |
|---|---|---|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | identidade estável |
| `acordes` | `TEXT NOT NULL` | JSON da lista ordenada, com repetições |
| `chave` | `TEXT NOT NULL UNIQUE` | JSON canônico em minúsculas, para dedup e lookup |
| `criada_em` | `TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP` | timestamp UTC |

Não há coluna de modo: a regra de matching é a mesma para todo o catálogo. Seed:
as 6 originais com os acordes exatos de `main.py:40-45` (`Bm,G,D,A`;
`C,G,Am,F`; `Em,G`; `C,A7,Dm,G7`; `Gm,F`; `C,C7,F,Fm`). O seed insere se não
existir e não sobrescreve uma linha existente com a mesma `chave`. Sem tabela de
matches persistidos, sem `nome` e sem uma tabela normalizada de acordes: a lista
é pequena e sempre lida/gravada inteira. Sem Alembic; `CREATE TABLE IF NOT
EXISTS` e `PRAGMA user_version` são suficientes para a primeira versão.

### API

Todos os retornos continuam `json.dumps(...)` — string com
`Content-Type: text/html` — inclusive os novos e os erros.

**`GET /sequencias`** — catálogo em ordem de `id`:

```json
[
  {"id": 1, "acordes": ["Bm", "G", "D", "A"]},
  {"id": 7, "acordes": ["Am", "F", "C", "G"]}
]
```

Sem paginação: o catálogo é pequeno.

**`POST /sequencias`** — corpo JSON `{"acordes":["Am","F","C","G"]}`. Cria e
devolve `201` com `{"id":7,"acordes":[...],"duplicada":false}`. Se a chave já
existe, devolve `200` com a linha existente e `"duplicada":true`. É idempotente
de propósito: evita duplicata por duplo clique/retry e, quando alguém recadastra
uma das 6, devolve a original em vez de criar uma linha repetida. Validação
inválida devolve `400 {"erro":"..."}`. Sem login, sem `PUT`/`DELETE`.

**`GET /similares?sequencia=...`** — mesmo formato de hoje (array de músicas,
`pagina`, `generos`). Muda só a resolução: em vez de mapear para um índice de
tag, faz parse da lista por vírgula, normaliza, procura a `chave` no SQLite e
aplica a regra única. Se não achar, devolve `[]` com HTTP 200 (comportamento
atual). As 6 strings antigas continuam funcionando; variações de caixa e espaço
passam a funcionar também. O branch `acordes`/`id_unico_musica` não muda.

**Validação do cadastro.** 2 a 12 acordes; cada token com até 20 caracteres;
sem espaços em branco internos ou vírgulas; precisa começar por A-G (com `#`/`b`
opcional); e precisa existir no vocabulário de acordes do dataset, comparado em
minúsculas. A forma exibida é o token com a primeira letra maiúscula e o
restante preservado (`a#m` → `A#m`), para não escolher uma grafia errada como
`A#M`; a chave canônica é a lista em minúsculas.

**URL e `#`.** O frontend hoje concatena `similares?sequencia=C#,G`; o `#` vira
fragmento e o servidor recebe só `C`. A busca passa a usar
`$http.get("similares", {params: {...}})` (ou `encodeURIComponent`), para que
acordes com `#` funcionem. Isso é necessário para sequências novas e corrige um
bug latente da página.

### Frontend

Em `#/porsequencia`:

- `SequenciaController` carrega `GET /sequencias` no init e monta
  `vm.sequenciasFamosas` no formato que o template já usa
  (`acordes: [{acorde, cor}]`), com cor fixa `#2E1C74` como hoje. As 4
  hardcoded somem; as 6 aparecem, incluindo `Em G` e `C A7 Dm G7`.
- Estado de carregamento/erro do catálogo, com botão de tentar de novo.
- Formulário “Cadastrar nova sequência”: input de texto (`C, G, Am, F`),
  preview dos acordes em `<df-hex>` e botão que faz `POST /sequencias`. O parse
  do input é split por vírgula + trim; o backend valida. Em sucesso, a sequência
  entra na lista, é selecionada e a busca roda automaticamente; se
  `duplicada`, mostra “essa sequência já existia” e seleciona a existente.
  Erros 400 mostram a mensagem do backend.
- A busca continua em `pesquisarPorSequencia`; o seletor de gênero continua com
  a constante `GENEROS` (fora do escopo). O template de resultados não muda.
- Sem framework novo, sem build e sem serviço Angular: `$http` direto, como o
  resto do código.

## Alternativas consideradas e descartadas

- **Híbrido (regra restrita para as 6 e bloco contíguo permissivo para as
  novas)** — preservaria a regressão, mas daria dois significados diferentes a
  “sequência”, exigiria uma coluna de modo e faria o resultado depender da
  origem da linha. A decisão de produto é que a música não pode ter acorde fora
  da sequência, então o hibridismo foi descartado.
- **Bloco contíguo permissivo para todas** — é a leitura mais óbvia de “a
  sequência aparece”, mas quebra a regressão (`Em G` iria de 4 para 3.110) e
  aceita músicas com acordes fora da sequência, contra a definição escolhida.
  Descartada.
- **Manter as tags do CSV para as 6 e uma regra nova para as novas** — também
  preservaria a regressão, mas manteria a busca dependente de `SEQ_FAMOSA` e de
  um mapeamento de índices. A regra histórica é reproduzível em tempo real
  (pesquisa §2.2) e pode valer para todo o catálogo. Descartada.
- **Persistir os matches por sequência** — leitura rápida, mas envelhece quando
  o CSV muda, exige recompilar ao subir dataset novo e adiciona escrita no
  caminho de criação. Matching em tempo real + cache resolve. Descartada.
- **JSON puro, TinyDB, DuckDB, PostgreSQL/MySQL** — JSON puro e TinyDB perdem
  constraint/ACID (TinyDB ainda adiciona dependência); DuckDB adiciona binário
  grande; PostgreSQL/MySQL exigem serviço externo e contrariam o ADR 0001.
  Descartadas.
- **Picker de acordes em vez de texto** — mais guiado, mas o vocabulário real
  tem 6.653 tokens sujos e a paleta curada de `acordes.js` não cobre bemóis e
  qualidades. Texto + validação + preview é menor e mais honesto. Descartada.
- **`409 Conflict` para duplicata** — mais “REST”, porém pior para um catálogo
  anônimo em que duplo clique e retry são comuns. O `200` idempotente devolve a
  sequência existente e o frontend a seleciona. Descartada.
- **Nome/descrição da sequência** — não é requisito; a lista de acordes já
  identifica a sequência. Fora do escopo.

## Escopo explícito

**Dentro do escopo:**

- Banco SQLite com tabela `sequencias`, inicialização/seed idempotente e
  persistência via volume nomeado.
- Motor de matching com a regra única (bloco contíguo + vocabulário fechado),
  cache em memória e ordenação determinística.
- Endpoints `GET /sequencias`, `POST /sequencias` e a nova resolução de
  `GET /similares?sequencia=...`, mantendo `json.dumps(...)`.
- Frontend `#/porsequencia` lendo o catálogo do backend, formulário de cadastro,
  estados de carregamento/erro e busca automática após cadastrar.
- Correção da montagem da URL de busca para acordes com `#`.
- Testes automatizados de matching e API, incluindo o baseline das 6 e a
  verificação de que a busca não lê mais `seqs_famosas`.
- Atualização de `README.md`, `AGENTS.md`, `Dockerfile`, `.gitignore` e
  `.dockerignore` para refletir o banco e o volume.

**Fora do escopo (e por quê):**

- Login, autoria, moderação, rate limiting, edição e remoção de sequências — o
  requisito é catálogo aberto e anônimo, e o deploy é local-only; isso teria
  que ser revisto antes de expor o catálogo publicamente.
- Nome, descrição, tags ou favoritos de sequência — não são requisitos.
- Migrar músicas/gêneros para o banco ou alterar o CSV/`SEQ_FAMOSA` — fixado
  pelo enunciado; a coluna antiga fica só para compatibilidade de
  `/musica/<id>/`.
- Trocar `json.dumps` por `jsonify`, criar envelope de resposta ou metadados de
  paginação — mudaria o contrato atual.
- Modernizar o AngularJS, adicionar build ou redesenhar a página — o ADR 0003
  apenas libera tocar no frontend; não exige modernização.
- Trocar a lista hardcoded de gêneros pelo endpoint `/generos` — é uma limpeza
  separada, não parte do catálogo de sequências.
- Um modo de matching permissivo (bloco contíguo sem vocabulário fechado) — a
  definição escolhida é a restrita; se isso mudar, entra como opção explícita
  depois.
- Normalização enarmônica, remoção de baixo ou teoria musical além do
  vocabulário do dataset — remover baixo quebra 3 das 6 (pesquisa §1.3).
- Persistir matches, paginar o catálogo de sequências ou pré-computar todas as
  sequências no startup — o cache lazy resolve com menos complexidade.
- Testes E2E de browser e deploy em nuvem/multi-container — não há ferramental
  no repositório e o ADR 0001 fixa o deploy local single-container.
