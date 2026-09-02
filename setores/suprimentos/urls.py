from django.urls import path

from .views import componentes_separar

app_name = "suprimentos"

urlpatterns = [
    path("componentes-a-separar/", componentes_separar, name="componentes_separar"),
]
