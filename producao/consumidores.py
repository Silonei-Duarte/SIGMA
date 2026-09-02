import json
from urllib.parse import parse_qs

from channels.generic.websocket import AsyncWebsocketConsumer


class RecursoConsumer(AsyncWebsocketConsumer):
    """Canal único do navegador para os eventos do recurso selecionado."""

    async def connect(self):
        self.recurso_id = self.scope["url_route"]["kwargs"]["recurso_id"]
        codbar = parse_qs(self.scope["query_string"].decode()).get("codbar", [""])[0]
        self.group_names = [
            f"recurso_{self.recurso_id}",
            f"balanca_{self.recurso_id}",
        ]
        if codbar:
            self.group_names.append(f"op_{codbar}")
        for group_name in self.group_names:
            await self.channel_layer.group_add(group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        for group_name in self.group_names:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def balanca_update(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "balanca_update",
                    "balanca": event["balanca"],
                }
            )
        )

    async def refresh_page(self, event):
        await self.send(text_data=json.dumps({"type": "refresh_page"}))

    async def parada_update(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "parada_update",
                    "aberta": event.get("aberta", False),
                    "pendentes": event.get("pendentes", 0),
                    "bloqueia": event.get("bloqueia", False),
                }
            )
        )
