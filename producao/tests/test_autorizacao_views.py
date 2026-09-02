from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import CentroRecurso, Departamento, Empresa, Filial, Recurso, Setor

User = get_user_model()


class AutorizacaoSequenciamentoStatusTests(TestCase):
    """Autorização e escopo das rotas privadas de Sequenciamento e Status de Recursos."""

    def setUp(self):
        self.empresa_a = Empresa.objects.create(codemp=901, nome="Empresa A", fantasia="EA")
        self.filial_a = Filial.objects.create(
            empresa=self.empresa_a,
            codfil=1,
            nome="Filial A",
            fantasia="FA",
            cnpj=f"{901_00001:014d}",
        )
        self.usuario = User.objects.create_user(
            username="prod_a", password="senha", filial=self.filial_a
        )
        self.client.force_login(self.usuario)

    def _criar_centro_empresa_b(self):
        empresa_b = Empresa.objects.create(codemp=902, nome="Empresa B", fantasia="EB")
        filial_b = Filial.objects.create(
            empresa=empresa_b,
            codfil=1,
            nome="Filial B",
            fantasia="FB",
            cnpj=f"{902_00001:014d}",
        )
        departamento = Departamento.objects.create(filial=filial_b, descricao="Depto B")
        setor = Setor.objects.create(departamento=departamento, descricao="Setor B")
        return CentroRecurso.objects.create(setor=setor, codigo="CRB", descricao="Centro B")

    def _conceder(self, codename):
        permissao = Permission.objects.get(content_type__app_label="producao", codename=codename)
        self.usuario.user_permissions.add(permissao)

    # --- sequenciamento ---

    def test_anonimo_e_redirecionado_para_o_login(self):
        self.client.logout()

        resposta = self.client.get(reverse("sequenciamento"))

        self.assertEqual(resposta.status_code, 302)

    def test_sequenciamento_sem_permissao_recebe_403(self):
        resposta = self.client.get(reverse("sequenciamento"))

        self.assertEqual(resposta.status_code, 403)

    def test_sequenciamento_com_permissao_acessa_a_tela(self):
        self._conceder("pode_acessar_sequenciamento")

        resposta = self.client.get(reverse("sequenciamento"))

        self.assertEqual(resposta.status_code, 200)

    def test_staff_acessa_o_sequenciamento_sem_permissao(self):
        self.usuario.is_staff = True
        self.usuario.save()

        resposta = self.client.get(reverse("sequenciamento"))

        self.assertEqual(resposta.status_code, 200)

    # --- exportar_sequenciamento ---

    def test_exportar_sem_permissao_recebe_403(self):
        resposta = self.client.get(reverse("exportar_sequenciamento"), {"centro": "1"})

        self.assertEqual(resposta.status_code, 403)

    def test_exportar_com_permissao_passa_do_gate_de_rota(self):
        # Sem centro informado a view responde 400 próprio — prova que o
        # gate de permissão deixou passar até o corpo.
        self._conceder("pode_acessar_sequenciamento")

        resposta = self.client.get(reverse("exportar_sequenciamento"))

        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(resposta.content.decode(), "Centro não informado.")

    # --- consolidar / automático (ação sensível) ---

    def test_consolidar_sem_permissao_recebe_403_do_decorator(self):
        resposta = self.client.post(reverse("consolidar_sequenciamento"))

        self.assertEqual(resposta.status_code, 403)

    def test_consolidar_com_permissao_alcanca_validacao_interna_de_centro(self):
        self._conceder("pode_consolidar_sequenciamento_erp")

        resposta = self.client.post(
            reverse("consolidar_sequenciamento"),
            {"centro_id": "", "sequenciamento_json": "[]"},
        )

        # Rota liberada pelo decorator; a validação de escopo do centro segue
        # respondendo dentro da view (não é 403 do decorator).
        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(resposta.json()["msg"], "Centro não disponível.")

    def test_superusuario_passa_da_rota_de_consolidar(self):
        self.usuario.is_superuser = True
        self.usuario.save()

        resposta = self.client.post(
            reverse("consolidar_sequenciamento"),
            {"centro_id": "", "sequenciamento_json": "[]"},
        )

        self.assertEqual(resposta.json()["msg"], "Centro não disponível.")

    def test_automatico_sem_permissao_recebe_403(self):
        resposta = self.client.post(reverse("sequenciar_automatico"))

        self.assertEqual(resposta.status_code, 403)

    def test_automatico_com_permissao_alcanca_validacao_interna_de_centro(self):
        self._conceder("pode_consolidar_sequenciamento_erp")

        resposta = self.client.post(
            reverse("sequenciar_automatico"),
            {"centro_id": "", "sequenciamento_json": "[]"},
        )

        # Rota liberada pelo decorator; a view segue sua própria validação
        # de entrada (resposta JSON da view, não o 403 cru do decorator).
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["msg"], "Centro não informado")

    # --- escopo cross-filial com identificador forjado ---

    def test_consolidar_nao_aceita_centro_de_outra_empresa(self):
        self._conceder("pode_consolidar_sequenciamento_erp")
        centro_b = self._criar_centro_empresa_b()

        resposta = self.client.post(
            reverse("consolidar_sequenciamento"),
            {"centro_id": centro_b.pk, "sequenciamento_json": "[]"},
        )

        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(resposta.json()["msg"], "Centro não disponível.")

    def test_automatico_nao_aceita_centro_de_outra_empresa(self):
        self._conceder("pode_consolidar_sequenciamento_erp")
        centro_b = self._criar_centro_empresa_b()

        resposta = self.client.post(
            reverse("sequenciar_automatico"),
            {"centro_id": centro_b.pk, "sequenciamento_json": "[]"},
        )

        # Centro de outra empresa nega na validação interna, antes do ERP.
        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(resposta.json()["msg"], "Centro não disponível.")

    def test_exportar_nao_exporta_centro_de_outra_empresa(self):
        self._conceder("pode_acessar_sequenciamento")
        centro_b = self._criar_centro_empresa_b()

        resposta = self.client.get(reverse("exportar_sequenciamento"), {"centro": centro_b.pk})

        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(resposta.content.decode(), "Centro não disponível para o seu usuário.")

    def test_post_do_sequenciamento_descarta_centro_forjado(self):
        self._conceder("pode_acessar_sequenciamento")
        centro_b = self._criar_centro_empresa_b()
        Recurso.objects.create(centro_recurso=centro_b, codigo="RB", descricao="Recurso B")

        resposta = self.client.post(
            reverse("sequenciamento"), {"centro": centro_b.pk, "empresa": self.empresa_a.pk}
        )

        # O centro de outra empresa nunca entra no escopo; a view trata como
        # falha de consulta e renderiza a mensagem genérica sem tocar no ERP.
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            resposta.context["erro"], "Não foi possível consultar o sequenciamento no ERP."
        )

    def test_superusuario_passa_dos_gates_sem_permissao(self):
        self.usuario.is_superuser = True
        self.usuario.save()

        self.assertEqual(self.client.get(reverse("sequenciamento")).status_code, 200)
        # 400 vem da validação interna (sem centro), provando que o gate passou.
        resposta_exportar = self.client.get(reverse("exportar_sequenciamento"))
        self.assertEqual(resposta_exportar.status_code, 400)
        self.assertEqual(self.client.get(reverse("status_recursos")).status_code, 200)

    # --- status_recursos ---

    def test_status_recursos_sem_permissao_recebe_403(self):
        resposta = self.client.get(reverse("status_recursos"))

        self.assertEqual(resposta.status_code, 403)

    def test_status_recursos_com_permissao_renderiza(self):
        self._conceder("pode_acessar_relatorios_producao")

        resposta = self.client.get(reverse("status_recursos"))

        self.assertEqual(resposta.status_code, 200)

    def test_status_recursos_para_staff(self):
        self.usuario.is_staff = True
        self.usuario.save()

        resposta = self.client.get(reverse("status_recursos"))

        self.assertEqual(resposta.status_code, 200)
