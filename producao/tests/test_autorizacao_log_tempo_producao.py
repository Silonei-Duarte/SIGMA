from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CentroRecurso, Departamento, Empresa, Filial, Recurso, Setor
from producao.models import LogTrocaOPAtiva, ParadaMaquina

User = get_user_model()

EXCLUIR = "pode_excluir_pendencias_integracao"
ALTERAR = "pode_alterar_paradas"


class AutorizacaoLogTempoProducaoTests(TestCase):
    """Autorização das rotas do log de tempo produção.

    A tela fica livre a autenticados (mesma decisão das outras telas de
    produção). Exclusões exigem `pode_excluir_pendencias_integracao`;
    alteração de horário e abertura manual pelo log exigem
    `pode_alterar_paradas` — staff passa pelo bypass em ambas. Salvar
    justificativas permanece no corpo (regra depende do recurso alt_just).
    """

    def setUp(self):
        self.recurso_a = self._criar_recurso(1, "A")
        self.recurso_b = self._criar_recurso(2, "B")
        self.usuario = User.objects.create_user(
            username="tempo_a",
            password="senha",
            filial=self.recurso_a.centro_recurso.setor.departamento.filial,
        )
        self.client.force_login(self.usuario)

    @staticmethod
    def _criar_recurso(codemp, sufixo):
        empresa = Empresa.objects.create(
            codemp=codemp, nome=f"Empresa {sufixo}", fantasia=f"E{sufixo}"
        )
        filial = Filial.objects.create(
            empresa=empresa,
            codfil=1,
            nome=f"Filial {sufixo}",
            fantasia=f"F{sufixo}",
            cnpj=f"{codemp:04d}0000000001",
        )
        departamento = Departamento.objects.create(filial=filial, descricao=f"Depto {sufixo}")
        setor = Setor.objects.create(departamento=departamento, descricao=f"Setor {sufixo}")
        centro = CentroRecurso.objects.create(
            setor=setor, codigo=f"CR{sufixo}", descricao=f"Centro {sufixo}"
        )
        return Recurso.objects.create(
            centro_recurso=centro, codigo=f"R{sufixo}", descricao=f"Recurso {sufixo}"
        )

    def _conceder(self, codename):
        self.usuario.user_permissions.add(
            Permission.objects.get(content_type__app_label="producao", codename=codename)
        )

    def _criar_periodo_com_parada(self):
        agora = timezone.now().replace(microsecond=0)
        periodo = LogTrocaOPAtiva.objects.create(
            recurso=self.recurso_a,
            origem="1",
            op=100,
            estagio=1,
            seqrot=1,
            horario_troca=agora - timedelta(hours=2),
            horario_saida=agora - timedelta(hours=1),
        )
        parada = ParadaMaquina.objects.create(
            recurso=self.recurso_a,
            inicio=agora - timedelta(minutes=90),
            fim=agora - timedelta(minutes=75),
            tipo=ParadaMaquina.Tipo.MANUAL,
            usuario=self.usuario,
        )
        parada.periodos_produtivos.add(periodo)
        return periodo, parada

    # --- tela livre ---

    def test_anonimo_e_redirecionado_para_o_login(self):
        self.client.logout()

        resposta = self.client.get(reverse("log_tempo_producao"))

        self.assertEqual(resposta.status_code, 302)

    def test_tela_logada_sem_permissao_renderiza_vazia(self):
        resposta = self.client.get(reverse("log_tempo_producao"))

        self.assertEqual(resposta.status_code, 200)

    # --- exclusões de período e parada ---

    def test_excluir_periodo_sem_permissao_recebe_403(self):
        periodo, _ = self._criar_periodo_com_parada()

        resposta = self.client.post(reverse("excluir_periodo_tempo_producao", args=[periodo.pk]))

        self.assertEqual(resposta.status_code, 403)
        self.assertTrue(LogTrocaOPAtiva.objects.filter(pk=periodo.pk).exists())

    def test_excluir_parada_sem_permissao_recebe_403(self):
        _, parada = self._criar_periodo_com_parada()

        resposta = self.client.post(reverse("excluir_parada_tempo_producao", args=[parada.pk]))

        self.assertEqual(resposta.status_code, 403)
        self.assertTrue(ParadaMaquina.objects.filter(pk=parada.pk).exists())

    def test_excluir_periodo_com_permissao_exclui(self):
        self._conceder(EXCLUIR)
        periodo, _ = self._criar_periodo_com_parada()
        periodo.paradas.update(fim=timezone.now())

        resposta = self.client.post(reverse("excluir_periodo_tempo_producao", args=[periodo.pk]))

        self.assertRedirects(resposta, reverse("log_tempo_producao"))
        self.assertFalse(LogTrocaOPAtiva.objects.filter(pk=periodo.pk).exists())

    def _criar_periodo_no_recurso(self, recurso):
        agora = timezone.now().replace(microsecond=0)
        return LogTrocaOPAtiva.objects.create(
            recurso=recurso,
            origem="1",
            op=200,
            estagio=1,
            seqrot=1,
            horario_troca=agora - timedelta(hours=2),
            horario_saida=agora - timedelta(hours=1),
        )

    def test_excluir_periodo_de_outra_empresa_nao_encontra_registro(self):
        self._conceder(EXCLUIR)
        periodo_b = self._criar_periodo_no_recurso(self.recurso_b)

        resposta = self.client.post(reverse("excluir_periodo_tempo_producao", args=[periodo_b.pk]))

        # Com DEBUG=False o handler404 do projeto redireciona para a base;
        # o essencial é o registro permanecer.
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(LogTrocaOPAtiva.objects.filter(pk=periodo_b.pk).exists())

    def test_excluir_parada_de_outra_empresa_nao_encontra_registro(self):
        self._conceder(EXCLUIR)
        agora = timezone.now().replace(microsecond=0)
        parada_b = ParadaMaquina.objects.create(
            recurso=self.recurso_b,
            inicio=agora - timedelta(minutes=60),
            fim=agora - timedelta(minutes=45),
            tipo=ParadaMaquina.Tipo.MANUAL,
            usuario=self.usuario,
        )

        resposta = self.client.post(
            reverse("excluir_parada_tempo_producao", args=[parada_b.pk]),
            {"periodo_id": self._criar_periodo_no_recurso(self.recurso_b).pk},
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(ParadaMaquina.objects.filter(pk=parada_b.pk).exists())

    def test_excluir_parada_com_permissao_exclui(self):
        self._conceder(EXCLUIR)
        periodo, parada = self._criar_periodo_com_parada()

        resposta = self.client.post(
            reverse("excluir_parada_tempo_producao", args=[parada.pk]),
            {"periodo_id": periodo.pk},
        )

        # A parada só pertence a este período, então a view exclui o
        # registro; o período produtivo permanece.
        self.assertRedirects(resposta, reverse("log_tempo_producao"))
        self.assertFalse(ParadaMaquina.objects.filter(pk=parada.pk).exists())
        self.assertTrue(LogTrocaOPAtiva.objects.filter(pk=periodo.pk).exists())

    # --- alterar horários da parada ---

    def test_alterar_horarios_sem_permissao_recebe_403(self):
        _, parada = self._criar_periodo_com_parada()

        resposta = self.client.post(
            reverse("alterar_horarios_parada_tempo_producao", args=[parada.pk]),
            {"inicio": "2026-01-01 10:00", "fim": "2026-01-01 10:30"},
        )

        self.assertEqual(resposta.status_code, 403)

    def test_alterar_horarios_staff_passa_por_bypass(self):
        self.usuario.is_staff = True
        self.usuario.save()
        _, parada = self._criar_periodo_com_parada()

        resposta = self.client.post(
            reverse("alterar_horarios_parada_tempo_producao", args=[parada.pk]),
            {"inicio": "2026-01-01 10:00", "fim": "2026-01-01 10:30"},
        )

        # Autorização liberada; validação dos dados responde no fluxo normal.
        self.assertEqual(resposta.status_code, 302)
        self.assertNotEqual(resposta.status_code, 403)

    def test_alterar_horarios_com_permissao_passa_do_gate_de_rota(self):
        self._conceder(ALTERAR)
        _, parada = self._criar_periodo_com_parada()

        resposta = self.client.post(
            reverse("alterar_horarios_parada_tempo_producao", args=[parada.pk]),
            {"inicio": "", "fim": ""},
        )

        # Sem horários válidos a view nega por entrada (302 com mensagem),
        # provando que o gate passou; não é o 403 do decorator.
        self.assertEqual(resposta.status_code, 302)

    # --- abrir parada manual pelo log ---

    def test_sem_permissao_o_controle_de_parada_manual_nao_renderiza(self):
        Recurso.objects.filter(pk=self.recurso_a.pk).update(
            aponta_parada=True, permite_parada_manual=True
        )

        resposta = self.client.get(reverse("log_tempo_producao"))

        # O POST nega com 403 (teste abaixo); a tela não pode oferecer o
        # controle que o servidor vai negar — nem com recurso que permita
        # parada manual, era o fallback antigo do modal.
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, "Abrir Parada")
        self.assertNotContains(resposta, "modal-parada-manual")

    def test_com_permissao_o_controle_de_parada_manual_renderiza(self):
        Recurso.objects.filter(pk=self.recurso_a.pk).update(aponta_parada=True)
        self._conceder(ALTERAR)

        resposta = self.client.get(reverse("log_tempo_producao"))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Abrir Parada")
        self.assertContains(resposta, "modal-parada-manual")

    def test_staff_sem_permissao_direta_ve_o_controle_de_parada_manual(self):
        Recurso.objects.filter(pk=self.recurso_a.pk).update(aponta_parada=True)
        self.usuario.is_staff = True
        self.usuario.save()

        resposta = self.client.get(reverse("log_tempo_producao"))

        self.assertFalse(self.usuario.has_perm("producao.pode_alterar_paradas"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Abrir Parada")
        self.assertContains(resposta, "modal-parada-manual")

    def test_criar_parada_manual_log_sem_permissao_recebe_403(self):
        resposta = self.client.post(
            reverse("criar_parada_manual_log"),
            {"recurso": self.recurso_a.pk, "numcad": "1"},
        )

        self.assertEqual(resposta.status_code, 403)

    def test_criar_parada_manual_log_com_permissao_passa_do_gate(self):
        self._conceder(ALTERAR)
        agora = timezone.now().replace(microsecond=0)
        LogTrocaOPAtiva.objects.create(
            recurso=self.recurso_a,
            origem="1",
            op=100,
            estagio=1,
            seqrot=1,
            horario_troca=agora - timedelta(hours=1),
        )

        resposta = self.client.post(
            reverse("criar_parada_manual_log"),
            {"recurso": self.recurso_a.pk, "numcad": "invalido"},
        )

        # Operador inválido nega na validação de ERP, não no decorator.
        self.assertRedirects(resposta, reverse("log_tempo_producao"), fetch_redirect_response=False)
