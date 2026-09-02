from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CentroRecurso, Departamento, Empresa, Filial, Recurso, Setor
from producao.models import Apontamento, LogTrocaOPAtiva, PacoteTempoERP

User = get_user_model()

PERMISSAO = "pode_excluir_pendencias_integracao"


class AutorizacaoExclusaoFilasTests(TestCase):
    """Exclusões das filas de integração usam a permissão unificada.

    O decorator exige `producao.pode_excluir_pendencias_integracao`; por
    decisão do sênior não há mais guard interno de superusuário: quem
    recebe a permissão exclui, e staff/superusuário passam pelo bypass do
    decorator. O escopo por empresa continua no corpo das views.
    """

    def setUp(self):
        self.empresa = Empresa.objects.create(codemp=1, nome="Empresa 1", fantasia="E1")
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            codfil=1,
            nome="Filial 1",
            fantasia="F1",
            cnpj=f"{1_00001:014d}",
        )
        self.apontamento = Apontamento.objects.create(
            codemp=1,
            origem="1",
            numorp=100,
            codetg=1,
            seqrot=1,
            numcad=1,
            qtdre1=10,
            lote="L1",
        )
        self.usuario = User.objects.create_user(
            username="fila_a", password="senha", filial=self.filial
        )
        self.client.force_login(self.usuario)

    def _conceder(self):
        self.usuario.user_permissions.add(
            Permission.objects.get(content_type__app_label="producao", codename=PERMISSAO)
        )

    # --- deny da rota (decorator) ---

    def test_anonimo_e_redirecionado_para_o_login(self):
        self.client.logout()

        resposta = self.client.post(reverse("excluir_apontamento_erp", args=[self.apontamento.pk]))

        self.assertEqual(resposta.status_code, 302)

    def test_autenticado_sem_permissao_recebe_403(self):
        rotas = [
            ("excluir_apontamento_erp", [self.apontamento.pk]),
            ("excluir_todos_apontamentos_log", []),
            ("excluir_componente_log", [1]),
            ("excluir_todos_componentes_log", []),
            ("excluir_baixa_componente", [1]),
            ("excluir_todas_baixas_componentes", []),
            ("excluir_pacote_tempo_erp", [1]),
            ("excluir_parada_pacote_tempo_erp", [1]),
            ("excluir_tempos_erp_nao_integrados", []),
        ]
        for nome, argumentos in rotas:
            with self.subTest(rota=nome):
                resposta = self.client.post(reverse(nome, args=argumentos))
                self.assertEqual(resposta.status_code, 403)

    # --- autorizadas: com permissão, staff e superusuário ---

    def test_com_permissao_exclui_registro_da_propria_empresa(self):
        self._conceder()

        resposta = self.client.post(reverse("excluir_apontamento_erp", args=[self.apontamento.pk]))

        self.assertRedirects(resposta, reverse("logs_apontamentos"))
        self.assertFalse(Apontamento.objects.filter(pk=self.apontamento.pk).exists())

    def test_staff_passa_sem_permissao_por_bypass_do_decorator(self):
        self.usuario.is_staff = True
        self.usuario.save()

        resposta = self.client.post(reverse("excluir_apontamento_erp", args=[self.apontamento.pk]))

        self.assertRedirects(resposta, reverse("logs_apontamentos"))
        self.assertFalse(Apontamento.objects.filter(pk=self.apontamento.pk).exists())

    def test_superusuario_exclui_sem_precisar_da_permissao(self):
        self.usuario.is_superuser = True
        self.usuario.save()

        resposta = self.client.post(reverse("excluir_apontamento_erp", args=[self.apontamento.pk]))

        self.assertRedirects(resposta, reverse("logs_apontamentos"))
        self.assertFalse(Apontamento.objects.filter(pk=self.apontamento.pk).exists())


class EscopoExclusaoTemposErpTests(TestCase):
    """Exclusões dos pacotes de tempo ERP respeitam o escopo de recursos do
    usuário: com permissão, não-staff não alcança pacote de outra empresa."""

    @classmethod
    def setUpTestData(cls):
        cls.empresa_a, cls.recurso_a = cls._criar_cadeia(11, "A")
        cls.empresa_b, cls.recurso_b = cls._criar_cadeia(12, "B")

    @staticmethod
    def _criar_cadeia(codemp, sufixo):
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
        recurso = Recurso.objects.create(
            centro_recurso=centro, codigo=f"R{sufixo}", descricao=f"Recurso {sufixo}"
        )
        return empresa, recurso

    def _criar_pacote(self, recurso):
        agora = timezone.now()
        troca = LogTrocaOPAtiva.objects.create(
            recurso=recurso,
            origem="1",
            op=100,
            estagio=1,
            seqrot=1,
            horario_troca=agora - timedelta(hours=8),
        )
        return PacoteTempoERP.objects.create(
            troca_op_ativa=troca,
            corte_inicio_real=agora - timedelta(hours=4),
            corte_fim_real=agora,
            status=PacoteTempoERP.Status.PENDENTE,
        )

    def _login_com_permissao(self, filial):
        usuario = User.objects.create_user(
            username=f"tmp{filial.pk}", password="senha", filial=filial
        )
        usuario.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="producao", codename="pode_excluir_pendencias_integracao"
            )
        )
        self.client.force_login(usuario)
        return usuario

    def test_excluir_pacote_de_outra_empresa_nao_encontra_registro(self):
        self._login_com_permissao(self.empresa_a.filiais.first())
        pacote_b = self._criar_pacote(self.recurso_b)

        resposta = self.client.post(reverse("excluir_pacote_tempo_erp", args=[pacote_b.pk]))

        self.assertRedirects(resposta, reverse("logs_tempos_erp"))
        self.assertTrue(PacoteTempoERP.objects.filter(pk=pacote_b.pk).exists())

    def test_excluir_nao_integrados_limita_ao_escopo_do_usuario(self):
        self._login_com_permissao(self.empresa_a.filiais.first())
        pacote_a = self._criar_pacote(self.recurso_a)
        pacote_b = self._criar_pacote(self.recurso_b)

        resposta = self.client.post(reverse("excluir_tempos_erp_nao_integrados"))

        self.assertRedirects(resposta, reverse("logs_tempos_erp"))
        self.assertFalse(PacoteTempoERP.objects.filter(pk=pacote_a.pk).exists())
        self.assertTrue(PacoteTempoERP.objects.filter(pk=pacote_b.pk).exists())
