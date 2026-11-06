# coding: utf-8
import json
import unittest

from tests import support
from main import SEQUENCIAS_ORIGINAIS, app


class ApiTest(unittest.TestCase):

    def setUp(self):
        support.limpar_catalogo()
        support.limpar_cache()
        self.client = app.test_client()

    def get_json(self, caminho, **kwargs):
        resposta = self.client.get(caminho, **kwargs)
        self.assertEqual(resposta.status_code, 200)
        return json.loads(resposta.get_data(as_text=True))

    def buscar_todas_as_paginas(self, sequencia):
        ids = []
        pagina = 1
        while True:
            dados = self.get_json('/similares', query_string={
                'sequencia': sequencia,
                'pagina': pagina,
            })
            if not dados:
                break
            ids.extend(musica['id_unico_musica'] for musica in dados)
            pagina += 1
        return ids

    # --- catalogo ---

    def test_get_sequencias_devolve_as_seis(self):
        resposta = self.client.get('/sequencias')
        sequencias = json.loads(resposta.get_data(as_text=True))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            [(s['id'], tuple(s['acordes'])) for s in sequencias],
            [(i + 1, tuple(a)) for i, a in enumerate(SEQUENCIAS_ORIGINAIS)])

    def test_respostas_sao_json_em_string_com_content_type_html(self):
        for caminho in ('/sequencias', '/similares?sequencia=Gm,F', '/generos'):
            resposta = self.client.get(caminho)
            self.assertEqual(resposta.status_code, 200)
            self.assertEqual(resposta.mimetype, 'text/html')
            self.assertIsInstance(
                json.loads(resposta.get_data(as_text=True)),
                (list, dict))

    def test_post_cria_sequencia_nova(self):
        resposta = self.client.post('/sequencias', json={
            'acordes': ['c', 'g', 'am'],
        })
        dados = json.loads(resposta.get_data(as_text=True))

        self.assertEqual(resposta.status_code, 201)
        self.assertFalse(dados['duplicada'])
        self.assertEqual(dados['acordes'], ['C', 'G', 'Am'])
        self.assertEqual(dados['id'], 7)
        self.assertEqual(len(self.get_json('/sequencias')), 7)

    def test_post_duplicado_devolve_existente(self):
        primeira = self.client.post('/sequencias', json={
            'acordes': ['C', 'G', 'Am']})
        resposta = self.client.post('/sequencias', json={
            'acordes': ['C', 'G', 'Am']})
        dados = json.loads(resposta.get_data(as_text=True))

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(dados['duplicada'])
        self.assertEqual(
            dados['id'],
            json.loads(primeira.get_data(as_text=True))['id'])
        self.assertEqual(len(self.get_json('/sequencias')), 7)

    def test_post_duplicado_ignora_caixa_e_espaco(self):
        self.client.post('/sequencias', json={'acordes': ['C', 'G', 'Am']})
        resposta = self.client.post('/sequencias', json={
            'acordes': [' c ', 'g', 'AM']})
        dados = json.loads(resposta.get_data(as_text=True))

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(dados['duplicada'])
        self.assertEqual(len(self.get_json('/sequencias')), 7)

    def test_post_duplicado_das_seis_originais_devolve_a_original(self):
        resposta = self.client.post('/sequencias', json={
            'acordes': ['bm', 'g', 'd', 'a']})
        dados = json.loads(resposta.get_data(as_text=True))

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(dados['duplicada'])
        self.assertEqual(dados['id'], 1)
        self.assertEqual(dados['acordes'], ['Bm', 'G', 'D', 'A'])

    def test_post_invalido_devolve_400_com_erro(self):
        casos = [
            {},
            {'acordes': 'C,G'},
            {'acordes': ['C']},
            {'acordes': ['C'] * 13},
            {'acordes': ['C', 'X']},
            {'acordes': ['C', '']},
            {'acordes': ['C', 'G m']},
            {'acordes': ['C', 'G,Am']},
            {'acordes': ['C', 'A' * 21]},
            {'acordes': ['H', 'C']},
            {'acordes': ['C', 1]},
        ]

        for corpo in casos:
            resposta = self.client.post('/sequencias', json=corpo)
            dados = json.loads(resposta.get_data(as_text=True))
            self.assertEqual(resposta.status_code, 400, corpo)
            self.assertEqual(resposta.mimetype, 'text/html')
            self.assertIn('erro', dados)

        resposta = self.client.post('/sequencias', data='nao e json',
                                    content_type='application/json')
        self.assertEqual(resposta.status_code, 400)
        self.assertIn('erro', json.loads(resposta.get_data(as_text=True)))

    # --- busca por sequencia ---

    def test_busca_por_sequencia_existente(self):
        dados = self.get_json('/similares', query_string={
            'sequencia': 'Bm,G,D,A'})

        self.assertEqual(len(dados), 100)  # primeira pagina

    def test_busca_por_sequencia_inexistente_devolve_lista_vazia(self):
        resposta = self.client.get('/similares', query_string={
            'sequencia': 'C,G,Am,F,Em,Dm'})
        dados = json.loads(resposta.get_data(as_text=True))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.mimetype, 'text/html')
        self.assertEqual(dados, [])

    def test_busca_aceita_variacao_de_caixa_e_espaco(self):
        normal = self.buscar_todas_as_paginas('Bm,G,D,A')
        variacao = self.buscar_todas_as_paginas(' bm , g , d , a ')

        self.assertEqual(len(normal), 199)
        self.assertEqual(set(variacao), set(normal))

    def test_busca_com_sustenido_codificado(self):
        acordes = ['E', 'D7', 'A7', 'D7', 'C#m', 'D7', 'A7', 'D7']
        cadastro = self.client.post('/sequencias', json={'acordes': acordes})
        self.assertEqual(cadastro.status_code, 201)

        dados = self.get_json('/similares', query_string={
            'sequencia': ','.join(acordes)})

        self.assertGreaterEqual(len(dados), 1)
        self.assertIn('C#m', dados[0]['acordes'])

    def test_busca_customizada_funciona_apos_cadastro(self):
        self.client.post('/sequencias', json={'acordes': ['C', 'G', 'Am']})

        dados = self.get_json('/similares', query_string={
            'sequencia': 'C,G,Am'})

        self.assertGreater(len(dados), 0)
        # a mesma sequencia tambem responde com caixa diferente
        variacao = self.get_json('/similares', query_string={
            'sequencia': 'c,g,am'})
        self.assertEqual(
            [m['id_unico_musica'] for m in variacao],
            [m['id_unico_musica'] for m in dados])


if __name__ == '__main__':
    unittest.main()
