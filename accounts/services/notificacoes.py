import logging
import threading
from pathlib import Path

import firebase_admin
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from firebase_admin import credentials, messaging

from accounts.models import DispositivoNotificacao

_firebase_lock = threading.Lock()
logger = logging.getLogger(__name__)


def _firebase_app():
    try:
        return firebase_admin.get_app()
    except ValueError:
        pass

    with _firebase_lock:
        try:
            return firebase_admin.get_app()
        except ValueError as error:
            caminho_configurado = settings.FIREBASE_CREDENTIALS_FILE
            if not caminho_configurado:
                raise ImproperlyConfigured("FIREBASE_CREDENTIALS_FILE não configurado.") from error

            caminho = Path(caminho_configurado)
            if not caminho.is_absolute():
                caminho = settings.BASE_DIR / caminho
            if not caminho.is_file():
                raise ImproperlyConfigured("Credencial Firebase não encontrada.") from error

            credencial = credentials.Certificate(str(caminho))
            return firebase_admin.initialize_app(credencial)


def enviar_notificacao_usuario(usuario, titulo, mensagem, dados=None):
    dispositivos = list(DispositivoNotificacao.objects.filter(usuario=usuario, ativo=True))
    if not dispositivos:
        return {"enviadas": 0, "falhas": 0}

    app = _firebase_app()
    enviadas = 0
    falhas = 0
    dados_texto = {str(chave): str(valor) for chave, valor in (dados or {}).items()}

    for dispositivo in dispositivos:
        notificacao = messaging.Message(
            notification=messaging.Notification(title=titulo, body=mensagem),
            data=dados_texto,
            android=messaging.AndroidConfig(
                notification=messaging.AndroidNotification(channel_id="sigma_geral"),
            ),
            token=dispositivo.token,
        )
        try:
            messaging.send(notificacao, app=app)
            enviadas += 1
        except messaging.UnregisteredError, messaging.SenderIdMismatchError:
            dispositivo.ativo = False
            dispositivo.save(update_fields=["ativo", "atualizado_em"])
            falhas += 1
        except Exception:
            logger.exception(
                "Falha ao enviar notificação Firebase para o dispositivo %s.",
                dispositivo.pk,
            )
            falhas += 1

    return {"enviadas": enviadas, "falhas": falhas}
