"""
FCM (Firebase Cloud Messaging) push bildirişleri — mobil programma ýapyk wagty hem.

Sazlamak: FIREBASE_CREDENTIALS_FILE=/ýol/service-account.json (Firebase Console -> Project settings ->
Service accounts -> Generate new private key). Boş bolsa push öçük, galan ähli zat öňküsi ýaly işleýär.

"data" habary ugradylýar ({id, vehicle, kind, message}) — mobil programma ony WebSocket wakasy ýaly
görkezýär; ID birmeňzeş bolany üçin iki ýoldan gelse-de telefon bir bildiriş görkezýär.
"""
import logging
import threading

from django.conf import settings
from django.db import transaction

from .models import PushDevice

logger = logging.getLogger(__name__)

FCM_SCOPE = 'https://www.googleapis.com/auth/firebase.messaging'
# Bu ýalňyşlyklar token indi ýaramsyz diýmekdir (programma pozuldy / token çalşyldy)
_DEAD_TOKEN_ERRORS = {'UNREGISTERED', 'INVALID_ARGUMENT', 'SENDER_ID_MISMATCH'}

_session = None
_project_id = None
_lock = threading.Lock()


def _get_session():
    """Service account bilen awtorizasiýaly HTTP sessiýa (token özi täzelenýär). Sazlanmadyk bolsa None."""
    global _session, _project_id
    path = getattr(settings, 'FIREBASE_CREDENTIALS_FILE', '')
    if not path:
        return None, None
    with _lock:
        if _session is None:
            from google.auth.transport.requests import AuthorizedSession
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_file(path, scopes=[FCM_SCOPE])
            _session, _project_id = AuthorizedSession(creds), creds.project_id
    return _session, _project_id


def is_enabled():
    return bool(getattr(settings, 'FIREBASE_CREDENTIALS_FILE', ''))


def _run_in_background(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()


def _error_status(response):
    try:
        details = response.json().get('error', {})
    except ValueError:
        return ''
    for d in details.get('details', []):
        if d.get('errorCode'):
            return d['errorCode']
    return details.get('status', '')


def _deliver(jobs):
    """jobs: [(token, data)]. Ýaramsyz tokenleri pozýar."""
    try:
        session, project_id = _get_session()
    except Exception as exc:
        logger.error("FCM sazlamasy ýalňyş (FIREBASE_CREDENTIALS_FILE): %s", exc)
        return
    if session is None:
        return
    url = f'https://fcm.googleapis.com/v1/projects/{project_id}/messages:send'
    dead = []
    for token, data in jobs:
        body = {'message': {'token': token, 'data': data, 'android': {'priority': 'high'}}}
        try:
            resp = session.post(url, json=body, timeout=10)
        except Exception as exc:
            logger.warning("FCM bildirişi ugradylmady: %s", exc)
            continue
        if resp.status_code == 200:
            continue
        error = _error_status(resp)
        if resp.status_code in (400, 404) and error in _DEAD_TOKEN_ERRORS:
            dead.append(token)
        else:
            logger.warning("FCM ýalňyşlygy %s: %s", resp.status_code, resp.text[:300])
    if dead:
        PushDevice.objects.filter(token__in=dead).delete()


def send_notifications(notifications):
    """Döredilen bildirişleri eýeleriniň telefonlaryna ugradýar (tranzaksiýadan soň, fonda)."""
    if not is_enabled() or not notifications:
        return
    items = [
        (n.user_id, {
            'id': str(n.pk), 'vehicle': n.vehicle_id or '', 'kind': n.kind, 'message': n.message,
        })
        for n in notifications
    ]

    def on_commit():
        tokens = {}
        for user_id, token in PushDevice.objects.filter(user_id__in={u for u, _ in items}).values_list('user_id', 'token'):
            tokens.setdefault(user_id, []).append(token)
        jobs = [(t, data) for user_id, data in items for t in tokens.get(user_id, [])]
        if jobs:
            _run_in_background(_deliver, jobs)

    transaction.on_commit(on_commit)
