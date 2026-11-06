# coding: utf-8
import json
import os
import unittest

from tests import support
import main


CAMINHO_FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'fixtures', 'baseline_6_sequencias.json')

CHAVES_MUSICA = {
    'id_artista', 'nome_artista', 'id_musica', 'nome_musica', 'genero',
    'popularidade', 'tom', 'cifra', 'acordes', 'seqs_famosas',
    'id_unico_musica', 'url',
}


def carregar_baseline():
    with open(CAMINHO_FIXTURE, encoding='utf-8') as arquivo:
        return json.load(arquivo)['sequencias']


class RegressaoTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.baseline = carregar_baseline()
        cls.client = main.app.test_client()

    def buscar_todas_as_paginas(self, sequencia):
        ids = []
        pagina = 1
        while True:
            resposta = self.client.get('/similares', query_string={
                'sequencia': sequencia,
                'pagina': pagina,
            })
            self.assertEqual(resposta.status_code, 200)
            dados = json.loads(resposta.get_data(as_text=True))
            if not dados:
                break
            ids.extend(musica['id_unico_musica'] for musica in dados)
            pagina += 1
        return ids

    def test_as_seis_sequencias_batem_com_o_baseline(self):
        self.assertEqual(len(self.baseline), 6)

        for sequencia, esperado in self.baseline.items():
            with self.subTest(sequencia=sequencia):
                obtido = self.buscar_todas_as_paginas(sequencia)

                self.assertEqual(len(obtido), len(esperado))
                self.assertEqual(set(obtido), set(esperado))
                self.assertEqual(len(obtido), len(set(obtido)))

    def test_resultado_nao_depende_de_seqs_famosas(self):
        estado = [(musica, musica.seqs_famosas)
                  for musica in main.musicas.values()]
        try:
            for musica, _ in estado:
                musica.seqs_famosas = []
            support.limpar_cache()

            for sequencia, esperado in self.baseline.items():
                with self.subTest(sequencia=sequencia):
                    obtido = self.buscar_todas_as_paginas(sequencia)
                    self.assertEqual(set(obtido), set(esperado))
        finally:
            for musica, seqs_famosas in estado:
                musica.seqs_famosas = seqs_famosas
            support.limpar_cache()

    def test_musica_mantem_as_mesmas_chaves(self):
        self.assertGreater(len(main.musicas), 0)
        id_unico = next(iter(main.musicas))

        resposta = self.client.get('/musica/%s/' % id_unico)
        dados = json.loads(resposta.get_data(as_text=True))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.mimetype, 'text/html')
        self.assertEqual(set(dados), CHAVES_MUSICA)
        self.assertEqual(set(main.musicas[id_unico].__dict__), CHAVES_MUSICA)


if __name__ == '__main__':
    unittest.main()
