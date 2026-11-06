# coding: utf-8
import json
import functools
import os
import sqlite3
from contextlib import closing
from flask import Flask, request
import sys
from musica import *
from collections import OrderedDict
import unicodedata

app = Flask(__name__)

def limpa_cifra(raw_cifra):
    cifra = []
    for m in raw_cifra:
        if m.strip() != '':
            # filtra tablaturas
            if '|' in m:
                acorde = m.split('|')[0].split()[0]
                cifra.append(acorde)
            # lida com acordes separados por espaço
            else:
                tokens = [token for token in m.split()]
                cifra += tokens
    return cifra

# colunas do csv
ARTISTA_ID = 0
MUSICA_ID = 1
ARTISTA = 2
MUSICA = 3
GENERO = 4
POPULARIDADE = 5
TOM = 6
SEQ_FAMOSA = 7
CIFRA = 8
TAM_PAGINA = 100

# banco de dados: apenas o catalogo de sequencias customizadas
CAMINHO_DB = os.environ.get('DECIFRAME_DB', 'db/deciframe.sqlite3')
VERSAO_SCHEMA = 1
SEQUENCIAS_ORIGINAIS = (
    ('Bm', 'G', 'D', 'A'),
    ('C', 'G', 'Am', 'F'),
    ('Em', 'G'),
    ('C', 'A7', 'Dm', 'G7'),
    ('Gm', 'F'),
    ('C', 'C7', 'F', 'Fm'),
)


def chave_sequencia(acordes):
    """Chave canonica: lista em minusculas em JSON compacto e estavel."""
    return json.dumps([acorde.lower() for acorde in acordes],
            ensure_ascii=False, separators=(',', ':'))


def conectar_db(caminho=None):
    caminho = caminho or CAMINHO_DB
    diretorio = os.path.dirname(os.path.abspath(caminho))
    os.makedirs(diretorio, exist_ok=True)

    conexao = sqlite3.connect(caminho)
    conexao.row_factory = sqlite3.Row
    conexao.execute('PRAGMA busy_timeout = 5000')
    return conexao


def _linha_para_sequencia(linha):
    return {
        'id': linha['id'],
        'acordes': json.loads(linha['acordes']),
    }


def listar_sequencias(caminho=None):
    with closing(conectar_db(caminho)) as conexao:
        linhas = conexao.execute(
            'SELECT id, acordes FROM sequencias ORDER BY id').fetchall()
    return [_linha_para_sequencia(linha) for linha in linhas]


def buscar_sequencia_por_chave(chave, caminho=None):
    with closing(conectar_db(caminho)) as conexao:
        linha = conexao.execute(
            'SELECT id, acordes FROM sequencias WHERE chave = ?',
            (chave,)).fetchone()
    if linha is None:
        return None
    return _linha_para_sequencia(linha)


def inserir_sequencia(acordes, chave, caminho=None):
    """Insere se a chave nao existir e devolve (sequencia, duplicada)."""
    acordes_json = json.dumps(list(acordes), ensure_ascii=False,
            separators=(',', ':'))

    with closing(conectar_db(caminho)) as conexao:
        with conexao:
            cursor = conexao.execute(
                'INSERT OR IGNORE INTO sequencias (acordes, chave) VALUES (?, ?)',
                (acordes_json, chave))
            duplicada = cursor.rowcount == 0

        linha = conexao.execute(
            'SELECT id, acordes FROM sequencias WHERE chave = ?',
            (chave,)).fetchone()

    if linha is None:
        raise RuntimeError('sequencia nao encontrada apos insercao: %s' % chave)
    return _linha_para_sequencia(linha), duplicada


def inicializar_db(caminho=None):
    with closing(conectar_db(caminho)) as conexao:
        with conexao:
            versao = conexao.execute('PRAGMA user_version').fetchone()[0]

            if versao == 0:
                conexao.execute('''
                    CREATE TABLE IF NOT EXISTS sequencias (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        acordes TEXT NOT NULL,
                        chave TEXT NOT NULL UNIQUE,
                        criada_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )''')
                conexao.execute('PRAGMA user_version = %d' % VERSAO_SCHEMA)
            elif versao != VERSAO_SCHEMA:
                raise RuntimeError(
                    'versao de schema nao suportada: %d (esperado %d)'
                    % (versao, VERSAO_SCHEMA))

            for acordes in SEQUENCIAS_ORIGINAIS:
                conexao.execute(
                    'INSERT OR IGNORE INTO sequencias (acordes, chave) VALUES (?, ?)',
                    (json.dumps(list(acordes), ensure_ascii=False,
                        separators=(',', ':')),
                     chave_sequencia(acordes)))


genero_musicas = {}
generos = set()
acordes = set()
sequencias = {'BmGDA' : 0,
        'CGAmF' : 1,
        'EmG' : 2,
        'CA7DmG7' : 3,
        'GmF' : 4,
        'CC7FFm' : 5}

musicas_dict = {}

# auxiliares do matching: cifra ordenada em minusculas e vocabulario fechado
cifras_lower = {}
vocabularios = {}

f = open('data/top/dataset_final.csv')
f.readline()

for line in f:
    line = line.replace('"', '').replace('NA', '')[:-1]

    musica = line.split(',')
    musica[POPULARIDADE] = int(musica[POPULARIDADE].replace('.', ''))

    if musica[CIFRA] != '':
        musica[CIFRA] = limpa_cifra(musica[CIFRA].split(';'))
    else:
        musica[CIFRA] = []

    musica[SEQ_FAMOSA] = musica[SEQ_FAMOSA].split(";")

    # conjunto único de gêneros
    generos.add(musica[GENERO])

    # inclui música no dict de músicas
    musica_obj = Musica(musica[ARTISTA_ID], musica[ARTISTA],
            musica[MUSICA_ID], musica[MUSICA], musica[GENERO],
            int(musica[POPULARIDADE]), musica[SEQ_FAMOSA],
            musica[TOM], musica[CIFRA])

    musicas_dict[musica_obj.id_unico_musica] = musica_obj

    # auxiliares do matching, sem tocar nos atributos de Musica
    cifra_lower = tuple(acorde.lower() for acorde in musica_obj.cifra)
    cifras_lower[musica_obj.id_unico_musica] = cifra_lower
    vocabularios[musica_obj.id_unico_musica] = set(cifra_lower)

    # conjunto único de acordes
    for acorde in musica_obj.acordes:
        acordes.add(acorde)

    # constrói dict mapeando gênero para músicas
    # deve ser usado para melhorar o desempenho das buscas
    if musica_obj.genero in genero_musicas:
        genero_musicas[musica_obj.genero].append(musica_obj)
    else:
        genero_musicas[musica_obj.genero] = [musica_obj]

# dicionário de músicas cujos valores são ordenados por popularidade
musicas = OrderedDict(sorted(musicas_dict.items(),
    key=lambda x: x[1].popularidade, reverse = True))

# para trabalhar melhor com json
generos = list(generos)

# ordena genero_musicas por popularidade
for k,v in genero_musicas.items():
    genero_musicas[k].sort(key = lambda x : x.popularidade, reverse = True)

f.close()

# cria/abre o catalogo de sequencias; se falhar, o processo nao sobe
inicializar_db()


def casa_sequencia(cifra_lower, vocabulario, seq):
    """Regra unica: bloco contiguo e nenhum acorde fora da sequencia."""
    if not seq:
        return False
    if not vocabulario <= set(seq):
        return False

    tamanho = len(seq)
    for i in range(len(cifra_lower) - tamanho + 1):
        if cifra_lower[i:i + tamanho] == seq:
            return True
    return False


@functools.lru_cache(maxsize=64)
def _matches_para_chave(chave):
    """Musicas que casam com a chave canonica, ordenadas por popularidade."""
    seq = tuple(json.loads(chave))

    matches = []
    for musica in musicas.values():
        id_unico = musica.id_unico_musica
        if casa_sequencia(cifras_lower[id_unico], vocabularios[id_unico], seq):
            matches.append(musica)

    matches.sort(key=lambda m: (-m.popularidade, m.id_unico_musica))
    return tuple(matches)


def get_similares_por_chave(chave, generos_key, pagina_tag):
    """Filtra por genero, pagina e so entao monta os dicionarios da pagina."""
    # apply_filtro reconstroi a colecao a partir dos buckets de genero, entao
    # aqui filtramos o subconjunto do cache com a mesma semantica.
    generos_validos = set(g for g in generos_key if g in generos)
    collection = [musica for musica in _matches_para_chave(chave)
                  if musica.genero in generos_validos]

    similares = []
    for musica in get_pagina(collection, pagina_tag):
        similares.append({
            'id_unico_musica' : musica.id_unico_musica,
            'id_artista' : musica.id_artista,
            'id_musica' : musica.id_musica,
            'nome_artista' : musica.nome_artista,
            'nome_musica' : musica.nome_musica,
            'popularidade' : musica.popularidade,
            'acordes' : musica.acordes,
            'genero' : musica.genero,
            'url' : musica.url,
        })

    return similares


@app.route('/')
def index():
    return app.send_static_file('index.html')
''' Busca por músicas que possuem no título ou no nome do artista o argumento passado por key.
params: key e generos (opcional). Caso generos não sejam definidos, a busca não irá filtrar por gênero.
exemplo 1: /search?key=no dia em que eu saí de casa
exemplo 2: /search?key=no dia em que eu saí de casa&generos=Rock,Samba '''

@app.route('/<path:path>')
def static_proxy(path):
  # send_static_file will guess the correct MIME type
  return app.send_static_file(path)

@app.route('/search')
def busca():
    generos_tag = request.args.get('generos', [])
    pagina_tag = request.args.get('pagina','1')
    keys = request.args.get('key').lower()
    keys = remover_combinantes(keys).split(' ')

    generos_key = generos
    if generos_tag:
        generos_key = generos_tag.split(',')

    collection = apply_filtro(musicas.values(), generos_key)
    out = []

    for musica in collection:
        text = '%s %s' % (musica.nome_artista.lower(), musica.nome_musica.lower())
        text_list = remover_combinantes(text).split(' ')
        if all(key in text_list for key in keys):
            matches = {
                'id_unico_musica' : musica.id_unico_musica,
                'id_artista' : musica.id_artista,
                'id_musica' : musica.id_musica,
                'nome_artista' : musica.nome_artista,
                'nome_musica' : musica.nome_musica,
                'genero' : musica.genero,
                'url' : musica.url,
            }
            out.append(matches)
    return json.dumps(get_pagina(out, pagina_tag))

# cópia
def remover_combinantes(string):
    string = unicodedata.normalize('NFD', string)
    return u''.join(ch for ch in string if unicodedata.category(ch) != 'Mn')

''' Retorna as músicas armazenadas no sistema (ordenados por popularidade).
    O serviço é paginado. Cada página tem tamanho 100, por default.
    params: pagina. Caso não seja definida a página, o valor default é 1.
    exemplo 1: /musica?pagina=2
    exemplo 2: /musica'''
@app.route('/musicas')
def get_musicas():
    return json.dumps([v.__dict__ for v in musicas.values()])

@app.route('/generos')
def get_generos():
    return json.dumps(generos)

@app.route('/acordes')
def get_acordes():
    return json.dumps(list(acordes))

@app.route('/musica/<m_id>/')
def get_musica(m_id):
    return json.dumps(musicas[m_id].__dict__)

@app.route('/similares')
def get_similares():
    # tratando request
    acordes_tag = request.args.get('acordes')
    id_musica_tag = request.args.get('id_unico_musica')
    sequencia_tag = request.args.get('sequencia')
    pagina_tag = request.args.get('pagina','1')

    # se não existir, filtra por todos.
    generos_tag = request.args.get('generos')
    generos_key = generos
    if generos_tag:
        generos_key = generos_tag.split(',')

    acordes = []
    if acordes_tag:
        acordes = acordes_tag.split(',')
    elif id_musica_tag:
        musica = musicas[id_musica_tag]
        acordes = musica.acordes
    elif sequencia_tag:
        acordes = sequencia_tag.replace(',','')
        similares = []

        if acordes in sequencias:
            id_seq = sequencias[acordes]
            similares = get_pagina(get_similares_por_sequencia(id_seq, generos_key), pagina_tag)
        return json.dumps(similares)

    similares = get_similares(acordes, generos_key, id_musica_tag)

    return json.dumps(get_pagina(similares, pagina_tag))

def get_similares_por_sequencia(id_seq, generos_key):
    # filtra para melhor desempenho
    collection = apply_filtro(musicas.values(), generos_key)

    similares = []
    for musica in collection:
        if str(id_seq) in musica.seqs_famosas:
            similar = {
                'id_unico_musica' : musica.id_unico_musica,
                'id_artista' : musica.id_artista,
                'id_musica' : musica.id_musica,
                'nome_artista' : musica.nome_artista,
                'nome_musica' : musica.nome_musica,
                'popularidade' : musica.popularidade,
                'acordes' : musica.acordes,
                'genero' : musica.genero,
                'url' : musica.url,
            }
            similares.append(similar)

    return similares


def get_pagina(colecao, pagina_tag):
    sl = (int(pagina_tag) - 1)*TAM_PAGINA
    return colecao[sl:sl+TAM_PAGINA]

def get_similares(acordes, generos_key, id_musica = None):

    # filtra para melhor desempenho
    collection = apply_filtro(musicas.values(), generos_key)

    similares = []
    for musica in collection:

        if musica.id_unico_musica != id_musica:

            inter = set(acordes).intersection(set(musica.acordes))
            diff = set(musica.acordes) - set(acordes)

            # somente as que tiverem interseção e as que forem
            # dos generos solicitados.
            if len(inter) > 0:
                similar = {
                        'id_unico_musica' : musica.id_unico_musica,
                        'id_artista' : musica.id_artista,
                        'id_musica' : musica.id_musica,
                        'nome_artista' : musica.nome_artista,
                        'nome_musica' : musica.nome_musica,
                        'popularidade' : musica.popularidade,
                        'acordes' : musica.acordes,
                        'genero' : musica.genero,
                        'url' : musica.url,
                        'diferenca' : list(diff),
                        'intersecao' : list(inter)
                }

                similares.append(similar)

    # ordenados por menor diferença, maior interseção e maior popularidade.
    return sorted(similares, key=lambda x: (len(x['diferenca']), -len(x['intersecao'])))

## Filtra a coleção de músicas por gênero.
def apply_filtro(musicas, generos_key):
    # filtra para melhor desempenho
    collection = []
    for genero in generos_key:
        if genero in generos:
            collection += genero_musicas[genero]
    return collection

@app.after_request
def add_header(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

if __name__ == '__main__':
    app.run(debug=True)
