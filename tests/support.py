"""Apoio comum dos testes.

Aponta ``DECIFRAME_DB`` para um arquivo temporario *antes* de importar
``main``, para que a suite nunca escreva no ``db/`` do repositorio.
"""
import atexit
import contextlib
import os
import shutil
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

_TEMPDIR = tempfile.mkdtemp(prefix='deciframe-tests-')
CAMINHO_DB_TESTE = os.path.join(_TEMPDIR, 'deciframe.sqlite3')
os.environ['DECIFRAME_DB'] = CAMINHO_DB_TESTE

atexit.register(lambda: shutil.rmtree(_TEMPDIR, ignore_errors=True))

# so pode ser importado depois de ajustar o ambiente
import main  # noqa: E402


def limpar_catalogo():
    """Volta o banco da suite ao estado recem-semeado (6 sequencias)."""
    with contextlib.closing(main.conectar_db()) as conexao:
        with conexao:
            conexao.execute('DELETE FROM sequencias')
            conexao.execute(
                "DELETE FROM sqlite_sequence WHERE name = 'sequencias'")
    main.inicializar_db()


@contextlib.contextmanager
def banco_isolado():
    """Entrega um caminho de banco novo, apagado ao fim do bloco."""
    diretorio = tempfile.mkdtemp(prefix='deciframe-db-', dir=_TEMPDIR)
    try:
        yield os.path.join(diretorio, 'deciframe.sqlite3')
    finally:
        shutil.rmtree(diretorio, ignore_errors=True)


def limpar_cache():
    main._matches_para_chave.cache_clear()
