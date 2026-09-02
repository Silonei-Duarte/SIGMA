from django.urls import path

from .utils.rastreamento_lote import rastreamento_lote
from .views.consulta_lote import consulta_lote, imprimir_etiqueta_lote, imprimir_etiquetas_grupo
from .views.liberar_area_vermelha import (
    buscar_descricao_transformacao,
    buscar_usuarios_erp,
    liberar_area_vermelha,
)
from .views.liberar_lotes import liberar_lotes
from .views.observacoes_etiqueta import observacoes_etiqueta
from .views.wms_views import (
    enviar_integracao_wms,
    enviar_todas_integracoes_wms,
    excluir_integracao_wms,
    excluir_todas_integracoes_wms,
    integracao_wms_view,
)

app_name = "qualidade"

urlpatterns = [
    path("liberar-lotes/", liberar_lotes, name="liberar_lotes"),
    path("area-vermelha/", liberar_area_vermelha, name="area_vermelha"),
    path(
        "area-vermelha/buscar-descricao-transformacao/",
        buscar_descricao_transformacao,
        name="buscar_descricao_transformacao",
    ),
    path("area-vermelha/buscar-usuarios-erp/", buscar_usuarios_erp, name="buscar_usuarios_erp"),
    path("area-vermelha/observacoes-etiqueta/", observacoes_etiqueta, name="observacoes_etiqueta"),
    path("consulta-lote/", consulta_lote, name="consulta_lote"),
    path("consulta-lote/rastreamento/", rastreamento_lote, name="rastreamento_lote"),
    path("consulta-lote/etiquetas/", imprimir_etiquetas_grupo, name="imprimir_etiquetas_grupo"),
    path(
        "consulta-lote/<int:registro_id>/etiqueta/",
        imprimir_etiqueta_lote,
        name="imprimir_etiqueta_lote",
    ),
    path("integracao-wms/", integracao_wms_view, name="integracao_wms"),
    path("integracao-wms/enviar/<int:pk>/", enviar_integracao_wms, name="enviar_integracao_wms"),
    path(
        "integracao-wms/enviar-todas/",
        enviar_todas_integracoes_wms,
        name="enviar_todas_integracoes_wms",
    ),
    path("integracao-wms/excluir/<int:pk>/", excluir_integracao_wms, name="excluir_integracao_wms"),
    path(
        "integracao-wms/excluir-todas/",
        excluir_todas_integracoes_wms,
        name="excluir_todas_integracoes_wms",
    ),
]
