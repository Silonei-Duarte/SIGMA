from django.urls import path

from .views.sensores import cadastro_sensores, configurar_recurso, excluir_fonte, excluir_sensor

urlpatterns = [
    path("sensores/", cadastro_sensores, name="telemetria_sensores"),
    path("sensores/<int:sensor_id>/editar/", cadastro_sensores, name="telemetria_editar_sensor"),
    path("sensores/<int:sensor_id>/excluir/", excluir_sensor, name="telemetria_excluir_sensor"),
    path("fontes/<int:fonte_id>/editar/", cadastro_sensores, name="telemetria_editar_fonte"),
    path("fontes/<int:fonte_id>/excluir/", excluir_fonte, name="telemetria_excluir_fonte"),
    path(
        "recursos/<int:recurso_id>/configurar/",
        configurar_recurso,
        name="telemetria_configurar_recurso",
    ),
]
