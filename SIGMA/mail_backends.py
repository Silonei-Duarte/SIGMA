import base64
import logging
from time import monotonic
from urllib.parse import quote

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)


class MicrosoftGraphEmailBackend(BaseEmailBackend):
    """Envia mensagens Django pelo Microsoft Graph com client credentials."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.access_token = None
        self.access_token_expires_at = 0

    def open(self):
        if self.access_token and monotonic() < self.access_token_expires_at:
            return False

        required_settings = (
            "MICROSOFT_GRAPH_TENANT_ID",
            "MICROSOFT_GRAPH_CLIENT_ID",
            "MICROSOFT_GRAPH_CLIENT_SECRET",
            "MICROSOFT_GRAPH_MAIL_SENDER",
        )
        missing = [name for name in required_settings if not getattr(settings, name, "")]
        if missing:
            error = "Configuração Microsoft Graph ausente: " + ", ".join(missing)
            if self.fail_silently:
                logger.error(error)
                return None
            raise ValueError(error)

        try:
            response = requests.post(
                f"https://login.microsoftonline.com/{settings.MICROSOFT_GRAPH_TENANT_ID}/oauth2/v2.0/token",
                data={
                    "client_id": settings.MICROSOFT_GRAPH_CLIENT_ID,
                    "client_secret": settings.MICROSOFT_GRAPH_CLIENT_SECRET,
                    "scope": "https://graph.microsoft.com/.default",
                    "grant_type": "client_credentials",
                },
                timeout=settings.MICROSOFT_GRAPH_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            self.access_token = payload["access_token"]
            self.access_token_expires_at = monotonic() + max(
                int(payload.get("expires_in", 3600)) - 60, 0
            )
        except (KeyError, TypeError, ValueError, requests.RequestException) as exc:
            self.access_token = None
            logger.exception("Não foi possível autenticar no Microsoft Graph: %s", exc)
            if not self.fail_silently:
                raise
            return None
        return True

    def close(self):
        self.access_token = None
        self.access_token_expires_at = 0

    @staticmethod
    def _recipients(addresses):
        return [{"emailAddress": {"address": address}} for address in addresses]

    @staticmethod
    def _attachments(message):
        attachments = []
        for attachment in message.attachments:
            if not isinstance(attachment, tuple):
                raise ValueError("Anexos MIME não são suportados pelo backend Microsoft Graph.")
            filename, content, mimetype = attachment
            if isinstance(content, str):
                content = content.encode()
            attachments.append(
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": filename,
                    "contentType": mimetype or "application/octet-stream",
                    "contentBytes": base64.b64encode(content).decode("ascii"),
                }
            )
        return attachments

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if self.open() is None:
            return 0

        sent_count = 0
        endpoint = "https://graph.microsoft.com/v1.0/users/{}/sendMail".format(
            quote(settings.MICROSOFT_GRAPH_MAIL_SENDER, safe="")
        )
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        for message in email_messages:
            if not message.recipients():
                continue
            graph_message = {
                "subject": message.subject,
                "body": {
                    "contentType": "HTML" if message.content_subtype == "html" else "Text",
                    "content": message.body,
                },
                "toRecipients": self._recipients(message.to),
            }
            if message.cc:
                graph_message["ccRecipients"] = self._recipients(message.cc)
            if message.bcc:
                graph_message["bccRecipients"] = self._recipients(message.bcc)
            attachments = self._attachments(message)
            if attachments:
                graph_message["attachments"] = attachments

            try:
                response = requests.post(
                    endpoint,
                    headers=headers,
                    json={"message": graph_message, "saveToSentItems": True},
                    timeout=settings.MICROSOFT_GRAPH_TIMEOUT,
                )
                response.raise_for_status()
            except (ValueError, requests.RequestException) as exc:
                detail = str(exc)
                response_obj = getattr(exc, "response", None)
                if response_obj is not None and response_obj.text:
                    detail = f"{detail} | {response_obj.text}"
                logger.exception("Não foi possível enviar e-mail pelo Microsoft Graph: %s", detail)
                if not self.fail_silently:
                    raise RuntimeError(detail) from exc
            else:
                sent_count += 1

        return sent_count
