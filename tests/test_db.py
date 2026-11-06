# coding: utf-8
import json
import os
import sqlite3
import unittest

from tests import support
from main import (
    CAMINHO_DB,
    SEQUENCIAS_ORIGINAIS,
    VERSAO_SCHEMA,
    buscar_sequencia_por_chave,
    chave_sequencia,
    conectar_db,
    inicializar_db,
    inserir_sequencia,
    listar_sequencias,
)


class BancoTest(unittest.TestCase):

    def test_schema_e_seed_idempotentes(self):
        with support.banco_isolado() as caminho:
            inicializar_db(caminho)
            inicializar_db(caminho)

            with conectar_db(caminho) as conexao:
                versao = conexao.execute('PRAGMA user_version').fetchone()[0]
                total = conexao.execute(
                    'SELECT COUNT(*) FROM sequencias').fetchone()[0]

            self.assertEqual(versao, VERSAO_SCHEMA)
            self.assertEqual(total, len(SEQUENCIAS_ORIGINAIS))

    def test_seed_cria_as_seis_sequencias_na_ordem(self):
        with support.banco_isolado() as caminho:
            inicializar_db(caminho)
            sequencias = listar_sequencias(caminho)

            self.assertEqual(
                [tuple(s['acordes']) for s in sequencias],
                list(SEQUENCIAS_ORIGINAIS))
            self.assertEqual([s['id'] for s in sequencias], [1, 2, 3, 4, 5, 6])

    def test_seed_nao_duplica_ao_rodar_de_novo(self):
        with support.banco_isolado() as caminho:
            inicializar_db(caminho)
            inserir_sequencia(['C', 'G', 'Am'], chave_sequencia(['C', 'G', 'Am']),
                              caminho)
            inicializar_db(caminho)

            self.assertEqual(len(listar_sequencias(caminho)), 7)

    def test_seed_nao_sobrescreve_linha_existente(self):
        with support.banco_isolado() as caminho:
            inicializar_db(caminho)

            # mesma chave da primeira sequencia, exibicao diferente
            original = SEQUENCIAS_ORIGINAIS[0]
            chave = chave_sequencia(original)
            with conectar_db(caminho) as conexao:
                with conexao:
                    conexao.execute(
                        'UPDATE sequencias SET acordes = ? WHERE chave = ?',
                        (json.dumps(['BM', 'G', 'D', 'A']), chave))

            inicializar_db(caminho)
            sequencia = buscar_sequencia_por_chave(chave, caminho)

            self.assertEqual(sequencia['acordes'], ['BM', 'G', 'D', 'A'])

    def test_persiste_ao_fechar_e_reabrir(self):
        with support.banco_isolado() as caminho:
            inicializar_db(caminho)
            inserir_sequencia(['Dm', 'G', 'C'],
                              chave_sequencia(['Dm', 'G', 'C']), caminho)

            # listar_sequencias abre e fecha uma conexao nova
            sequencias = listar_sequencias(caminho)

            self.assertEqual(len(sequencias), 7)
            self.assertEqual(sequencias[-1]['acordes'], ['Dm', 'G', 'C'])

    def test_insercao_duplicada_devolve_a_original(self):
        with support.banco_isolado() as caminho:
            inicializar_db(caminho)
            chave = chave_sequencia(['C', 'G', 'Am'])

            primeira, duplicada1 = inserir_sequencia(
                ['C', 'G', 'Am'], chave, caminho)
            segunda, duplicada2 = inserir_sequencia(
                ['C', 'G', 'Am'], chave, caminho)

            self.assertFalse(duplicada1)
            self.assertTrue(duplicada2)
            self.assertEqual(primeira['id'], segunda['id'])
            self.assertEqual(len(listar_sequencias(caminho)), 7)

    def test_banco_novo_e_criado_com_diretorio(self):
        with support.banco_isolado() as caminho:
            subdiretorio = os.path.join(os.path.dirname(caminho), 'a', 'b')
            alvo = os.path.join(subdiretorio, 'x.sqlite3')

            inicializar_db(alvo)

            self.assertTrue(os.path.exists(alvo))

    def test_deciframe_db_respeitado(self):
        support.limpar_catalogo()

        self.assertEqual(os.environ['DECIFRAME_DB'], support.CAMINHO_DB_TESTE)
        self.assertEqual(CAMINHO_DB, support.CAMINHO_DB_TESTE)
        self.assertNotEqual(
            os.path.abspath(CAMINHO_DB),
            os.path.abspath('db/deciframe.sqlite3'))

        # o banco da suite foi criado no caminho do ambiente
        self.assertTrue(os.path.exists(support.CAMINHO_DB_TESTE))
        with sqlite3.connect(support.CAMINHO_DB_TESTE) as conexao:
            total = conexao.execute(
                'SELECT COUNT(*) FROM sequencias').fetchone()[0]
        self.assertEqual(total, len(SEQUENCIAS_ORIGINAIS))


if __name__ == '__main__':
    unittest.main()
