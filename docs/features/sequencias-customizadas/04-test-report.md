# Relatório de testes — Sequências de Acordes Customizadas

## Cobertura

Suíte `unittest` da stdlib, sem dependência nova: **33 testes**, todos passando.
Todos os módulos importam `tests.support` antes de `main`; o helper aponta
`DECIFRAME_DB` para um diretório temporário, então a suíte nunca escreve no
`db/` do repositório.

**`tests/test_matching.py` (10 testes)** — regra única de casamento:

- bloco contíguo no início e no meio da cifra;
- ordem diferente, bloco ausente e acorde da cifra fora da sequência não casam;
- caixa diferente é equivalente;
- repetição de acorde e sequência vazia;
- cifra vazia não casa;
- baixo com `/` não é normalizado (`E/B` ≠ `E`).

**`tests/test_db.py` (8 testes)** — SQLite:

- DDL e seed idempotentes (`PRAGMA user_version`, 6 linhas);
- seed cria as 6 na ordem e com os ids 1–6;
- seed repetido não duplica e não sobrescreve uma linha existente;
- sequência persiste ao fechar e reabrir a conexão;
- inserção duplicada devolve a linha original;
- banco novo cria o diretório pai;
- `DECIFRAME_DB` é respeitado e aponta para fora de `db/`.

**`tests/test_api.py` (12 testes)** — HTTP com `app.test_client()`:

- `GET /sequencias` devolve as 6 sem paginação;
- respostas continuam sendo JSON em string com `Content-Type: text/html`;
- `POST /sequencias`: `201` para nova, `200` + `duplicada: true` para
  duplicata (inclusive caixa/espaço e as 6 originais);
- validações devolvem `400` com `erro`: corpo inválido, lista ausente, poucos
  ou muitos acordes, acorde desconhecido, vazio, com espaço interno, com
  vírgula, longo demais, começando fora de A–G e não-string;
- busca por sequência existente (primeira página), inexistente (`[]`, HTTP
  200), com variação de caixa/espaço e com `#` codificado;
- sequência recém-cadastrada pode ser buscada, com e sem variação de caixa.

**`tests/test_regression.py` (3 testes)** — regressão:

- as 6 sequências originais, percorrendo todas as páginas de
  `/similares?sequencia=...`, batem com o fixture por conjunto de
  `id_unico_musica` e por contagem;
- o resultado não depende de `musica.seqs_famosas`: o teste zera a lista em
  memória, limpa o cache, repete as 6 buscas e restaura o estado em
  `finally`;
- `/musica/<id>/` mantém exatamente as chaves atuais de `Musica.__dict__`.

## Teste de regressão obrigatório

O fixture `tests/fixtures/baseline_6_sequencias.json` foi capturado no Passo 0,
antes de qualquer mudança, a partir da união de todas as páginas de
`/similares`. O dataset usado tem `sha256`
`5f94f49b945ffac76f9a114b353b51d6a07b9e6feeb1243ce5989295234b9207`.

Resultado da suíte e do smoke no Docker — mesmas contagens e mesmos conjuntos:

| Sequência | Músicas |
|---|---|
| `Bm,G,D,A` | 199 |
| `C,G,Am,F` | 296 |
| `Em,G` | 4 |
| `C,A7,Dm,G7` | 5 |
| `Gm,F` | 7 |
| `C,C7,F,Fm` | 3 |

A comparação é sempre por conjunto, nunca por ordem ou composição de página,
porque a paginação antiga dependia de `PYTHONHASHSEED`. Com `seqs_famosas`
zerado, as 6 continuam retornando o mesmo baseline.

O smoke no Docker também confirmou `Content-Type: text/html` e as mesmas 12
chaves em `/musica/<id>/`.

## Como rodar

No host, com as dependências do `requirements.txt` instaladas (o host usado no
desenvolvimento tem Python 3.14 sem Flask, por isso a suíte foi executada no
Docker):

```
python -m unittest discover -s tests -v
```

No Docker, que é como o app é validado:

```
docker build -t ciframe-tests .
docker run --rm ciframe-tests python -m unittest discover -s tests -v
```

Resultado: `Ran 33 tests in 2.2s` — `OK`.

### Smoke final no Docker

```
docker volume create deciframe-smoke
docker run -d --name ciframe-smoke -p 18086:8080 \
  -v deciframe-smoke:/app/db ciframe-tests
```

- `GET /generos` → 200;
- `GET /sequencias` → 6 sequências semeadas;
- `POST {"acordes":["C","G","Am"]}` → 201, id 7;
- `GET /similares?sequencia=C,G,Am` → 28 resultados na primeira página;
- repetir o `POST` → 200 com `"duplicada": true`;
- as 6 originais → `199/296/4/5/7/3`, conjuntos idênticos ao baseline;
- `docker restart ciframe-smoke` → a sequência nova continua no catálogo.

## O que ficou de fora

- **E2E de browser automatizado no repositório.** O fluxo foi validado
  manualmente no Passo 4, com 33 checagens em Chrome/CDP e capturas em
  `/tmp/opencode/step4-01..08-*.png`, mas esse script não foi versionado porque
  exigiria infraestrutura de browser que o projeto não tem.
- **Teste automatizado do controller AngularJS.** Houve uma verificação ad hoc
  em Node com 102 checagens, também fora do repositório; a suíte oficial cobre
  só o backend.
- **Vídeo/GIF de demonstração.** Fica a cargo do usuário, conforme combinado.
- **Ordem e composição das páginas.** Fora do contrato; a regressão compara
  apenas a união dos IDs.
- **Migração de banco de versões anteriores do schema.** Só existe a versão 1;
  versões desconhecidas falham no startup de propósito.
- **Concorrência de escrita e carga.** O deploy atual usa um worker do
  gunicorn; `busy_timeout` e `UNIQUE(chave)` cobrem o caso de duplicata, mas não
  há teste de estresse.
- **Atualização do fixture após mudança no CSV.** O fixture está atrelado ao
  `sha256` atual; se o dataset mudar de propósito, ele precisa ser recapturado.
