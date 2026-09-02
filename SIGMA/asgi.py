"""
ASGI config for SIGMA project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

import producao.roteamento

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SIGMA.settings")

django_asgi_app = get_asgi_application()

from accounts.apps import iniciar_workers_em_background  # noqa: E402

iniciar_workers_em_background()

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(URLRouter(producao.roteamento.websocket_urlpatterns)),
    }
)
