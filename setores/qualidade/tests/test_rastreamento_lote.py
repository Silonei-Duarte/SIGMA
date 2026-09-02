"""Testes de setores/qualidade/utils/rastreamento_lote.py — throttle por IP.

Achado crítico da auditoria do app `qualidade`: `rastreamento_lote` é público
por decisão de negócio (QR da etiqueta física é bipado sem login) e dispara
consultas Oracle pesadas do ERP e do Alchemy a cada request. Decisão do
sênior: manter público, com proteção contra abuso por limitação de
requisições por IP (cache padrão do Django).
"""

from django.test import SimpleTestCase, override_settings

from setores.qualidade.utils import rastreamento_lote as views


class _FakeRequest:
    def __init__(self, ip, forwarded=None):
        self.META = {"REMOTE_ADDR": ip}
        if forwarded:
            self.META["HTTP_X_FORWARDED_FOR"] = forwarded


class ThrottleRastreioTests(SimpleTestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    @override_settings(
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    )
    def test_primeiras_requisicoes_nao_passam_do_limite(self):
        requisicao = _FakeRequest("10.0.0.1")

        for _ in range(views.RASTREIO_LIMITE_JANELA):
            self.assertFalse(views._esta_acima_do_limite_rastreio(requisicao))

    @override_settings(
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    )
    def test_passou_do_limite_na_mesma_janela_e_bloqueado(self):
        requisicao = _FakeRequest("10.0.0.1")

        for _ in range(views.RASTREIO_LIMITE_JANELA):
            views._esta_acima_do_limite_rastreio(requisicao)

        self.assertTrue(views._esta_acima_do_limite_rastreio(requisicao))

    @override_settings(
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    )
    def test_limite_por_ip_nao_afeta_outro_ip(self):
        requisicao_a = _FakeRequest("10.0.0.1")
        requisicao_b = _FakeRequest("10.0.0.2")

        for _ in range(views.RASTREIO_LIMITE_JANELA):
            views._esta_acima_do_limite_rastreio(requisicao_a)

        self.assertTrue(views._esta_acima_do_limite_rastreio(requisicao_a))
        self.assertFalse(views._esta_acima_do_limite_rastreio(requisicao_b))

    def test_ip_vem_do_forwarded_for_quando_presente(self):
        requisicao = _FakeRequest("10.0.0.1", forwarded="192.168.1.50, 10.0.0.1")

        self.assertEqual(views._ip_do_cliente(requisicao), "192.168.1.50")
