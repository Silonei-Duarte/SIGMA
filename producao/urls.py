from django.urls import path
from django.views.generic import RedirectView

from .views import (
    abrir_parada_manual_apontamento,
    apontamento_base_view,
    consolidar_sequenciamento,
    desacoplar_op_ativa,
    encerrar_paradas,
    exportar_sequenciamento,
    justificar_paradas,
    sequenciamento_view,
    sequenciar_automatico,
    status_recursos_view,
)
from .views.logs_apontamento_componentes import (
    enviar_componente_log,
    enviar_todos_componentes_log,
    excluir_componente_log,
    excluir_todos_componentes_log,
    logs_apontamento_componentes,
)
from .views.logs_apontamentos import (
    buscar_dados_lote_erp,
    enviar_apontamento_log,
    enviar_todos_apontamentos_log,
    excluir_apontamento_erp,
    excluir_todos_apontamentos_log,
    logs_apontamentos,
)
from .views.logs_baixa_componentes import (
    enviar_baixa_componente_log,
    enviar_todas_baixas_componentes,
    excluir_baixa_componente,
    excluir_todas_baixas_componentes,
    logs_baixa_componentes,
)
from .views.logs_tempo_producao import (
    alterar_horarios_parada_tempo_producao,
    criar_parada_manual_log,
    excluir_parada_tempo_producao,
    excluir_periodo_tempo_producao,
    logs_tempo_producao,
    periodos_parada_manual,
    salvar_justificativas_parada,
)
from .views.logs_tempos_erp import (
    enviar_pacote_tempo_erp,
    enviar_tempos_erp,
    excluir_pacote_tempo_erp,
    excluir_parada_pacote_tempo_erp,
    excluir_tempos_erp_nao_integrados,
    logs_tempos_erp,
)

urlpatterns = [
    path("apontamentos/", apontamento_base_view, name="apontamento_base"),
    path(
        "apontamentos/recurso/<int:recurso_id>/justificar-paradas/",
        justificar_paradas,
        name="justificar_paradas",
    ),
    path(
        "apontamentos/recurso/<int:recurso_id>/encerrar-paradas/",
        encerrar_paradas,
        name="encerrar_paradas",
    ),
    path(
        "apontamentos/recurso/<int:recurso_id>/desacoplar-op/",
        desacoplar_op_ativa,
        name="desacoplar_op_ativa",
    ),
    path(
        "apontamentos/recurso/<int:recurso_id>/abrir-parada-manual/",
        abrir_parada_manual_apontamento,
        name="abrir_parada_manual_apontamento",
    ),
    path("status-recursos/", status_recursos_view, name="status_recursos"),
    path("logs-apontamentos/", logs_apontamentos, name="logs_apontamentos"),
    path(
        "logs-apontamentos/enviar/<int:pk>/", enviar_apontamento_log, name="enviar_apontamento_log"
    ),
    path(
        "logs-apontamentos/enviar-todos/",
        enviar_todos_apontamentos_log,
        name="enviar_todos_apontamentos_log",
    ),
    path(
        "logs-apontamentos/excluir/<int:pk>/",
        excluir_apontamento_erp,
        name="excluir_apontamento_erp",
    ),
    path(
        "logs-apontamentos/excluir-todos/",
        excluir_todos_apontamentos_log,
        name="excluir_todos_apontamentos_log",
    ),
    path("logs-apontamentos/buscar-lote-erp/", buscar_dados_lote_erp, name="buscar_dados_lote_erp"),
    path("log-tempo-producao/", logs_tempo_producao, name="log_tempo_producao"),
    path("log-tempos-erp/", logs_tempos_erp, name="logs_tempos_erp"),
    path("log-tempos-erp/enviar/", enviar_tempos_erp, name="enviar_tempos_erp"),
    path(
        "log-tempos-erp/<int:pk>/enviar/", enviar_pacote_tempo_erp, name="enviar_pacote_tempo_erp"
    ),
    path(
        "log-tempos-erp/<int:pk>/excluir/",
        excluir_pacote_tempo_erp,
        name="excluir_pacote_tempo_erp",
    ),
    path(
        "log-tempos-erp/parada/<int:pk>/excluir/",
        excluir_parada_pacote_tempo_erp,
        name="excluir_parada_pacote_tempo_erp",
    ),
    path(
        "log-tempos-erp/excluir-nao-integrados/",
        excluir_tempos_erp_nao_integrados,
        name="excluir_tempos_erp_nao_integrados",
    ),
    path(
        "log-tempo-producao/periodos-parada-manual/",
        periodos_parada_manual,
        name="periodos_parada_manual",
    ),
    path(
        "log-tempo-producao/criar-parada-manual/",
        criar_parada_manual_log,
        name="criar_parada_manual_log",
    ),
    path(
        "log-tempo-producao/parada/<int:pk>/horarios/",
        alterar_horarios_parada_tempo_producao,
        name="alterar_horarios_parada_tempo_producao",
    ),
    path(
        "log-tempo-producao/parada/<int:pk>/justificativas/",
        salvar_justificativas_parada,
        name="salvar_justificativas_parada",
    ),
    path(
        "log-tempo-producao/parada/<int:pk>/excluir/",
        excluir_parada_tempo_producao,
        name="excluir_parada_tempo_producao",
    ),
    path(
        "log-tempo-producao/periodo/<int:pk>/excluir/",
        excluir_periodo_tempo_producao,
        name="excluir_periodo_tempo_producao",
    ),
    path(
        "logs-parada/",
        RedirectView.as_view(pattern_name="log_tempo_producao", permanent=False),
        name="logs_parada_legacy",
    ),
    path(
        "logs-apontamento-componentes/",
        logs_apontamento_componentes,
        name="logs_apontamento_componentes",
    ),
    path(
        "logs-apontamento-componentes/enviar/<int:pk>/",
        enviar_componente_log,
        name="enviar_componente_log",
    ),
    path(
        "logs-apontamento-componentes/enviar-todos/",
        enviar_todos_componentes_log,
        name="enviar_todos_componentes_log",
    ),
    path(
        "logs-apontamento-componentes/excluir/<int:pk>/",
        excluir_componente_log,
        name="excluir_componente_log",
    ),
    path(
        "logs-apontamento-componentes/excluir-todos/",
        excluir_todos_componentes_log,
        name="excluir_todos_componentes_log",
    ),
    path("logs-baixa-componentes/", logs_baixa_componentes, name="logs_baixa_componentes"),
    path(
        "logs-baixa-componentes/enviar/<int:pk>/",
        enviar_baixa_componente_log,
        name="enviar_baixa_componente_log",
    ),
    path(
        "logs-baixa-componentes/enviar-todas/",
        enviar_todas_baixas_componentes,
        name="enviar_todas_baixas_componentes",
    ),
    path(
        "logs-baixa-componentes/excluir/<int:pk>/",
        excluir_baixa_componente,
        name="excluir_baixa_componente",
    ),
    path(
        "logs-baixa-componentes/excluir-todas/",
        excluir_todas_baixas_componentes,
        name="excluir_todas_baixas_componentes",
    ),
    path("sequenciamento/", sequenciamento_view, name="sequenciamento"),
    path("sequenciamento/consolidar/", consolidar_sequenciamento, name="consolidar_sequenciamento"),
    path("sequenciamento/exportar/", exportar_sequenciamento, name="exportar_sequenciamento"),
    path("sequenciamento/automatico/", sequenciar_automatico, name="sequenciar_automatico"),
]
