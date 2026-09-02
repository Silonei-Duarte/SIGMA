"""
Testes das dez rotas de exclusão do accounts que passaram a exigir POST.

Cobrem o achado alto da auditoria: as exclusões respondiam a GET, sem
proteção CSRF nenhuma (bastava um <img src="...deletar/1/"> em outra
página para excluir um cadastro pela sessão de um usuário logado). Depois
da correção, `@require_POST` faz o Django devolver 405 para GET antes de
qualquer checagem de negócio.
"""

from datetime import date, time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import (
    Calendario,
    CentroRecurso,
    Departamento,
    Empresa,
    Filial,
    HoraExtraPlanejada,
    Recurso,
    Setor,
    Tara,
    TurnoBase,
    TurnoRecurso,
)

User = get_user_model()


class ExclusaoExigePostTests(TestCase):
    """GET nas dez rotas de exclusão deve devolver 405, nunca executar a exclusão."""

    def setUp(self):
        self.superusuario = User.objects.create_user(
            username="admin.exclusoes.get",
            password="Senha@2026",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.superusuario)

        empresa = Empresa.objects.create(codemp=200, nome="Empresa Exclusão GET", fantasia="EEG")
        self.filial = Filial.objects.create(
            empresa=empresa,
            codfil=1,
            nome="Filial Exclusão GET",
            fantasia="FEG",
            cnpj="44.444.444/0001-44",
        )
        self.calendario = Calendario.objects.create(filial=self.filial, descricao="Calendário GET")
        self.departamento = Departamento.objects.create(
            filial=self.filial, descricao="Departamento GET"
        )
        self.turno_base = TurnoBase.objects.create(
            codigo="TB-GET", descricao="Turno Base GET", ordenacao=1, calendario=self.calendario
        )
        self.setor = Setor.objects.create(departamento=self.departamento, descricao="Setor GET")
        self.centro_recurso = CentroRecurso.objects.create(
            setor=self.setor, codigo="CR-GET", descricao="Centro GET"
        )
        self.recurso = Recurso.objects.create(
            codigo="R-GET", descricao="Recurso GET", centro_recurso=self.centro_recurso
        )
        self.tara = Tara.objects.create(tara="Tara GET", peso="10.000")
        self.turno_recurso = TurnoRecurso.objects.create(
            turnobase=self.turno_base,
            recurso=self.recurso,
            dias=[1, 2],
            hora_inicio=time(6, 0),
            hora_fim=time(14, 0),
        )
        self.hora_extra = HoraExtraPlanejada.objects.create(
            turnobase=self.turno_base,
            recurso=self.recurso,
            data_inicio=date(2026, 1, 1),
            data_fim=date(2026, 1, 31),
            hora_inicio=time(18, 0),
            hora_fim=time(20, 0),
        )

    def test_get_retorna_405_em_todas_as_rotas_de_exclusao(self):
        rotas = [
            ("excluir_filial", [self.filial.pk]),
            ("deletar_departamento", [self.departamento.pk]),
            ("deletar_turno_base", [self.turno_base.pk]),
            ("deletar_calendario", [self.calendario.pk]),
            ("deletar_setor", [self.setor.pk]),
            ("deletar_centro_recurso", [self.centro_recurso.pk]),
            ("deletar_recurso", [self.recurso.pk]),
            ("deletar_tara", [self.tara.pk]),
            ("deletar_turno", [self.turno_recurso.pk]),
            ("deletar_hora_extra", [self.hora_extra.pk]),
        ]
        for nome_rota, args in rotas:
            with self.subTest(rota=nome_rota):
                resposta = self.client.get(reverse(nome_rota, args=args))
                self.assertEqual(resposta.status_code, 405)


class ExclusaoPostContinuaFuncionandoTests(TestCase):
    """POST com CSRF válido (o client de teste já lida com isso por padrão)
    continua excluindo normalmente — a mudança não pode quebrar o caminho feliz."""

    def setUp(self):
        self.superusuario = User.objects.create_user(
            username="admin.exclusoes.post",
            password="Senha@2026",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.superusuario)
        self.empresa = Empresa.objects.create(
            codemp=300, nome="Empresa Exclusão POST", fantasia="EEP"
        )

    def _nova_filial(self, codfil):
        return Filial.objects.create(
            empresa=self.empresa,
            codfil=codfil,
            nome=f"Filial POST {codfil}",
            fantasia="FP",
            cnpj="55.555.555/0001-55",
        )

    def test_post_exclui_filial(self):
        filial = self._nova_filial(1)
        resposta = self.client.post(reverse("excluir_filial", args=[filial.pk]))
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(Filial.objects.filter(pk=filial.pk).exists())

    def test_post_exclui_departamento(self):
        filial = self._nova_filial(2)
        departamento = Departamento.objects.create(filial=filial, descricao="Departamento POST")
        resposta = self.client.post(reverse("deletar_departamento", args=[departamento.pk]))
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(Departamento.objects.filter(pk=departamento.pk).exists())

    def test_post_exclui_calendario(self):
        filial = self._nova_filial(3)
        calendario = Calendario.objects.create(filial=filial, descricao="Calendário POST")
        resposta = self.client.post(reverse("deletar_calendario", args=[calendario.pk]))
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(Calendario.objects.filter(pk=calendario.pk).exists())

    def test_post_exclui_turno_base(self):
        filial = self._nova_filial(4)
        calendario = Calendario.objects.create(filial=filial, descricao="Calendário TB POST")
        turno_base = TurnoBase.objects.create(
            codigo="TB-POST-4", descricao="TB POST", ordenacao=1, calendario=calendario
        )
        resposta = self.client.post(reverse("deletar_turno_base", args=[turno_base.pk]))
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(TurnoBase.objects.filter(pk=turno_base.pk).exists())

    def test_post_exclui_setor(self):
        filial = self._nova_filial(5)
        departamento = Departamento.objects.create(
            filial=filial, descricao="Departamento Setor POST"
        )
        setor = Setor.objects.create(departamento=departamento, descricao="Setor POST")
        resposta = self.client.post(reverse("deletar_setor", args=[setor.pk]))
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(Setor.objects.filter(pk=setor.pk).exists())

    def test_post_exclui_centro_recurso(self):
        filial = self._nova_filial(6)
        departamento = Departamento.objects.create(filial=filial, descricao="Departamento CR POST")
        setor = Setor.objects.create(departamento=departamento, descricao="Setor CR POST")
        centro = CentroRecurso.objects.create(
            setor=setor, codigo="CR-POST-6", descricao="Centro POST"
        )
        resposta = self.client.post(reverse("deletar_centro_recurso", args=[centro.pk]))
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(CentroRecurso.objects.filter(pk=centro.pk).exists())

    def test_post_exclui_recurso(self):
        filial = self._nova_filial(7)
        departamento = Departamento.objects.create(
            filial=filial, descricao="Departamento Recurso POST"
        )
        setor = Setor.objects.create(departamento=departamento, descricao="Setor Recurso POST")
        centro = CentroRecurso.objects.create(
            setor=setor, codigo="CR-POST-7", descricao="Centro Recurso POST"
        )
        recurso = Recurso.objects.create(
            codigo="R-POST-7", descricao="Recurso POST", centro_recurso=centro
        )
        if recurso.id == 1:
            # a view bloqueia por regra de negócio a exclusão do recurso id=1 ("Geral");
            # em bases novas o autoincremento pode cair aqui por acaso de ordem de execução.
            self.skipTest(
                "Recurso criado com id=1 nesta execução; view bloqueia por regra de negócio."
            )
        resposta = self.client.post(reverse("deletar_recurso", args=[recurso.pk]))
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(Recurso.objects.filter(pk=recurso.pk).exists())

    def test_post_exclui_tara(self):
        tara = Tara.objects.create(tara="Tara POST", peso="5.000")
        resposta = self.client.post(reverse("deletar_tara", args=[tara.pk]))
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(Tara.objects.filter(pk=tara.pk).exists())

    def test_post_exclui_turno_recurso(self):
        filial = self._nova_filial(8)
        departamento = Departamento.objects.create(
            filial=filial, descricao="Departamento Turno POST"
        )
        setor = Setor.objects.create(departamento=departamento, descricao="Setor Turno POST")
        centro = CentroRecurso.objects.create(
            setor=setor, codigo="CR-POST-8", descricao="Centro Turno POST"
        )
        recurso = Recurso.objects.create(
            codigo="R-POST-8", descricao="Recurso Turno POST", centro_recurso=centro
        )
        calendario = Calendario.objects.create(filial=filial, descricao="Calendário Turno POST")
        turno_base = TurnoBase.objects.create(
            codigo="TB-POST-8", descricao="TB Turno POST", ordenacao=1, calendario=calendario
        )
        turno_recurso = TurnoRecurso.objects.create(
            turnobase=turno_base,
            recurso=recurso,
            dias=[1],
            hora_inicio=time(6, 0),
            hora_fim=time(14, 0),
        )
        resposta = self.client.post(reverse("deletar_turno", args=[turno_recurso.pk]))
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(TurnoRecurso.objects.filter(pk=turno_recurso.pk).exists())

    def test_post_exclui_hora_extra(self):
        filial = self._nova_filial(9)
        departamento = Departamento.objects.create(filial=filial, descricao="Departamento HE POST")
        setor = Setor.objects.create(departamento=departamento, descricao="Setor HE POST")
        centro = CentroRecurso.objects.create(
            setor=setor, codigo="CR-POST-9", descricao="Centro HE POST"
        )
        recurso = Recurso.objects.create(
            codigo="R-POST-9", descricao="Recurso HE POST", centro_recurso=centro
        )
        calendario = Calendario.objects.create(filial=filial, descricao="Calendário HE POST")
        turno_base = TurnoBase.objects.create(
            codigo="TB-POST-9", descricao="TB HE POST", ordenacao=1, calendario=calendario
        )
        hora_extra = HoraExtraPlanejada.objects.create(
            turnobase=turno_base,
            recurso=recurso,
            data_inicio=date(2026, 1, 1),
            data_fim=date(2026, 1, 31),
            hora_inicio=time(18, 0),
            hora_fim=time(20, 0),
        )
        resposta = self.client.post(reverse("deletar_hora_extra", args=[hora_extra.pk]))
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(HoraExtraPlanejada.objects.filter(pk=hora_extra.pk).exists())
