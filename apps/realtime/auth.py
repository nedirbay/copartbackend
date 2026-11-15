"""WebSocket üçin JWT awtorizasiýasy: ws://host/ws/?token=<access_token>"""
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken, TokenError


@database_sync_to_async
def _user_from_token(raw_token):
    auth = JWTAuthentication()
    try:
        validated = auth.get_validated_token(raw_token)
        return auth.get_user(validated)  # işjeň däl ulanyjy üçin AuthenticationFailed
    except (InvalidToken, TokenError, AuthenticationFailed):
        return AnonymousUser()


class JWTAuthMiddleware:
    """Brauzer WebSocket-de Authorization sözbaşysyny goýup bilmeýär, şonuň üçin token query-de gelýär."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        params = parse_qs(scope.get('query_string', b'').decode())
        token = (params.get('token') or [None])[0]
        scope = dict(scope, user=await _user_from_token(token) if token else AnonymousUser())
        return await self.app(scope, receive, send)
