# deciframe

Descubra as músicas que você já sabe tocar (e ainda não faz ideia). Busque por
título/artista, gênero, pelos acordes que você já manja, ou por sequências de
acordes famosas — o deciframe cruza isso com uma base de cifras e sugere
músicas parecidas.

Stack: backend Flask (Python) servindo uma API JSON + um frontend AngularJS
estático. Músicas e gêneros vêm de um CSV carregado em memória; o catálogo de
sequências de acordes customizadas fica em SQLite.

## Rodando localmente

### Com Docker

```
docker build -t ciframe .
docker run -p 8080:8080 -v deciframe-db:/app/db ciframe
```

Acesse [http://localhost:8080](http://localhost:8080).

O banco `db/deciframe.sqlite3` é criado automaticamente no primeiro start, já
com as 6 sequências originais. O volume nomeado `deciframe-db` mantém as
sequências cadastradas quando o container é recriado; sem o `-v`, o banco fica
em um volume anônimo que não é reaproveitado por um novo container.

Para usar outro caminho de banco, defina `DECIFRAME_DB`:

```
docker run -p 8080:8080 \
  -e DECIFRAME_DB=/app/db/meu.sqlite3 \
  -v deciframe-db:/app/db \
  ciframe
```

Apagar o arquivo do banco recria as 6 sequências semeadas no próximo start, mas
perde as sequências customizadas.

### Com virtualenv

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Acesse [http://localhost:5000](http://localhost:5000).

O banco local é criado automaticamente em `db/deciframe.sqlite3`, relativo ao
diretório onde o comando é executado.

---

Para convenções de contribuição, veja [CONTRIB.md](CONTRIB.md). Licença: [LICENSE](LICENSE).
