"""
Wakalary ugratmak.

* Ähli wakalar `transaction.on_commit` arkaly ugradylýar: tranzaksiýa yzyna gaýtarylsa waka gitmeýär
  we müşderi maglumaty okanda eýýäm täze ýagdaýy görýär.
* HTTP soragynyň dowamynda wakalar ýygnalýar we jogap taýýar bolanda bir gezek (gaýtalanmazdan)
  ugradylýar — bir hereket (meselem, status + taryh + bildiriş) müşderä bir signal bolup barýar.
* Kanal gatlagy (Redis) işlemese esasy hereket bozulmaýar, diňe log ýazylýar.

Toparlar (groups):
    user.<id>    — bir ulanyjynyň ähli birikmeleri (web + mobil)
    role.admin   — ähli Adminler
    all          — ähli giren ulanyjylar
"""
import contextvars
import json
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

logger = logging.getLogger(__name__)

ADMIN_GROUP = 'role.admin'
ALL_GROUP = 'all'

# Waka görnüşleri (müşderiler bilen umumy şertnama)
VEHICLE_CHANGED = 'vehicle.changed'
VEHICLE_DELETED = 'vehicle.deleted'
NOTIFICATIONS_CHANGED = 'notifications.changed'
DICTIONARY_CHANGED = 'dictionary.changed'
EMPLOYEES_CHANGED = 'employees.changed'

# Consumer-iň usullary (channels: "rt.event" -> rt_event)
_MSG_EVENT = 'rt.event'
_MSG_FORCE_LOGOUT = 'rt.force_logout'


def user_group(user_id):
    return f'user.{user_id}'


# Häzirki HTTP soragy üçin bufer: {(payload_json, msg_type): set(groups)} ýa-da None
_buffer = contextvars.ContextVar('realtime_buffer', default=None)


def _send(group, message):
    """Kanal gatlagyna bir habar ugradýar (testlerde çalşyp bolýar)."""
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(group, message)


def _dispatch(items):
    decoded = [(json.loads(payload_json), msg_type, groups) for (payload_json, msg_type), groups in items]
    # Awtoulag pozulanda onuň çykdajy/taryh ýazgylary hem pozulýar — artykmaç "changed" wakasyny ugratmaýarys
    deleted = {p['vin'] for p, _, _ in decoded if p.get('type') == VEHICLE_DELETED}
    for payload, msg_type, groups in decoded:
        if payload.get('type') == VEHICLE_CHANGED and payload.get('vin') in deleted:
            continue
        message = {'type': msg_type, 'payload': payload}
        for group in sorted(groups):
            try:
                _send(group, message)
            except Exception as exc:  # Redis ýok / ýalňyşlyk — esasy hereketi bozmaly däl
                logger.warning("Real-time waka ugradylmady (%s -> %s): %s", msg_type, group, exc)


def _enqueue(groups, payload, msg_type):
    groups = {g for g in groups if g}
    if not groups:
        return
    key = (json.dumps(payload, sort_keys=True, default=str), msg_type)

    def on_commit():
        buf = _buffer.get()
        if buf is None:
            _dispatch([(key, groups)])
        else:
            buf.setdefault(key, set()).update(groups)

    transaction.on_commit(on_commit)


def publish(groups, event_type, **data):
    """`groups` toparlaryna {"type": event_type, ...data} wakasyny ugradýar."""
    _enqueue(groups, {'type': event_type, **data}, _MSG_EVENT)


def force_logout(user_id):
    """Ulanyjynyň ähli açyk WebSocket birikmelerini ýapýar (meselem, işjeňsizleşdirilende)."""
    _enqueue([user_group(user_id)], {'type': 'session.revoked'}, _MSG_FORCE_LOGOUT)


class buffered:
    """Kontekst: içinde döredilen wakalar ýygnalýar we çykanda bir gezek ugradylýar."""

    def __enter__(self):
        self._token = _buffer.set({})
        return self

    def __exit__(self, exc_type, exc, tb):
        buf = _buffer.get()
        _buffer.reset(self._token)
        if buf:
            _dispatch(list(buf.items()))
        return False
