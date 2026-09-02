"""Regressões de apresentação do log de tempo de produção."""

from datetime import datetime
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.utils import timezone


class LogsTempoProducaoTemplateTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="tester_template_log_tempo", password="x"
        )

    def test_parada_com_acao_reserva_tres_slots_e_parada_sem_acao_mostra_traco(self):
        agora = timezone.make_aware(datetime(2026, 1, 1, 10, 0))
        parada_com_horario = self._parada(
            id=1,
            pode_alterar_horarios=True,
            pode_alterar_justificativas=False,
            fim=None,
            inicio=agora,
        )
        parada_sem_acao = self._parada(
            id=2,
            pode_alterar_horarios=False,
            pode_alterar_justificativas=False,
            fim=None,
            inicio=agora,
        )
        periodo = self._periodo(agora, [parada_com_horario, parada_sem_acao])
        request = RequestFactory().get("/producao/log-tempo-producao/")
        request.user = self.usuario

        conteudo = render_to_string(
            "producao/logs_tempo_producao.html",
            {"periodos": [periodo], "recursos_parada_manual": []},
            request=request,
        )

        self.assertIn('title="Alterar horários da parada"', conteudo)
        self.assertEqual(conteudo.count('class="inline-flex h-9 w-9" aria-hidden="true"'), 2)
        self.assertNotIn('title="Alterar justificativas"', conteudo)
        self.assertNotIn('title="Excluir parada"', conteudo)
        self.assertIn("\n                                            -\n", conteudo)

    def _parada(self, **values):
        values.update(
            {
                "get_tipo_display": "Manual",
                "operador": "Operador",
                "inicio_exibicao": values["inicio"],
                "fim_exibicao": values["fim"],
                "tempo_parada_exibicao": "00:10:00",
                "usuario": self.usuario,
                "data_hora": values["inicio"],
                "justificativas_exibicao": [],
                "justificativas": SimpleNamespace(all=[]),
                "justificativas_ordenadas": [],
                "motivos_parada": [],
            }
        )
        return SimpleNamespace(**values)

    def _periodo(self, agora, paradas):
        empresa = SimpleNamespace(codemp=1)
        filial = SimpleNamespace(empresa=empresa)
        departamento = SimpleNamespace(filial=filial)
        setor = SimpleNamespace(departamento=departamento)
        centro_recurso = SimpleNamespace(setor=setor)
        recurso = SimpleNamespace(codigo="R1", centro_recurso=centro_recurso)
        return SimpleNamespace(
            id=1,
            paradas_periodo=paradas,
            recurso=recurso,
            origem="1",
            op=1,
            estagio=1,
            seqrot=1,
            id_operador=1,
            horario_troca=agora,
            horario_saida=agora,
            tempo_periodo="00:00:00",
            usuario=self.usuario,
            data_hora=agora,
            expandido=True,
            tem_parada_aberta=True,
        )
