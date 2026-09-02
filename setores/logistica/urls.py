from django.urls import path

from .views import (
    bobinas_disponiveis,
    componentes_movimentar_view,
    historico_lote_componente,
)

app_name = "logistica"

urlpatterns = [
    path("componentes-movimentar/", componentes_movimentar_view, name="componentes_movimentar"),
    path(
        "componentes-movimentar/historico-lote/",
        historico_lote_componente,
        name="historico_lote_componente",
    ),
    path("componentes-movimentar/bobinas-wms/", bobinas_disponiveis, name="bobinas_disponiveis"),
]
