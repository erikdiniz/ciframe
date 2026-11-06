# coding: utf-8
import unittest

from tests import support  # noqa: F401  (ajusta o ambiente antes de main)
from main import casa_sequencia


class CasaSequenciaTest(unittest.TestCase):
    """Regra unica: bloco contiguo e nenhum acorde fora da sequencia."""

    def test_bloco_contiguo(self):
        cifra = ('c', 'g', 'am')
        self.assertTrue(casa_sequencia(cifra, set(cifra), ('c', 'g', 'am')))

    def test_bloco_contiguo_no_meio_da_cifra(self):
        cifra = ('g', 'am', 'c', 'g', 'am')
        self.assertTrue(casa_sequencia(cifra, set(cifra), ('c', 'g', 'am')))

    def test_ordem_diferente_nao_casa(self):
        cifra = ('c', 'g', 'am')
        self.assertFalse(casa_sequencia(cifra, set(cifra), ('g', 'c', 'am')))

    def test_acorde_da_cifra_fora_da_sequencia_nao_casa(self):
        cifra = ('c', 'g', 'am')
        self.assertFalse(casa_sequencia(cifra, set(cifra), ('c', 'g')))

    def test_ausencia_de_bloco_nao_casa(self):
        cifra = ('c', 'g', 'am', 'f')
        self.assertFalse(casa_sequencia(cifra, set(cifra), ('c', 'g', 'f')))

    def test_caixa_diferente_e_equivalente(self):
        cifra = ('c', 'g', 'am')
        self.assertTrue(casa_sequencia(cifra, set(cifra), ('C'.lower(),
                                                           'G'.lower(),
                                                           'Am'.lower())))

    def test_repeticao_de_acorde(self):
        cifra = ('c', 'g', 'c', 'g')
        self.assertTrue(casa_sequencia(cifra, set(cifra), ('g', 'c')))
        self.assertFalse(casa_sequencia(cifra, set(cifra), ('c', 'c')))

    def test_cifra_vazia_nao_casa(self):
        self.assertFalse(casa_sequencia((), set(), ('c', 'g')))

    def test_sequencia_vazia_nao_casa(self):
        cifra = ('c', 'g')
        self.assertFalse(casa_sequencia(cifra, set(cifra), ()))

    def test_baixo_slash_nao_e_normalizado(self):
        cifra = ('e/b', 'f#')
        self.assertTrue(casa_sequencia(cifra, set(cifra), ('e/b', 'f#')))
        self.assertFalse(casa_sequencia(cifra, set(cifra), ('e', 'f#')))


if __name__ == '__main__':
    unittest.main()
