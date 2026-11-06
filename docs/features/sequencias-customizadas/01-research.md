# Pesquisa — Sequências de Acordes Customizadas

## Resumo

Hoje a busca por sequência **não calcula nada sobre a cifra**: ela converte a
string recebida em uma das 6 chaves hardcoded de `main.py:40-45` e verifica se
o índice correspondente está na lista `musica.seqs_famosas`
(`main.py:190-223`), que veio pronta da coluna `SEQ_FAMOSA` do CSV. Essa coluna
foi gerada offline por `scripts/generate_data_set.py:7-24`, e a condição
efetiva do gerador é mais restritiva do que “a progressão aparece na música”:
exige que a sequência seja uma **substring contígua** da cifra **e** que a
música **não use nenhum acorde fora** do conjunto da sequência. Nos 67.585
registros do CSV isso resulta em apenas 199/296/4/5/7/3 músicas para as seis
sequências. A boa notícia é que essa condição é reproduzível exatamente em
tempo real (candidato **B**); o algoritmo natural de subsequência contígua
(candidato **A**) devolve sempre um superconjunto, com 91 a 3.106 músicas a
mais por sequência. O frontend tem uma lista própria de 4 sequências
hardcoded — diferentes das 6 do backend —, não usa o endpoint `/generos` e não
tem formulário nem chamada de escrita. Para persistir o catálogo, SQLite é
viável no container atual (módulo `sqlite3` presente no `python:3.9-slim`,
versão 3.46.1), mas exige um volume nomeado para sobreviver à recriação do
container; usar `/app/data` como ponto de montagem é frágil (bind mount
esconde o CSV; volume nomeado novo copia o CSV para dentro do volume, mas
passa a congelá-lo).

### Checklist das perguntas

1. **Algoritmo de matching** → seção 1.
2. **Validação da hipótese contra os dados reais** → seção 2.
3. **Banco de dados embarcado e persistência no Docker** → seção 3.
4. **Frontend existente (`#/porsequencia`)** → seção 4.

As seções 1-4 são o registro das descobertas; os trade-offs estão no fim.

## 1. Algoritmo de matching

### 1.1 O que existe hoje

O caminho completo da requisição está em `main.py:170-201`:

```python
elif sequencia_tag:
    acordes = sequencia_tag.replace(',','')
    similares = []

    if acordes in sequencias:
        id_seq = sequencias[acordes]
        similares = get_pagina(get_similares_por_sequencia(id_seq, generos_key), pagina_tag)
    return json.dumps(similares)
```

- `sequencias` (`main.py:40-45`) mapeia a string sem vírgulas para um inteiro
  de 0 a 5. Esse inteiro **não é um id de catálogo**: é o índice da tag
  pré-computada no CSV.
- `get_similares_por_sequencia` (`main.py:203-223`) só faz
  `if str(id_seq) in musica.seqs_famosas`.
- Se a chave não existir, a resposta é `[]` com HTTP 200. Não há erro, nem
  fallback para busca por acordes.
- O lookup é case-sensitive e não remove espaços: `Bm,G,D,A` vira `BmGDA` e
  funciona; `bm,g,d,a` ou `Bm, G, D, A` não funcionam.

A coluna `SEQ_FAMOSA` é lida em `main.py:63` e entregue ao objeto `Musica` em
`main.py:69-72`. O modelo (`musica.py:1-25`) guarda:

- `cifra` (`musica.py:16`): lista **ordenada** de acordes, com repetições,
  exatamente como veio do CSV;
- `acordes` (`musica.py:17`): `list(set(cifra))`, ou seja, **sem ordem e sem
  repetição**;
- `seqs_famosas` (`musica.py:18`): as tags pré-computadas.

Portanto, qualquer matching que dependa de ordem ou repetição **tem** que usar
`musica.cifra`; `musica.acordes` só serve para a busca por conjunto de acordes
que já existe (`main.py:230-263`).

### 1.2 De onde vêm as tags

`scripts/generate_data_set.py:7-24` define `get_famosas`:

```python
def get_famosas(acorde):
    seqs = ['bm;g;d;a','c;g;am;f', 'em;g' , 'c;a7;dm;g7', 'gm;f', 'c;c7;f;fm' ]
    out = []
    for i in range(len(seqs)):
        s = seqs[i]
        acorde = acorde.lower()
        if s in acorde:                       # substring contígua
            achou = True
            tem_seqs = []
            for l in acorde.split(';'):       # cada acorde da música
                tokens = s.split(';')
                if l not in tokens:           # tem que estar no conjunto da sequência
                    achou = False
                    break
            if achou:
                tem_seqs.append(str(i))
                out.append("-".join(tem_seqs))
    return out
```

A condição efetiva, reproduzida em Python 3, é:

```python
def get_famosas_reproduzido(cifra, seq):
    acorde = ';'.join(cifra).lower()
    s = ';'.join(seq).lower()
    if s in acorde:                       # 1) sequência contígua
        for l in acorde.split(';'):       # 2) todo acorde da música...
            if l not in s.split(';'):     # ...pertence ao conjunto da sequência
                return False
        return True
    return False
```

A condição (2) é o que explica os números pequenos: as 199 músicas tagueadas
com a sequência 0 usam **exatamente** `Bm`, `G`, `D`, `A`; as 4 tagueadas com
a sequência 2 usam **exatamente** `Em` e `G`. Não há comentário no script
explicando essa condição adicional; ela é o comportamento real do gerador.

### 1.3 Ordem, repetição e normalização

**A ordem importa?** Sim, nas duas definições consideradas e na tag atual. Para
`C G Am F`, os dados mostram:

| critério | músicas |
|---|---:|
| contígua `C, G, Am, F` | 1.216 |
| contígua na ordem `C, F, Am, G` | 208 |
| subsequência ordenada (com buracos) | 5.887 |
| contenção de conjunto (sem ordem) | 6.894 |

Ou seja, trocar a ordem muda o resultado em mais de 5x; ignorar a ordem muda
em mais de 5x no outro sentido.

**Repetições importam?** Dependem da definição. Em A/B, a sequência precisa
aparecer como um bloco contíguo; repetições dentro da música fazem parte do
bloco, e uma sequência cadastrada com repetição (ex.: `C, C, G`) só casa se a
repetição existir na cifra naquela ordem. `musica.acordes` não serve para isso
porque `list(set(...))` descarta repetições. Há 31.760 músicas com pelo menos
uma repetição consecutiva de acorde.

**É preciso normalizar?** Há decisões reais e não neutras:

- **Caixa:** o gerador offline já compara tudo em minúsculas. Para as 6
  sequências, comparar em minúsculas não altera nenhum resultado
  (199/296/4/5/7/3), então é uma normalização segura para o critério de
  regressão e útil para entrada do usuário (`bm,g,d,a` passaria a casar).
- **Baixo (`/`):** 267.926 tokens (7,64% do total) têm `/`. Remover o baixo
  antes de comparar **quebra** a reprodução exata em 3 das 6 sequências:
  seq 0 vai de 199→222, seq 1 de 296→330 e seq 4 de 7→8. É uma decisão de
  produto, não uma limpeza neutra.
- **Enarmonia (`C#` vs `Db`):** não existe normalização no código atual; as
  duas grafias são acordes diferentes nos dados.
- **Espaços:** `limpa_cifra` (`main.py:11-23`) quebra por espaço e nenhum
  token do CSV contém espaço; mas a URL não remove espaços, então
  `Bm, G, D, A` falha no lookup.
- **Tokens sujos:** o CSV tem `2x`, `1a.vez`, `:`, `(Cm)`, `add9`, `m`, `e`,
  `eb7b9b5` etc. O endpoint `/acordes` devolve os 6.653 tokens distintos, sem
  curadoria. Qualquer validação precisa decidir entre aceitar essa lista ou
  uma lista curada.

### 1.4 Definições candidatas

Todas usam `musica.cifra`:

- **A — contígua exata:** existe `i` tal que `cifra[i:i+n] == sequencia`.
  É a leitura natural de “a sequência aparece na música”.
- **B — contígua + vocabulário:** A **e** `set(cifra) <= set(sequencia)`.
  É a reprodução exata do gerador offline.

Contagens sobre os dados reais:

| seq | acordes | tag atual | A contígua | B contígua+vocab. | subsequência ordenada | contenção de conjunto | A − atual |
|---|---|---:|---:|---:|---:|---:|---:|
| 0 | Bm G D A | 199 | 866 | 199 | 4.763 | 5.768 | +667 |
| 1 | C G Am F | 296 | 1.216 | 296 | 5.887 | 6.894 | +920 |
| 2 | Em G | 4 | 3.110 | 4 | 13.643 | 14.160 | +3.106 |
| 3 | C A7 Dm G7 | 5 | 96 | 5 | 427 | 582 | +91 |
| 4 | Gm F | 7 | 1.039 | 7 | 3.641 | 3.847 | +1.032 |
| 5 | C C7 F Fm | 3 | 132 | 3 | 280 | 365 | +129 |

**B é exatamente igual à tag atual** nas 6 sequências. **A é sempre um
superconjunto** (nenhuma música tagueada é perdida), mas acrescenta de 91 a
3.106 músicas. Exemplo concreto: “5 Seconds Of Summer — Airplanes” contém
`C, G, Am, F` contiguamente, mas usa também `Bb` e `Em`; logo aparece em A e
não em B.

### 1.5 Desempenho

O matching em tempo real varre 67.585 músicas e 3.505.331 tokens. Medições no
container `python:3.9-slim` (requisições via gunicorn; varreduras via
`docker exec`):

- requisição atual por uma das 6: ~40-48 ms (só faz `in` na lista de tags,
  `main.py:209`);
- varredura A em Python puro: ~390-404 ms;
- varredura B: ~407-416 ms;
- contenção de conjunto sozinha: ~125-129 ms.

Não existe índice hoje. O custo de A/B inclui a varredura e a criação de
slices `cifra[i:i+n]`.

## 2. Validação da hipótese

### 2.1 Método

1. Parse do `data/top/dataset_final.csv` replicando exatamente
   `main.py:49-98` (mesmo `limpa_cifra`, mesmo
   `replace('"','').replace('NA','')`, mesmo `split(',')`).
2. Construção dos conjuntos de músicas tagueadas para cada inteiro 0-5.
3. Construção dos conjuntos produzidos por A e B sobre `musica.cifra`.
4. Comparação com as respostas reais do app rodando no container, somando
   todas as páginas de `/similares?sequencia=...`.

### 2.2 Resultado

| seq | acordes | tag no CSV | reprodução B | API real (todas as páginas) | A contígua |
|---|---|---:|---:|---:|---:|
| 0 | Bm G D A | 199 | 199 | 199 | 866 |
| 1 | C G Am F | 296 | 296 | 296 | 1.216 |
| 2 | Em G | 4 | 4 | 4 | 3.110 |
| 3 | C A7 Dm G7 | 5 | 5 | 5 | 96 |
| 4 | Gm F | 7 | 7 | 7 | 1.039 |
| 5 | C C7 F Fm | 3 | 3 | 3 | 132 |

- **B reproduz exatamente** os conjuntos atuais (diferença zero nos dois
  sentidos).
- **A nunca perde** uma música tagueada, mas adiciona muitas.
- A API real confirma os totais de B: as páginas somam 199, 296, 4, 5, 7 e 3
  resultados distintos.

### 2.3 O que isso implica para a regressão

Se “mesmos resultados” for interpretado como **igualdade exata de conjunto**,
o algoritmo em tempo real precisa ser B — ou as 6 originais precisam de um
tratamento especial (por exemplo, manter as tags antigas para elas). Se for
interpretado como **“nenhum resultado atual pode desaparecer”**, A passa, mas
o número de resultados muda (ex.: `Em G` de 4 para 3.110). Essa é a decisão
central que a proposta precisa tomar; a pesquisa não a toma aqui.

Um detalhe de teste: a paginação atual **não é estável entre processos**.
`generos` nasce de um `set` (`main.py:37-39`, `92`) e `apply_filtro`
(`main.py:266-272`) percorre essa lista; com `PYTHONHASHSEED=1` e
`PYTHONHASHSEED=2`, a página 1 de `C,G,Am,F` tem **conjuntos diferentes**
(embora a união de todas as páginas seja a mesma). Portanto o teste de
regressão deve comparar o conjunto completo (união das páginas), não o
conteúdo de uma página específica.

## 3. Banco de dados

### 3.1 Opções embarcadas

| opção | serviço externo | dependência nova | persistência | observações |
|---|---|---|---|---|
| **SQLite** | não | não (`sqlite3` é stdlib) | arquivo único | relacional, ACID, `UNIQUE`, transações; verificado no `python:3.9-slim` (3.46.1) |
| TinyDB | não | sim (`tinydb`) | arquivo JSON | simples, mas sem ACID/concorrência real; bom só para catálogo minúsculo |
| DuckDB | não | sim (`duckdb`) | arquivo único | embarcado, analítico; binário maior, overkill para um catálogo pequeno |
| JSON puro | não | não | arquivo | não é banco; exige escrita atômica (temp + rename) e não tem consulta/constraint |
| `dbm`/`shelve` | não | não (stdlib) | arquivos | chave-valor, sem SQL; locking e portabilidade limitados |
| PostgreSQL/MySQL | **sim** | sim | serviço | exigiria outro container/serviço, contrariando o ADR 0001 (single container local-only) |

SQLite é a única opção relacional, transacional e **sem dependência nova**.
As demais são viáveis tecnicamente, mas introduzem dependência, perda de
garantias ou um serviço externo.

### 3.2 Implicações no Dockerfile e na persistência

- O `Dockerfile:1-12` atual não tem `VOLUME`; o `README.md:15-18` roda
  `docker run -p 8080:8080 ciframe`, sem volume.
- `docker restart` / `stop` + `start` preservam a camada gravável do
  container; um arquivo SQLite dentro dela sobrevive.
- `docker rm` e recriação (por exemplo, após novo `docker build`) descartam
  a camada gravável. Para sobreviver a isso, é preciso volume nomeado (ex.:
  `-v deciframe-db:/app/db`) ou bind mount.
- O ponto de montagem **não pode** ser `/app` (esconderia o código). Montar
  em `/app/data` é frágil: bind mount esconde `data/top/dataset_final.csv`
  (lido em `main.py:49`); volume nomeado recém-criado copia o CSV para dentro
  do volume, mas passa a congelá-lo (atualizações da imagem não chegam ao
  volume). Um diretório novo como `/app/db` ou `/app/state` evita os dois
  problemas.
- `COPY . .` copiaria um arquivo de banco local para a imagem; o
  `.dockerignore` atual não o exclui. A inicialização/seed precisa ser
  idempotente (`CREATE TABLE IF NOT EXISTS`, `INSERT OR IGNORE`).
- O `CMD` do gunicorn não passa `-w`, então sobe **1 worker**; com um único
  processo, a concorrência de escrita no SQLite é trivial. Se o número de
  workers aumentar, entram em cena WAL e `busy_timeout`.
- O container roda como root; permissões do arquivo/volume não são um
  problema hoje.

## 4. Frontend existente

### 4.1 O que a página faz

- Rota `#/porsequencia`: `static/assets/js/routes.js:17-21` → template
  `templates/sequencia.html`, controller `SequenciaController` com
  `controllerAs: "Sequencia"`.
- `static/assets/js/controllers/sequencia.js:2-37` define **4 sequências
  hardcoded** (`sequencia1`..`sequencia4`) e as empilha em
  `vm.sequenciasFamosas`. Cada uma tem `index` (sempre `1`, não usado) e um
  array `acordes` de `{acorde, cor}`, com cor fixa `#2E1C74`.
- `static/templates/sequencia.html:5-8` renderiza a lista com `ng-repeat` e
  `<df-hex>`; o clique chama `Sequencia.pesquisarPorSequencia(sequencia)`.
- `sequencia.js:55-61` monta a string com vírgulas; `sequencia.js:63-90` faz
  `$http.get("similares?sequencia=...")` (URL relativa; o constante
  `RESTAPI` de `app.js:3-5` não é usado) e, opcionalmente, acrescenta
  `&generos=...`.
- `sequencia.html:40-59` renderiza os cards com
  `orderBy:'-popularidade'` e `ng-hide="music.diferenca.length"`. Os
  resultados de sequência não incluem `diferenca` (`main.py:210-220`), então
  a expressão é *undefined*/falsa e os cards aparecem. O clique abre
  `music.url` (`sequencia.js:97-99`).
- O seletor de gênero usa o constante `GENEROS` hardcoded em
  `app.js:6-58`, não o endpoint `/generos` (que existe e devolve 52 gêneros).

### 4.2 A discrepância 4 × 6

| objeto no JS | acordes | chave no backend | id da tag |
|---|---|---|---|
| `sequencia1` | Bm, G, D, A | `BmGDA` | 0 |
| `sequencia2` | C, G, Am, F | `CGAmF` | 1 |
| `sequencia3` | Gm, F | `GmF` | 4 |
| `sequencia4` | C, C7, F, Fm | `CC7FFm` | 5 |

Faltam `Em G` (id 2) e `C A7 Dm G7` (id 3). A lista do frontend não é um
subconjunto ordenado das 6: ela pula duas e reordena as restantes. É um estado
pré-existente do código, não um erro da tarefa.

### 4.3 O que não existe

- Nenhum formulário de cadastro, campo de nome, botão de salvar ou chamada
  `$http.post`/`put`/`delete` em `static/assets/js` (busca por esses verbos
  não retorna nada).
- Nenhum serviço Angular ou camada de dados; os controllers chamam `$http`
  diretamente.
- Nenhum teste automatizado no repositório; o único arquivo com “test” no
  nome é o template `04-test-report.md`.

### 4.4 Restrições que qualquer solução precisa acomodar

- O catálogo exibido tem que vir do backend; manter a lista hardcoded não
  atende ao requisito.
- O cadastro precisa de uma UI nova e de uma chamada de escrita; hoje não há
  nenhuma das duas.
- Cada acorde renderizado por `<df-hex>` precisa de uma cor
  (`acorde-color`); o catálogo novo terá que fornecer ou derivar isso.
- A resposta de busca deve manter os campos que o template usa
  (`nome_musica`, `nome_artista`, `genero`, `popularidade`, `url`;
  `diferenca` é opcional), senão os cards quebram ou ficam vazios.
- A chamada continua relativa (`similares?...`) e a resposta continua
  `json.dumps(...)` como string; `jsonify` mudaria o contrato.
- O formato de URL atual (`sequencia=Bm,G,D,A`) é o que o frontend sabe
  montar; qualquer API nova precisa ser compatível com ele ou o controller
  precisa mudar junto.

## Trade-offs identificados

### Algoritmo

- **A — contígua exata:** é a leitura natural de “a progressão aparece na
  música”, preserva ordem e repetição e nunca perde os resultados atuais.
  Contra: muda o número de resultados das 6 (ex.: `Em G` de 4 para 3.110), o
  que pode ser lido como quebra do critério de regressão.
- **B — contígua + vocabulário:** reproduz exatamente as 6 tags e o teste de
  regressão fica trivial. Contra: é uma condição muito restritiva (a música
  não pode ter nenhum acorde fora da sequência); para sequências novas ela
  exclui músicas que contêm a progressão, mas têm ponte/bridge com outro
  acorde. É o comportamento herdado do gerador offline.
- **Híbrido:** A para sequências novas e B (ou as tags antigas persistidas)
  para as 6 originais. Preserva a regressão e melhora o comportamento novo,
  ao custo de duas semânticas e de um flag/caminho especial no código.
- **Subsequência ordenada (com buracos):** mais generosa; para `C G Am F`
  devolve 5.887 músicas. Contra: “aparece” fica vago e o resultado cresce
  muito.
- **Contenção de conjunto (sem ordem):** é o que a busca por acordes já faz,
  mas ignora a definição de “sequência”; devolve 6.894 músicas para
  `C G Am F` e não distingue ordens.
- **Normalização:** comparar em minúsculas é seguro para a regressão das 6;
  remover baixo (`/`) quebra a igualdade em 3 das 6; enarmonia e tokens sujos
  exigiriam uma tabela de normalização que hoje não existe.

### Banco

- **SQLite:** zero dependência, transacional, arquivo único, encaixa no
  container único. Contra: é um arquivo que precisa de volume para sobreviver
  a `docker rm`; concorrência de escrita exige cuidado se houver mais de um
  worker.
- **TinyDB/JSON:** mais simples de começar, mas sem ACID/concorrência e com
  risco de corrupção em escrita concorrente; adiciona dependência no caso do
  TinyDB.
- **DuckDB:** embarcado e robusto, mas binário grande e foco analítico;
  overkill para um catálogo que deve crescer devagar.
- **PostgreSQL/MySQL:** melhor concorrência e ferramental, mas exige serviço
  externo e contraria o ADR 0001; só faria sentido se o deploy deixasse de ser
  single-container.
- **Volume:** nomeado (`-v deciframe-db:/app/db`) é explícito e sobrevive à
  recriação; bind mount é fácil de inspecionar, mas depende do caminho do
  host. Sem volume, `docker rm` perde tudo. O mount não pode cobrir
  `/app/data`.

### Frontend

- **Buscar o catálogo no backend e renderizar dinamicamente:** atende ao
  requisito e elimina a divergência 4 × 6; exige estado de carregamento/erro
  e adaptação do `ng-repeat`.
- **Manter a lista hardcoded e só acrescentar as novas:** mudança menor, mas
  o catálogo continua mentindo (não reflete o backend) e as 6 originais
  continuam divergindo.
- **Formulário em texto livre (ex.: “C, G, Am, F”):** simples, mas precisa de
  parsing/validação e lida com tokens sujos; **picker de acordes** (reusando
  `df-hex` ou a paleta de `acordes.js`) é mais guiado, porém mais trabalho de
  UI. O endpoint `/acordes` tem 6.653 tokens, incluindo lixo; a paleta curada
  de `acordes.js` tem poucos acordes e não cobre bemóis/qualidades.
- **Nome da sequência:** opcional (só a lista de acordes) é o mínimo do
  requisito; obrigatório melhora a exibição, mas adiciona validação e um
  campo que o backend atual não tem.
- **Duplicatas:** rejeitar com erro, devolver a existente ou permitir
  duplicatas são três comportamentos possíveis; hoje não existe conceito de
  duplicata porque o catálogo é um dicionário hardcoded.
- **Cores:** manter a cor fixa `#2E1C74` é o menor esforço; derivar cor por
  nota mantém a identidade visual da página de acordes, mas é lógica nova.

### Regressão e testes

- Comparar **conjunto completo** (união de todas as páginas) é estável;
  comparar página a página não é, por causa da ordem de `generos` descrita em
  2.3.
- Exigir igualdade exata força B (ou tratamento especial das 6); exigir
  apenas “nenhum resultado atual perdido” permite A.
- O teste de regressão precisa de uma linha de base capturada **antes** da
  mudança; ela pode ser gerada a partir do CSV (como nesta pesquisa) ou de
  respostas reais do container.

## Evidências detalhadas

O mapa completo do código, os números brutos, os comandos executados e a
reprodução da condição de `SEQ_FAMOSA` estão em
[`research/sequencias-customizadas.md`](../../../research/sequencias-customizadas.md).

Resumo dos comandos de runtime usados:

```bash
docker build -t ciframe-research .
docker run -d --name ciframe-research-run -p 18080:8080 ciframe-research
curl -s http://localhost:18080/generos
curl -s 'http://localhost:18080/similares?sequencia=C,G,Am,F&pagina=1'
curl -s 'http://localhost:18080/similares?sequencia=Zz,Zz'
docker run --rm python:3.9-slim python -c "import sqlite3; print(sqlite3.sqlite_version)"
```

Resultados: `/generos` devolve 52 gêneros com `Content-Type: text/html`;
`C,G,Am,F` devolve 100 + 100 + 96 resultados nas páginas 1-3; sequência
desconhecida devolve `[]` com HTTP 200; `sqlite3` existe no `python:3.9-slim`
(3.46.1).
