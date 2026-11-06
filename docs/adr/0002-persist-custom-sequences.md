# Persistir o catálogo de sequências de acordes customizadas em SQLite

As seis sequências famosas de acordes estavam hardcoded em `main.py`, e o
conjunto de músicas que casava com cada uma era pré-computado offline na coluna
`SEQ_FAMOSA` de `data/top/dataset_final.csv`. Isso era adequado enquanto o
catálogo era fixo, mas a nova feature permite que qualquer visitante adicione
uma sequência, e o catálogo precisa sobreviver a reinícios e crescer sem um novo
deploy. Por isso introduzimos um banco SQLite pequeno, apenas para o catálogo de
sequências; o catálogo de músicas e gêneros continua no CSV e em memória, como
antes.

Escolhemos SQLite porque faz parte da biblioteca padrão do Python, não exige
dependência nova nem serviço externo, e oferece transações e uma restrição
`UNIQUE` que um arquivo JSON ou o TinyDB não teriam. Ele se encaixa no deploy
single-container e local-only registrado no ADR 0001; PostgreSQL ou MySQL
reintroduziriam um segundo serviço, e DuckDB ou TinyDB adicionariam uma
dependência para um catálogo que deve continuar pequeno. O banco fica em
`db/deciframe.sqlite3` (sobrescrevível por `DECIFRAME_DB`), é criado e semeado
de forma idempotente no startup, e é montado a partir de um volume nomeado
(`deciframe-db` em `/app/db`) para sobreviver a `docker rm` e a rebuilds da
imagem. O processo falha rápido se o banco não puder ser aberto ou inicializado,
em vez de subir com um catálogo silenciosamente vazio. O Dockerfile declara o
volume e o README documenta a flag `-v`; `db/` é ignorado tanto pelo git quanto
pelo Docker, para que o banco local de um desenvolvedor nunca vá para a imagem.

O schema guarda a lista ordenada de acordes de cada sequência como texto JSON,
uma chave canônica em minúsculas para deduplicação e lookup, e um timestamp de
criação. Não há coluna de modo: a regra de matching é única para todo o catálogo.
Ela é a regra histórica — bloco contíguo mais a restrição de que a música não usa
nenhum acorde fora da sequência —, a mesma que gerou as tags de `SEQ_FAMOSA`.
Aplicá-la a todas as sequências preserva exatamente os resultados das 6 e dá uma
definição única e testável para as novas. O custo é intencional: uma sequência
nova só retorna músicas que usam exclusivamente os acordes dela; uma música com
a progressão e uma ponte com outro acorde não aparece. Se o produto quiser um
matching mais permissivo no futuro, isso vira uma decisão explícita, não um
comportamento implícito por linha.

Consequências: a busca por sequência agora é calculada em tempo de requisição e
cacheada em memória, em vez de ler uma tag pré-computada; `SEQ_FAMOSA` e
`Musica.seqs_famosas` permanecem apenas para que `/musica/<id>/` mantenha sua
saída atual e não são mais a fonte dos resultados de sequência. A regra restrita
é aplicada uniformemente, então não há flag por sequência nem dois
comportamentos para explicar e testar. O catálogo é append-only e anônimo, sem
autoria, moderação, remoção ou rate limiting — aceitável para um deploy
local-only, mas uma precondição a revisitar antes de expor o catálogo
publicamente. Mudanças futuras de schema vão precisar de versionamento/migração;
por enquanto, um `CREATE TABLE IF NOT EXISTS` idempotente mais o seed é
suficiente.
