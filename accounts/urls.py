from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views
from .views.filiais import (
    ajax_departamentos,
    ajax_filiais,
)

urlpatterns = [
    # Home e autenticação
    path("", views.home, name="home"),
    path("login/", views.PaginaInicialLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(next_page="login"), name="logout"),
    # Usuários
    path("usuarios/", views.lista_usuarios, name="lista_usuarios"),
    path("usuarios/cadastrar/", views.cadastrar_usuario, name="cadastrar_usuario"),
    path("usuarios/editar/<int:user_id>/", views.editar_usuario, name="editar_usuario"),
    path("usuarios/deletar/<int:user_id>/", views.deletar_usuario, name="deletar_usuario"),
    path("grupos/", views.grupos_view, name="grupos_view"),
    # Empresas
    path("empresas/", views.lista_empresas, name="lista_empresas"),
    path("empresas/criar/", views.criar_empresa, name="criar_empresa"),
    path("empresas/<int:pk>/editar/", views.editar_empresa, name="editar_empresa"),
    # Filiais
    path("filiais/", views.lista_filiais, name="lista_filiais"),
    path("filiais/<int:pk>/editar/", views.lista_filiais, name="editar_filial"),
    path("filiais/excluir/<int:pk>/", views.excluir_filial, name="excluir_filial"),
    # Departamentos
    path("departamentos/", views.lista_departamentos, name="lista_departamentos"),
    path("departamentos/cadastrar/", views.cadastrar_departamento, name="cadastrar_departamento"),
    path(
        "departamentos/editar/<int:departamento_id>/",
        views.editar_departamento,
        name="editar_departamento",
    ),
    path(
        "departamentos/deletar/<int:pk>/", views.deletar_departamento, name="deletar_departamento"
    ),
    # Turno Base
    path("turnos-base/", views.turnos_base, name="turnos_base"),
    path("turnos-base/editar/<int:pk>/", views.editar_turno_base, name="editar_turno_base"),
    path("turnos-base/deletar/<int:pk>/", views.deletar_turno_base, name="deletar_turno_base"),
    # Calendários
    path("calendarios/", views.calendarios, name="calendarios"),
    path("calendarios/editar/<int:pk>/", views.editar_calendario, name="editar_calendario"),
    path("calendarios/deletar/<int:pk>/", views.deletar_calendario, name="deletar_calendario"),
    # Eventos de Calendário
    path(
        "calendarios/<int:calendario_id>/eventos/",
        views.eventos_calendario,
        name="eventos_calendario",
    ),
    path("eventos/editar/<int:pk>/", views.editar_evento, name="editar_evento"),
    path("eventos/deletar/<int:pk>/", views.deletar_evento, name="deletar_evento"),
    # API JSON para calendário
    path("calendarios/<int:calendario_id>/eventos/json/", views.api_eventos, name="api_eventos"),
    path("calendarios/evento/create/", views.api_evento_create, name="api_evento_create"),
    path("calendarios/evento/update/", views.api_evento_update, name="api_evento_update"),
    # Setores
    path("setores/", views.setores_view, name="setores"),
    path("setores/editar/<int:setor_id>/", views.setores_view, name="editar_setor"),
    path("setores/deletar/<int:pk>/", views.deletar_setor, name="deletar_setor"),
    # Centros de Recursos
    path("centros-recursos/", views.centros_recursos_view, name="centros_recursos"),
    path(
        "centros-recursos/editar/<int:centro_id>/",
        views.centros_recursos_view,
        name="editar_centro_recurso",
    ),
    path(
        "centros-recursos/deletar/<int:pk>/",
        views.deletar_centro_recurso,
        name="deletar_centro_recurso",
    ),
    # Recursos
    path("recursos/", views.lista_recursos, name="lista_recursos"),
    path("recursos/deletar/<int:pk>/", views.deletar_recurso, name="deletar_recurso"),
    # Taras
    path("taras/", views.lista_taras, name="lista_taras"),
    path("taras/deletar/<int:pk>/", views.deletar_tara, name="deletar_tara"),
    # AJAX cascata
    path("ajax/filiais/", ajax_filiais, name="ajax_filiais"),
    path("ajax/departamentos/", ajax_departamentos, name="ajax_departamentos"),
    path("ajax/setores/", views.ajax_setores, name="ajax_setores"),
    path("ajax/centros/", views.ajax_centros, name="ajax_centros"),
    path("ajax/recursos/", views.ajax_recursos, name="ajax_recursos"),
    path(
        "ajax/motivos-por-grupo-parada/",
        views.motivos_por_grupo_parada,
        name="motivos_por_grupo_parada",
    ),
    path(
        "ajax/recursos-ativos-por-empresa/",
        views.recursos_ativos_por_empresa,
        name="recursos_ativos_por_empresa",
    ),
    # Turnos
    path("turnos/", views.lista_turnos, name="lista_turnos"),
    path("turnos/deletar/<int:pk>/", views.deletar_turno, name="deletar_turno"),
    path("turnos/editar/<int:pk>/", views.editar_turno, name="editar_turno"),
    path("turnos/replicar/<int:recurso_id>/", views.replicar_turnos, name="replicar_turnos"),
    # Horas Extras Planejadas
    path("horas_extras/", views.lista_horas_extras, name="lista_horas_extras"),
    path("horas_extras/deletar/<int:pk>/", views.deletar_hora_extra, name="deletar_hora_extra"),
    path("horas_extras/editar/<int:pk>/", views.editar_hora_extra, name="editar_hora_extra"),
    # OEE Planejado
    path("oee/reprocessar/", views.reprocessar_planejado, name="reprocessar_planejado"),
    # Services internos
    path("services/status/", views.status_services, name="status_services"),
    # Configurações da aplicação (variáveis não sensíveis editáveis em runtime;
    # só chaves declaradas em código são listadas e editáveis — sem criar;
    # voltar ao padrão exclui a linha salva e restitui o default do código)
    path("configuracoes/", views.lista_configuracoes, name="lista_configuracoes"),
    path(
        "configuracoes/editar/<str:chave>/",
        views.editar_configuracao,
        name="editar_configuracao",
    ),
    path(
        "configuracoes/padrao/<str:chave>/",
        views.voltar_ao_padrao_configuracao,
        name="voltar_padrao_configuracao",
    ),
    # Utilitários (notificações Android, APK, e-mail)
    path("utilitarios/", views.utilitarios, name="utilitarios"),
    path("notificacoes/apk/", views.baixar_apk_sigma, name="baixar_apk_sigma"),
    path(
        "notificacoes/dispositivos/registrar/",
        views.registrar_dispositivo_notificacao,
        name="registrar_dispositivo_notificacao",
    ),
    path(
        "notificacoes/teste/enviar/",
        views.enviar_notificacao_teste,
        name="enviar_notificacao_teste",
    ),
    path(
        "utilitarios/email/enviar/",
        views.enviar_email_teste,
        name="enviar_email_teste",
    ),
]
