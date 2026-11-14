"""Bildirişler: programmanyň içinde saklanýar, Telegram sazlanan bolsa oňa hem ugradylýar."""
import json
import logging
import threading
import urllib.request

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

from .models import Notification

logger = logging.getLogger(__name__)
User = get_user_model()


def _send_telegram(chat_id, text):
    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    if not token or not chat_id:
        return
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps({'chat_id': chat_id, 'text': text}).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
        )
        urllib.request.urlopen(req, timeout=5).read()
    except Exception as exc:  # Telegram ýalňyşlygy esasy hereketi bozmaly däl
        logger.warning("Telegram bildirişi ugradylmady: %s", exc)


def notify(users, message, *, vehicle=None, kind='INFO', exclude=None):
    """Berlen ulanyjylara bildiriş döredýär. exclude — hereketi edeniň özüne ugratmazlyk üçin."""
    recipients = {u.pk: u for u in users if u is not None and u.is_active}
    if exclude is not None:
        recipients.pop(exclude.pk, None)
    if not recipients:
        return

    text = f"{vehicle.vin}: {message}" if vehicle is not None else message
    Notification.objects.bulk_create([
        Notification(user=u, vehicle=vehicle, kind=kind, message=text[:500]) for u in recipients.values()
    ])

    chat_ids = [u.telegram_chat_id for u in recipients.values() if u.telegram_chat_id]
    if chat_ids and getattr(settings, 'TELEGRAM_BOT_TOKEN', ''):
        def send_all():
            for chat_id in chat_ids:
                _send_telegram(chat_id, text)
        # Tranzaksiýa üstünlikli tamamlanandan soň, jogaby saklamazdan fon akymynda
        transaction.on_commit(lambda: threading.Thread(target=send_all, daemon=True).start())


def admins():
    return list(User.objects.filter(is_active=True).filter(role=User.Role.ADMIN)) + \
        list(User.objects.filter(is_active=True, is_superuser=True).exclude(role=User.Role.ADMIN))
