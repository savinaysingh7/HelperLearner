try:
    from channels.generic.websocket import AsyncJsonWebsocketConsumer
except Exception:  # pragma: no cover - optional runtime dependency
    AsyncJsonWebsocketConsumer = None


if AsyncJsonWebsocketConsumer is not None:
    class UpdatesConsumer(AsyncJsonWebsocketConsumer):
        """Authenticated websocket stream for realtime user updates."""

        async def connect(self):
            user = self.scope.get('user')
            if not user or not user.is_authenticated:
                await self.close(code=4401)
                return

            self.group_name = f'user_{user.pk}'
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()

        async def disconnect(self, code):
            if hasattr(self, 'group_name'):
                await self.channel_layer.group_discard(self.group_name, self.channel_name)

        async def receive_json(self, content, **kwargs):
            # Keep endpoint read-only for now.
            return None

        async def push_event(self, event):
            await self.send_json(
                {
                    'event': event.get('event'),
                    'payload': event.get('payload', {}),
                }
            )
else:
    class UpdatesConsumer:  # pragma: no cover - fallback when channels is absent
        pass
