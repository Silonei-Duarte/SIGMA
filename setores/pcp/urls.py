from django.urls import path

from .views.calendario_ops import (
    calendario_ops,
    detalhes_calendario_ops,
    eventos_calendario_ops,
    salvar_cores_calendario_ops,
)

app_name = "pcp"

urlpatterns = [
    path("calendario-ops/", calendario_ops, name="calendario_ops"),
    path("calendario-ops/eventos/", eventos_calendario_ops, name="eventos_calendario_ops"),
    path("calendario-ops/cores/", salvar_cores_calendario_ops, name="salvar_cores_calendario_ops"),
    path("calendario-ops/detalhes/", detalhes_calendario_ops, name="detalhes_calendario_ops"),
]
