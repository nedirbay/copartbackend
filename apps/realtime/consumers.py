from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .events import ADMIN_GROUP, ALL_GROUP, user_group

# Ýapylyş kodlary (müşderiler bilen umumy şertnama)
CLOSE_UNAUTHORIZED = 4001  # token ýok / möhleti geçen — täzeläp gaýtadan birikmeli
CLOSE_SESSION_REVOKED = 4003  # ulanyjy işjeňsizleşdirildi — gaýtadan birikmeli däl


class RealtimeConsumer(AsyncJsonWebsocketConsumer):
    """
    Her giren ulanyjy öz toparyna (user.<id>), Admin bolsa role.admin toparyna goşulýar.
    Serwer -> müşderi: {"type": "vehicle.changed", "vin": "..."} we ş.m.
    Müşderi -> serwer: {"type": "ping"} -> {"type": "pong"}
    """

    async def connect(self):
        user = self.scope.get('user')
        if user is None or not user.is_authenticated:
            # accept()-dan öň ýapylsa müşderi diňe HTTP 403 görýär — kody okap biler ýaly ilki kabul edýäris
            await self.accept()
            await self.close(code=CLOSE_UNAUTHORIZED)
            return
        self.groups_joined = [user_group(user.pk), ALL_GROUP]
        if user.is_admin_role:
            self.groups_joined.append(ADMIN_GROUP)
        for group in self.groups_joined:
            await self.channel_layer.group_add(group, self.channel_name)
        await self.accept()
        await self.send_json({'type': 'hello', 'user_id': user.pk})

    async def disconnect(self, code):
        for group in getattr(self, 'groups_joined', []):
            await self.channel_layer.group_discard(group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if isinstance(content, dict) and content.get('type') == 'ping':
            await self.send_json({'type': 'pong'})

    # ---- kanal gatlagyndan gelýän habarlar (events.py)
    async def rt_event(self, message):
        await self.send_json(message['payload'])

    async def rt_force_logout(self, message):
        await self.send_json(message['payload'])
        await self.close(code=CLOSE_SESSION_REVOKED)
