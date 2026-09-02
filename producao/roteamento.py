from django.urls import re_path

from . import consumidores

websocket_urlpatterns = [
    re_path(r"ws/recurso/(?P<recurso_id>\d+)/$", consumidores.RecursoConsumer.as_asgi()),
]
