from .auth import PaginaInicialLoginView, home
from .calendario import (
    api_evento_create,
    api_evento_update,
    api_eventos,
    calendarios,
    deletar_calendario,
    deletar_evento,
    editar_calendario,
    editar_evento,
    eventos_calendario,
)
from .centros_recursos import centros_recursos_view, deletar_centro_recurso
from .configuracoes import editar_configuracao, lista_configuracoes, voltar_ao_padrao_configuracao
from .departamentos import (
    cadastrar_departamento,
    deletar_departamento,
    editar_departamento,
    lista_departamentos,
)
from .empresas import criar_empresa, editar_empresa, lista_empresas
from .filiais import (
    ajax_centros,
    ajax_departamentos,
    ajax_filiais,
    ajax_recursos,
    ajax_setores,
    excluir_filial,
    lista_filiais,
)
from .grupos import grupos_view
from .horas_extras import deletar_hora_extra, editar_hora_extra, lista_horas_extras
from .planejado_views import reprocessar_planejado
from .recursos import (
    deletar_recurso,
    filtrar_centros,
    filtrar_departamentos,
    filtrar_setores,
    lista_recursos,
    motivos_por_grupo_parada,
    recursos_ativos_por_empresa,
)
from .services import status_services
from .setores import deletar_setor, setores_view
from .taras import deletar_tara, lista_taras
from .turnos import deletar_turno, editar_turno, lista_turnos, replicar_turnos
from .turnosbase import deletar_turno_base, editar_turno_base, turnos_base
from .usuarios import cadastrar_usuario, deletar_usuario, editar_usuario, lista_usuarios
from .utilitarios import (
    baixar_apk_sigma,
    enviar_email_teste,
    enviar_notificacao_teste,
    registrar_dispositivo_notificacao,
    utilitarios,
)

__all__ = [
    "PaginaInicialLoginView",
    "home",
    "api_evento_create",
    "api_evento_update",
    "api_eventos",
    "calendarios",
    "deletar_calendario",
    "deletar_evento",
    "editar_calendario",
    "editar_evento",
    "eventos_calendario",
    "centros_recursos_view",
    "deletar_centro_recurso",
    "editar_configuracao",
    "lista_configuracoes",
    "voltar_ao_padrao_configuracao",
    "cadastrar_departamento",
    "deletar_departamento",
    "editar_departamento",
    "lista_departamentos",
    "criar_empresa",
    "editar_empresa",
    "lista_empresas",
    "ajax_centros",
    "ajax_departamentos",
    "ajax_filiais",
    "ajax_recursos",
    "ajax_setores",
    "excluir_filial",
    "lista_filiais",
    "grupos_view",
    "deletar_hora_extra",
    "editar_hora_extra",
    "lista_horas_extras",
    "reprocessar_planejado",
    "deletar_recurso",
    "filtrar_centros",
    "filtrar_departamentos",
    "filtrar_setores",
    "lista_recursos",
    "motivos_por_grupo_parada",
    "recursos_ativos_por_empresa",
    "status_services",
    "deletar_setor",
    "setores_view",
    "deletar_tara",
    "lista_taras",
    "deletar_turno",
    "editar_turno",
    "lista_turnos",
    "replicar_turnos",
    "deletar_turno_base",
    "editar_turno_base",
    "turnos_base",
    "cadastrar_usuario",
    "deletar_usuario",
    "editar_usuario",
    "lista_usuarios",
    "baixar_apk_sigma",
    "enviar_email_teste",
    "enviar_notificacao_teste",
    "registrar_dispositivo_notificacao",
    "utilitarios",
]
