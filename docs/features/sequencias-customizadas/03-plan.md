# Plano — Sequências de Acordes Customizadas

## Contexto

Hoje `GET /similares?sequencia=...` não calcula nada sobre a cifra: ele converte
a string em uma das 6 chaves hardcoded de `main.py:40-45` e consulta a tag
pré-computada `musica.seqs_famosas` (`main.py:190-223`). O frontend
`#/porsequencia` tem outras 4 sequências hardcoded e nenhum formulário de
cadastro. A proposta (`02-proposal.md`) e o ADR 0002 decidem trocar isso por um
catálogo SQLite de sequências e por um matching único e restrito calculado em
tempo real.

A regra que este plano executa, para **todas** as sequências, sem modo e sem
exceção para as 6, é: a sequência precisa aparecer como bloco contíguo em
`musica.cifra` **e** `set(musica.cifra) <= set(sequencia)`. A comparação é feita
em `musica.cifra` (lista ordenada, com repetições), nunca em `musica.acordes`
(set sem ordem). As 6 originais passam a ser apenas as primeiras linhas do
catálogo semeado.

Restrições fixas que o plano não pode violar:

- Músicas e gêneros continuam vindo do CSV em memória; só o catálogo de
  sequências vai para o banco.
- Deploy continua single-container local-only (ADR 0001).
- Endpoints continuam devolvendo `json.dumps(...)` como string, com
  `Content-Type: text/html`; nada de `jsonify`.
- As 6 sequências originais precisam devolver exatamente o mesmo conjunto de
  músicas de antes da mudança.

Ordem de execução: baseline → banco/seed → matching → API → frontend →
infraestrutura/documentação → testes e fechamento. O baseline é o primeiro
passo e precisa ser capturado **antes de qualquer alteração em `main.py`**.

## Passos

### 0. Baseline antes de tocar no código

1. [ ] Subir a versão atual sem alterações (Docker na porta 8080 ou virtualenv
   na 5000) e confirmar que `GET /generos` responde uma lista JSON.
2. [ ] Capturar, para cada uma das 6, a união de todas as páginas de
   `GET /similares?sequencia=...`, sem filtro de gênero, guardando
   `id_unico_musica` na ordem em que aparecer. Um script ad-hoc em
   `/tmp/opencode` basta; o importante é não editar `main.py` antes disso.
3. [ ] Gravar o resultado em `tests/fixtures/baseline_6_sequencias.json`, com
   as listas de IDs, a contagem esperada e o `sha256` de
   `data/top/dataset_final.csv`. Exemplo de captura:

   ```python
   import hashlib, json, pathlib, urllib.parse, urllib.request

   SEQS = {
       "Bm,G,D,A": 199,
       "C,G,Am,F": 296,
       "Em,G": 4,
       "C,A7,Dm,G7": 5,
       "Gm,F": 7,
       "C,C7,F,Fm": 3,
   }
   BASE = "http://localhost:8080/similares"  # 5000 no virtualenv

   saida = {}
   for seq, esperado in SEQS.items():
       ids, pagina = [], 1
       while True:
           qs = urllib.parse.urlencode({"sequencia": seq, "pagina": pagina})
           with urllib.request.urlopen(f"{BASE}?{qs}") as resposta:
               lote = json.load(resposta)
           if not lote:
               break
           ids.extend(m["id_unico_musica"] for m in lote)
           pagina += 1
       assert len(ids) == esperado, (seq, len(ids), esperado)
       saida[seq] = ids

   csv = pathlib.Path("data/top/dataset_final.csv").read_bytes()
   fixture = {
       "capturado_de": "GET /similares antes da migração, união de todas as páginas",
       "dataset_sha256": hashlib.sha256(csv).hexdigest(),
       "sequencias": saida,
   }
   pathlib.Path("tests/fixtures").mkdir(parents=True, exist_ok=True)
   pathlib.Path("tests/fixtures/baseline_6_sequencias.json").write_text(
       json.dumps(fixture, ensure_ascii=False, indent=2) + "\n"
   )
   ```

4. [ ] Conferir as contagens `199/296/4/5/7/3` e guardar o `sha256` no relatório
   de testes. Se alguma contagem divergir, parar e investigar antes de
   prosseguir: o baseline estaria errado.
5. [ ] Criar a estrutura `tests/` e o runner com `unittest` da stdlib. Nada de
   dependência nova em `requirements.txt`.
6. [ ] Commitar (ou ao menos congelar) o fixture antes da primeira alteração de
   código, para que o teste de regressão tenha uma referência que não foi
   produzida pela implementação nova.

### 1. Banco SQLite, schema e seed

1. [ ] Adicionar em `main.py` os imports necessários (`os`, `sqlite3`,
   `functools`) e a constante
   `CAMINHO_DB = os.environ.get("DECIFRAME_DB", "db/deciframe.sqlite3")`.
2. [ ] Implementar `conectar_db(caminho=None)`: cria o diretório pai se preciso,
   abre o arquivo com `sqlite3.connect`, configura `row_factory` e
   `PRAGMA busy_timeout = 5000`. A conexão é aberta e fechada por operação;
   não manter uma conexão global compartilhada entre threads.
3. [ ] Implementar `inicializar_db(caminho=None)` com DDL idempotente:

   ```sql
   CREATE TABLE IF NOT EXISTS sequencias (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     acordes TEXT NOT NULL,
     chave TEXT NOT NULL UNIQUE,
     criada_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
   );
   ```

   Usar `PRAGMA user_version`: se for 0, criar a tabela e gravar 1; se já for 1,
   seguir; qualquer outro valor falha no startup. Não criar arquivo de schema
   separado nem Alembic nesta primeira versão.
4. [ ] Implementar a chave canônica compartilhada por seed, POST e lookup:
   lista em minúsculas serializada como JSON compacto e estável
   (`json.dumps([...], ensure_ascii=False, separators=(",", ":"))`). A coluna
   `acordes` guarda a forma de exibição; a coluna `chave` guarda a forma
   canônica.
5. [ ] Semear as 6 na ordem de `main.py:40-45` com `INSERT OR IGNORE` por
   `chave`: `Bm,G,D,A`; `C,G,Am,F`; `Em,G`; `C,A7,Dm,G7`; `Gm,F`;
   `C,C7,F,Fm`. O seed não sobrescreve uma linha existente e não depende de IDs
   fixos; a identificação é sempre pela `chave`.
6. [ ] Chamar `inicializar_db()` no import, depois do carregamento do CSV e
   antes de registrar/servir as rotas. Se o banco não abrir ou não inicializar,
   levantar o erro e deixar o processo falhar; não cair para catálogo vazio.
7. [ ] Adicionar helpers pequenos: `listar_sequencias()` (ordem de `id`),
   `buscar_sequencia_por_chave(chave)` e `inserir_sequencia(acordes, chave)`
   (idempotente, devolve linha existente + indicador de duplicata).
8. [ ] Adicionar `db/` ao `.gitignore` e ao `.dockerignore` para que o banco de
   desenvolvimento não entre no git nem na imagem.
9. [ ] Garantir que nenhum atributo novo seja adicionado a `Musica`; a lista de
   músicas e o formato de `/musica/<id>/` continuam iguais.

### 2. Motor de matching e cache

1. [ ] Durante o carregamento do CSV, construir dois dicionários auxiliares em
   `main.py`, indexados por `id_unico_musica`:
   `cifras_lower` (lista de acordes em minúsculas, na ordem, com repetições) e
   `vocabularios` (`set` dos acordes em minúsculas). Não alterar `musica.py`.
2. [ ] Implementar `casa_sequencia(cifra_lower, vocabulario, seq)`:
   primeiro testar `vocabulario <= set(seq)` (descarte barato); depois procurar
   o bloco contíguo com `cifra_lower[i:i+n] == seq`. A sequência é uma tupla de
   tokens já normalizados em minúsculas.
3. [ ] Implementar `_matches_para_chave(chave)` com
   `@functools.lru_cache(maxsize=64)`. A chave do cache é a `chave` canônica
   (conteúdo), não o `id`; assim o seed e uma linha equivalente compartilham
   cache e a eviction é limitada. A função varre `musicas.values()`, filtra por
   `casa_sequencia` e devolve uma tupla de objetos `Musica` ordenada por
   `(-popularidade, id_unico_musica)`.
4. [ ] Não cachear dicionários de resposta: eles são montados somente para a
   página pedida, a partir dos objetos `Musica`, com os mesmos campos de
   `get_similares_por_sequencia` (`id_unico_musica`, `id_artista`, `id_musica`,
   `nome_artista`, `nome_musica`, `popularidade`, `acordes`, `genero`, `url`).
   Sem `diferenca` e sem `intersecao`, como hoje.
5. [ ] Aplicar o filtro de gênero depois do cache e antes da paginação,
   preservando o comportamento de `apply_filtro`: sem `generos`, todas as
   músicas; com `generos`, somente gêneros existentes no dataset. Reutilizar
   `get_pagina` com `TAM_PAGINA = 100`. Como `apply_filtro` reconstrói a
   coleção a partir dos buckets de gênero, o subconjunto do cache precisa ser
   filtrado com a mesma semântica (gêneros válidos), não passado direto para
   `apply_filtro`.
6. [ ] Manter temporariamente o dicionário `sequencias` de `main.py:40-45` e a
   função antiga `get_similares_por_sequencia`, para que `/similares` continue
   funcionando entre os passos; a remoção acontece no Passo 3, junto com a
   troca do ramo. O caminho novo não consulta `musica.seqs_famosas`.
7. [ ] Manter `get_similares` (busca por `acordes`/`id_unico_musica`) e a
   precedência de `/similares` intactos.

### 3. API

1. [ ] Implementar `GET /sequencias`: lê o catálogo em ordem de `id` e devolve
   `[{"id": 1, "acordes": ["Bm", "G", "D", "A"]}, ...]` com `json.dumps`.
   Sem paginação.
2. [ ] Implementar `POST /sequencias`:
   - corpo JSON `{"acordes": [...]}`; `request.get_json(silent=True)` e corpo
     inválido devolvem `400 {"erro": "..."}`;
   - fazer `strip` em cada item e validar 2–12 acordes; cada item string, sem
     espaços internos, sem vírgula, até 20 caracteres, começando por A–G (com
     `#`/`b` opcional) e presente no vocabulário `acordes_lower` do dataset;
   - normalizar a exibição para primeira letra maiúscula e restante preservado
     (`a#m` → `A#m`) e calcular a `chave` em minúsculas;
   - inserir com `INSERT OR IGNORE` e reler por `chave`; devolver
     `201 {"id": ..., "acordes": [...], "duplicada": false}` para linha nova e
     `200 {"id": ..., "acordes": [...], "duplicada": true}` para existente;
   - todos os retornos, inclusive erros, com `json.dumps`.
3. [ ] Adicionar `acordes_lower` ao carregamento do CSV, sem remover nem alterar
   o conjunto `acordes` usado por `/acordes`.
4. [ ] Reescrever o ramo `elif sequencia_tag` de `/similares`: fazer split por
   vírgula, `strip` em cada token, descartar tokens vazios, calcular a chave
   canônica e buscar a sequência no SQLite. Se não existir, devolver `[]` com
   HTTP 200. Se existir, usar o matching restrito, aplicar gênero e paginar.
   Remover o dicionário `sequencias` e a função antiga
   `get_similares_por_sequencia`, agora substituída por
   `get_similares_por_chave`.
5. [ ] Manter a precedência atual: `acordes` > `id_unico_musica` > `sequencia`.
   Variações de caixa e espaço em `sequencia` passam a funcionar; o ramo
   `acordes`/`id_unico_musica` não muda.
6. [ ] Verificar que `GET /similares?sequencia=C%23,G` chega ao backend com `#`
   decodificado e funciona para uma sequência cadastrada com `C#`; o problema
   de URL é corrigido no frontend, mas o backend precisa aceitar o valor
   codificado.
7. [ ] Não trocar `json.dumps` por `jsonify` em nenhum endpoint e não criar
   envelope de resposta.

### 4. Frontend `#/porsequencia`

1. [ ] Em `static/assets/js/controllers/sequencia.js`, remover os objetos
   `sequencia1`..`sequencia4` e a montagem hardcoded de
   `vm.sequenciasFamosas`.
2. [ ] No init do controller, chamar `carregarSequencias()`:
   `$http.get("sequencias")`, normalizar a resposta (se vier string, aplicar
   `angular.fromJson`) e mapear cada `{id, acordes}` para o formato do template
   (`{id, acordes: [{acorde, cor: "#2E1C74"}]}`). Expor
   `vm.carregandoSequencias`, `vm.erroSequencias` e uma função de retry.
3. [ ] Adicionar o formulário de cadastro no estado do controller: texto cru,
   preview dos acordes, `vm.cadastrando`, `vm.erroCadastro`,
   `vm.mensagemCadastro`. `cadastrarSequencia()` faz split por vírgula + trim,
   monta `{acordes: tokens}`, chama `$http.post("sequencias", ...)` e:
   - em `201`, recarrega o catálogo (ou insere o retorno), seleciona a sequência
     e roda a busca automaticamente;
   - em `200` com `duplicada: true`, mostra “essa sequência já existia”,
     seleciona a existente e roda a busca;
   - em `400`, exibe `data.erro` do backend.
4. [ ] Corrigir a montagem da busca em `pesquisarPorSequencia` para usar
   `$http.get("similares", {params: params})`, com `params.sequencia` igual à
   string de acordes separada por vírgula e `params.generos` só quando
   `vm.meuGenero` não for vazio. Isso faz o Angular codificar `#` como `%23` e
   corrige o bug latente de `C#` virar fragmento de URL.
5. [ ] Em `static/templates/sequencia.html`, manter o catálogo e os cards como
   estão, adicionando: estado de carregamento, estado de erro com botão de
   retry, formulário “Cadastrar nova sequência”, preview com `<df-hex>` e áreas
   de mensagem/erro. Não redesenhar a página nem trocar o seletor de gênero
   (`GENEROS` continua fora do escopo).
6. [ ] Testar manualmente no browser: as 6 aparecem (incluindo `Em G` e
   `C A7 Dm G7`), cadastro novo funciona, duplicata seleciona a existente,
   validação mostra erro, busca por sequência funciona, filtro de gênero
   continua funcionando e uma sequência com `#` busca corretamente. Fazer hard
   refresh para descartar JS antigo em cache.
7. [ ] Não adicionar framework, build step, serviço Angular ou dependência
   nova; usar `$http` direto, como o restante do código.
8. [ ] Adicionar “Carregar mais” nos resultados da busca, usando o parâmetro
   `pagina` já existente e sem metadados novos na resposta: acumular páginas,
   resetar em nova busca/gênero, ignorar respostas de buscas antigas e assumir
   que há mais enquanto o lote tiver 100 itens.
9. [ ] Limitar a altura do catálogo de sequências com rolagem, sem paginar
   `GET /sequencias`, para que o formulário de cadastro não seja empurrado para
   baixo quando o catálogo crescer.

### 5. Docker, volume e documentação

1. [ ] Adicionar `VOLUME ["/app/db"]` ao `Dockerfile`, sem mudar a base, o
   `CMD` ou o modelo single-container.
2. [ ] Atualizar o `README.md`: remover a afirmação de “sem banco”, explicar que
   o catálogo de sequências fica em SQLite e mostrar o comando com volume
   nomeado: `docker run -p 8080:8080 -v deciframe-db:/app/db ciframe`.
   Mencionar `DECIFRAME_DB` para um caminho alternativo e que o banco local é
   criado automaticamente.
3. [ ] Atualizar o `AGENTS.md`: stack (CSV em memória + SQLite só para
   sequências), run local, e gotcha de que apagar `db/deciframe.sqlite3` recria
   as 6 semeadas, mas perde as customizadas.
4. [ ] Garantir que `db/` está nos dois ignores e que o build não copia banco
   local para a imagem.
5. [ ] Construir e rodar a imagem com volume nomeado; cadastrar uma sequência,
   reiniciar o container e confirmar que ela continua no catálogo; recriar o
   container após rebuild mantendo o volume e confirmar de novo.
6. [ ] Confirmar que `docker run --rm ciframe ls -la /app/db` (sem volume) não
   mostra um banco versionado vindo da imagem.
7. [ ] Limpar containers/volumes de teste ao final para não deixar estado
   escondido no ambiente.

### 6. Testes, regressão e fechamento

1. [ ] Criar `tests/support.py` para configurar `DECIFRAME_DB` para um arquivo
   temporário **antes** de importar `main`, evitar escrever no `db/` do
   repositório e oferecer um helper para limpar/resemear o catálogo entre
   testes que escrevem. Todos os módulos de teste importam `tests.support`
   antes de `main`.
2. [ ] `tests/test_matching.py`: bloco contíguo, ordem diferente, acorde fora do
   conjunto, ausência de bloco, caixa diferente, repetição de acorde, cifra
   vazia e baixo (`/`) não normalizado.
3. [ ] `tests/test_db.py`: DDL idempotente, seed com 6 linhas, seed repetido sem
   duplicar, seed não sobrescreve linha existente, persistência ao fechar e
   reabrir o arquivo, e `DECIFRAME_DB` respeitado.
4. [ ] `tests/test_api.py`: `GET /sequencias`, `POST` novo (`201`), duplicata
   (`200` + `duplicada: true`), validações (`400`), busca por sequência
   existente, busca por sequência inexistente (`[]`, HTTP 200), variação de
   caixa/espaço, sequência com `#` codificado e `Content-Type: text/html` com
   corpo JSON em string.
5. [ ] `tests/test_regression.py`: para cada uma das 6, percorrer todas as
   páginas de `/similares?sequencia=...` e comparar a **união** dos
   `id_unico_musica` com o fixture; conferir também as contagens. Comparar
   conjuntos, nunca ordem ou composição de página.
6. [ ] Testar a independência de `SEQ_FAMOSA`: salvar o estado de
   `seqs_famosas`, zerar em memória, repetir as 6 buscas e confirmar que o
   resultado continua igual ao baseline; restaurar o estado em `finally`.
7. [ ] Testar que `/musica/<id>/` não ganhou campos novos: as chaves de
   `Musica.__dict__` continuam exatamente as atuais.
8. [ ] Rodar a suíte com `python -m unittest discover -s tests -v` e registrar
   no `04-test-report.md` a cobertura, o resultado da regressão, os comandos e
   o que ficou de fora (browser E2E e frontend automatizado, por exemplo).
9. [ ] Fazer o smoke test no Docker: `curl /generos`, `curl /sequencias`,
   `POST /sequencias`, busca pela sequência nova, busca pelas 6 e reinício com
   volume.
10. [ ] Gravar o GIF/vídeo de demonstração no browser exigido pela entrega:
    catálogo com as 6, cadastro de uma sequência nova, busca, duplicata e uma
    sequência com `#`.
11. [ ] Se a implementação mudar alguma decisão da proposta (regra, schema,
    status code, cache), atualizar este plano e a proposta/ADR **antes** de
    continuar. Não deixar o plano desatualizado.

## Arquivos afetados

| Arquivo | Mudança |
|---|---|
| `main.py` | Inicialização/seed do SQLite, chave canônica, validação, matching restrito, cache, `GET/POST /sequencias` e novo ramo de `/similares`. Remove o dicionário `sequencias` e a busca por `seqs_famosas`. |
| `musica.py` | Sem mudanças. Não adicionar atributos, para não alterar a saída de `/musica/<id>/`. |
| `static/assets/js/controllers/sequencia.js` | Remove as 4 sequências hardcoded; carrega o catálogo do backend; formulário/POST; retry; busca via `$http` com `params` (corrige `#`). |
| `static/templates/sequencia.html` | Estados de carregamento/erro, formulário de cadastro, preview e mensagens; catálogo e cards existentes são mantidos. |
| `Dockerfile` | `VOLUME ["/app/db"]`. |
| `README.md` | Documenta SQLite, `DECIFRAME_DB` e o volume nomeado no `docker run`. |
| `AGENTS.md` | Atualiza stack, run e gotchas do banco/seed. |
| `.gitignore` | Ignora `db/`. |
| `.dockerignore` | Ignora `db/`. |
| `tests/` (novo) | `support.py`, testes de matching, banco, API e regressão. |
| `tests/fixtures/baseline_6_sequencias.json` (novo) | Baseline das 6 capturado antes da mudança. |
| `db/` (novo, ignorado) | Banco SQLite de runtime; não versionado. |
| `requirements.txt` | Sem mudanças; `sqlite3` é da stdlib. |
| `static/assets/js/app.js` | Sem mudanças; `GENEROS` e `RESTAPI` continuam fora do escopo. |
| `docs/features/sequencias-customizadas/04-test-report.md` | Preenchido na fase 5 com resultados reais. |

## Estratégia de testes

- **Unitários**: função de matching e chave canônica com cifras pequenas e
  casos de borda (ordem, repetição, caixa, baixo, vocabulário fechado).
- **Banco**: init idempotente, seed, deduplicação, persistência em arquivo e
  respeito a `DECIFRAME_DB`. Cada teste usa um arquivo temporário; nunca o
  `db/` do repositório.
- **API**: Flask `app.test_client()`, incluindo status, corpo `json.dumps`,
  `Content-Type`, validação e idempotência do POST.
- **Regressão**: fixture capturado antes da mudança; união de todas as páginas,
  comparação por conjunto. A ordem e o tamanho de página não fazem parte do
  contrato, porque a paginação atual depende de `PYTHONHASHSEED`.
- **Manual**: browser para o fluxo completo do frontend e para o caso `#`;
  Docker para volume, restart e rebuild. Não há infraestrutura de teste de
  browser no repositório, e criar uma está fora do escopo.
- **Comando único**: `python -m unittest discover -s tests -v`.

## Riscos e mitigação

| Risco | Como detectar | Mitigação |
|---|---|---|
| Baseline capturado depois de alterar `main.py` ou com paginação incompleta. | Contagens diferentes de `199/296/4/5/7/3` ou fixture com menos IDs. | Capturar no passo 0, antes de editar; percorrer páginas até vir `[]`; guardar `sha256` do CSV e revisar o fixture. |
| Paginação não determinística por causa do `set` de gêneros. | Página 1 muda entre execuções, mas o total não. | Comparar somente a união por conjunto; ordenar o resultado novo por popularidade desc + `id_unico_musica` asc antes do corte. |
| Adicionar campos a `Musica` e quebrar `/musica/<id>/`. | Teste das chaves de `__dict__` falha. | Manter `musica.py` intacto e usar dicionários auxiliares em `main.py` para `cifras_lower`/`vocabularios`. |
| Seed duplicar ou sobrescrever sequência existente. | Catálogo com duas linhas iguais ou forma de exibição alterada. | `INSERT OR IGNORE` + `UNIQUE(chave)`; teste de seed repetido e de linha existente. |
| Banco não sobrevive a `docker rm`/rebuild. | Sequência some após recriar o container. | Volume nomeado `deciframe-db:/app/db`, `VOLUME` no Dockerfile e teste de restart/rebuild. |
| Banco local entra na imagem ou no git. | `docker run --rm ciframe ls -la /app/db` mostra arquivo; `git status` mostra `db/`. | `db/` em `.gitignore` e `.dockerignore`; conferir o build context. |
| Banco não abre ou o diretório não é gravável. | Processo sobe com catálogo vazio ou erro obscuro. | Falhar rápido com erro claro no startup; criar o diretório pai; testar caminho inválido. |
| Cache cresce demais ou fica velho. | Uso de memória alto ou resultado desatualizado após mudança no catálogo. | `lru_cache(maxsize=64)` com tuplas de `Musica` (não dicionários de resposta); catálogo é append-only, sem update/delete. |
| Busca de sequência com `#` continua quebrada. | `C#` chega ao backend como `C`. | `$http.get(..., {params})` no frontend; teste de API com `C%23`; verificação manual no browser. |
| Angular não interpreta a resposta `text/html` como JSON. | `data` chega como string e o `ng-repeat` não renderiza. | Manter `json.dumps` e usar `angular.fromJson` defensivamente no controller; validar manualmente. |
| Vocabulário do dataset não contém um acorde que o usuário espera. | POST devolve `400` com “acorde desconhecido”. | Mensagem de erro clara; teste garante que os acordes do seed existem em `acordes_lower`. Se o CSV mudar, revisar o seed. |
| Duas escritas simultâneas no SQLite. | `database is locked` ou duplicata. | `busy_timeout`, `UNIQUE(chave)` e `INSERT OR IGNORE`; o deploy atual tem 1 worker do gunicorn. |
| Testes mutam estado global (`seqs_famosas`) e contaminam os seguintes. | Regressão passa isolada e falha na suíte. | Salvar/restaurar em `try/finally` ou rodar o cenário em subprocesso; limpar o banco temporário entre testes que escrevem. |
| Teste de regressão vira um teste do dataset, não da feature. | Fixture quebra após qualquer atualização do CSV. | Documentar que o fixture está atrelado ao `sha256` atual; se o dataset mudar de propósito, recapturar o baseline e atualizar o relatório. |
| Frontend não tem teste automatizado. | Regressão de template/controller passa despercebida. | Assumir a limitação no relatório; checklist manual e gravação do GIF/vídeo demonstrando o fluxo. |

## Definição de pronto

- [ ] As 6 sequências originais retornam exatamente o mesmo conjunto de
  `id_unico_musica` do baseline, com contagens `199/296/4/5/7/3`.
- [ ] A busca não depende mais de `musica.seqs_famosas`; o teste que zera a
  lista em memória continua devolvendo o baseline.
- [ ] Qualquer sequência cadastrada pode ser buscada e obedece à regra única:
  bloco contíguo em `musica.cifra` e nenhum acorde fora do conjunto da
  sequência.
- [ ] `GET /sequencias` lista o catálogo e `POST /sequencias` cadastra de forma
  idempotente, com `201`/`200`/`400` e mensagens de erro úteis.
- [ ] O catálogo persiste após reiniciar o processo, recriar o container e
  reconstruir a imagem usando o volume nomeado.
- [ ] O frontend `#/porsequencia` carrega as 6 do backend (incluindo `Em G` e
  `C A7 Dm G7`), permite cadastrar, selecionar, buscar, filtrar por gênero e
  lida com carregamento/erro/duplicata; sequências com `#` funcionam.
- [ ] Endpoints continuam devolvendo `json.dumps(...)` como string, com
  `Content-Type: text/html`, inclusive os novos e os erros.
- [ ] `/musica/<id>/` não mudou de formato; `Musica.__dict__` tem as mesmas
  chaves de antes.
- [ ] `README.md`, `AGENTS.md`, `Dockerfile`, `.gitignore` e `.dockerignore`
  refletem o banco e o volume.
- [ ] O GIF/vídeo de demonstração do fluxo no browser foi gravado para a
  entrega.
- [ ] `python -m unittest discover -s tests -v` passa, e o
  `04-test-report.md` registra cobertura, regressão, comandos e limitações com
  honestidade.
- [ ] Se alguma decisão mudou durante a implementação, este plano e a
  proposta/ADR foram atualizados antes de continuar.
