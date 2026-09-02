from django.urls import include, path

urlpatterns = [
    path("manutencao/", include("setores.manutencao.urls")),
    path("qualidade/", include("setores.qualidade.urls")),
    path("pcp/", include("setores.pcp.urls")),
    path("logistica/", include("setores.logistica.urls")),
    path("suprimentos/", include("setores.suprimentos.urls")),
]
